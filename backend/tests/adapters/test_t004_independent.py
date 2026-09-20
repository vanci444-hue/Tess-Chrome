"""T004 Tester 的补充验收：隔离临时库、合成响应，无真实外部请求。"""

import asyncio
import json
from contextlib import asynccontextmanager
from decimal import ROUND_HALF_UP, Decimal

import httpx
import pytest
from sqlalchemy import func, select
from src.adapters.amap import AmapProvider
from src.adapters.asr import QwenASRConnection
from src.adapters.base import ProviderError
from src.adapters.llm import BailianLLMProvider
from src.config.settings import Settings
from src.db.models import ASRSession, Fact, SalesInput, TimelineMessage
from src.tools.finance import calculate_finance
from test_asr import FakeUpstream, allocate
from test_asr import client as client_fixture

client = client_fixture


def test_independent_payment_oracle():
    # 独立逐月账本核对，而非仅复制被测公式的最终答案。
    product = dict(
        id="isolated",
        method="equal_payment",
        terms_months=[24],
        monthly_interest_rate="0.003",
        min_down_ratio="0",
        max_down_ratio="1",
        financed_fees_fen=12000,
        upfront_fees_fen=5000,
        discount_fen=30000,
        source_kind="mock",
    )
    result = calculate_finance(23456789, product, {"down_payment_fen": 8000000})
    plan = result["solutions"][0]
    balance = Decimal(23456789 + 12000 - 30000 - 8000000)
    for _ in range(23):
        balance = balance + balance * Decimal(".003") - plan["monthly_payment_fen"]
    expected_last = int((balance * Decimal("1.003")).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    assert plan["last_payment_fen"] == expected_last
    assert (
        plan["financing_cost_fen"]
        == plan["monthly_payment_fen"] * 23 + expected_last - plan["principal_fen"] + 17000
    )
    with pytest.raises(ProviderError, match="冲突"):
        calculate_finance(20000, dict(product, discount_fen=30000), {})


async def test_configuration_waits_for_acknowledgement_and_rejects_error():
    events = asyncio.Queue()
    sent = []

    class Wire:
        async def send_json(self, value):
            sent.append(value)

    connection = QwenASRConnection(Wire(), Settings())
    connection.receive = events.get
    waiting = asyncio.create_task(connection.configure("zh"))
    await asyncio.sleep(0)
    assert not waiting.done()
    await events.put({"type": "session.created"})
    await asyncio.sleep(0)
    assert not waiting.done()
    await events.put({"type": "session.updated"})
    await asyncio.wait_for(waiting, 1)
    assert sent[0]["session"]["input_audio_transcription"] == {"language": "zh"}
    await events.put({"type": "error"})
    with pytest.raises(ProviderError) as rejected:
        await connection.configure(None)
    assert rejected.value.code == "ASR_CONFIG_REJECTED"


@pytest.mark.parametrize("explicit_discard", [False, True])
def test_client_disconnect_and_discard_release_provider_without_business_data(
    client, explicit_discard
):
    client, app, session = client
    closed = asyncio.Event()

    class Provider:
        @asynccontextmanager
        async def connect(self, language):
            try:
                yield FakeUpstream()
            finally:
                closed.set()

    app.state.asr_provider = Provider()
    data = allocate(client, session).json()["data"]
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        if explicit_discard:
            ws.send_json({"type": "discard"})
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

    async def verify():
        await asyncio.wait_for(closed.wait(), 1)
        async with app.state.session_factory() as db:
            row = await db.get(ASRSession, data["asr_session_id"])
            assert row.state == "discarded" and row.finished_at
            for model in (Fact, SalesInput, TimelineMessage):
                assert await db.scalar(select(func.count()).select_from(model)) == 0

    client.portal.call(verify)
    assert not list(app.state.settings.upload_path.glob("**/*"))


def test_audio_missing_key_is_503_not_placeholder_stream(client):
    client, app, session = client
    app.state.settings.bailian_api_key = ""
    response = allocate(client, session)
    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["error_code"] == "DEPENDENCY_UNAVAILABLE"
    assert app.state.asr_provider.upstream is None


async def test_map_route_marker_correspondence_and_payload_size():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("driving"):
            return httpx.Response(
                200,
                json={"status": "1", "route": {"paths": [{"distance": "2560", "duration": "540"}]}},
            )
        return httpx.Response(
            200, content=b"\x89PNG\r\n\x1a\n" + b"x" * 50, headers={"content-type": "image/png"}
        )

    config = Settings(amap_web_service_key="synthetic-only")
    provider = AmapProvider(config, httpx.MockTransport(respond))
    center = {"longitude": 116.4, "latitude": 40}
    stations = [{"number": 1, "location_gcj02": {"longitude": 116.41, "latitude": 40.01}}]
    route = await provider.route(center, stations[0]["location_gcj02"])
    assert route["driving_distance_m"] == 2560 and route["driving_duration_seconds"] == 540
    assert "center_distance_m" not in route
    await provider.static_map(center, stations)
    markers = requests[-1].url.params["markers"]
    assert markers == "mid,0x333333,中:116.4,40|mid,0xE82127,1:116.41,40.01"
    config.map_image_max_bytes = 10
    with pytest.raises(ProviderError) as oversized:
        await provider.static_map(center, stations)
    assert oversized.value.code == "MAP_RESPONSE_TOO_LARGE"


async def test_llm_timeout_is_single_attempt_and_safe_error():
    calls = []

    def timeout(request):
        calls.append(json.loads(request.content))
        raise httpx.ReadTimeout("synthetic-private-error", request=request)

    provider = BailianLLMProvider(
        Settings(bailian_api_key="synthetic-only", bailian_base_url="https://example.test/v1"),
        httpx.MockTransport(timeout),
    )
    with pytest.raises(ProviderError) as failure:
        await provider.complete([{"role": "user", "content": "计算"}])
    assert failure.value.code == "LLM_TIMEOUT"
    assert "synthetic" not in str(failure.value) and len(calls) == 1
