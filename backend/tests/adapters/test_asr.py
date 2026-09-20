"""ASR 使用可控上游模拟事件验证隔离与协议，不是识别准确率验收。"""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from src.adapters.asr import QwenASRConnection
from src.api.routes.audio import router
from src.config.settings import Settings
from src.db.models import ASRSession, Customer, Fact, SalesInput, Session, TimelineMessage
from src.main import create_app
from starlette.websockets import WebSocketDisconnect


class FakeUpstream:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.sent = []

    async def append(self, pcm):
        self.sent.append(pcm)
        for event in [
            {
                "type": "conversation.item.input_audio_transcription.text",
                "item_id": "i",
                "text": "首付",
                "stash": "八万",
            },
            {
                "type": "conversation.item.input_audio_transcription.text",
                "item_id": "i",
                "text": "首付",
                "stash": "八万",
            },
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "item_id": "i",
                "transcript": "首付八万",
            },
            {
                "type": "conversation.item.input_audio_transcription.text",
                "item_id": "i",
                "text": "旧的",
                "stash": "迟到",
            },
        ]:
            await self.queue.put(event)

    async def finish(self):
        await self.queue.put({"type": "session.finished"})

    async def receive(self):
        return await self.queue.get()


class FakeProvider:
    def __init__(self):
        self.upstream = None
        self.languages = []

    @asynccontextmanager
    async def connect(self, language):
        self.languages.append(language)
        self.upstream = FakeUpstream()
        yield self.upstream


@pytest.fixture
def client(tmp_path):
    cfg = Settings(
        database_path=str(tmp_path / "isolated.db"),
        upload_dir=str(tmp_path / "uploads"),
        bailian_api_key="test",
        bailian_asr_ws_url="wss://example.test",
    )
    app = create_app(cfg, extra_routers=[router])
    app.state.asr_provider = FakeProvider()

    async def seed():
        async with app.state.session_factory() as db:
            c = Customer(nickname="独立测试", normalized_phone="13800000000")
            db.add(c)
            await db.flush()
            s = Session(customer_id=c.id, title="Test")
            db.add(s)
            await db.commit()
            return s.id

    with TestClient(app, base_url="http://127.0.0.1:8099") as client:
        session = client.portal.call(seed)
        yield client, app, session


def allocate(client, session, key=None, language=None):
    return client.post(
        f"/api/sessions/{session}/audio",
        json={"expected_revision": 1, "language": language},
        headers={"Origin": "http://127.0.0.1:5199", "Idempotency-Key": key or str(uuid4())},
    )


def test_stream_dedup_manual_send_isolation_single_use(client):
    client, app, session = client
    key = str(uuid4())
    response = allocate(client, session, key, "zh")
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert allocate(client, session, key, "zh").json()["data"] == data
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"\0" * 3200)
        assert ws.receive_json()["type"] == "partial"
        assert ws.receive_json()["type"] == "final"
        ws.send_json({"type": "finish"})
        assert ws.receive_json()["type"] == "finished"
    assert app.state.asr_provider.languages == ["zh"]
    assert allocate(client, session, key, "zh").status_code == 409

    async def verify():
        async with app.state.session_factory() as db:
            for model in (Fact, SalesInput, TimelineMessage):
                assert await db.scalar(select(func.count()).select_from(model)) == 0
            row = await db.get(ASRSession, data["asr_session_id"])
            assert row.state == "finished"

    client.portal.call(verify)


def test_ws_boundary_and_bad_pcm(client):
    client, app, session = client
    data = allocate(client, session).json()["data"]
    from starlette.testclient import WebSocketDenialResponse

    with pytest.raises(WebSocketDenialResponse) as error:
        with client.websocket_connect(
            data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "https://evil.example"}
        ):
            pass
    assert error.value.status_code == 403
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(b"1")
        assert ws.receive_json()["code"] == "ASR_PROTOCOL_ERROR"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1008


async def test_provider_session_config_pcm_vad_finish_no_commit():
    class WS:
        def __init__(self):
            self.sent = []

        async def send_json(self, value):
            self.sent.append(value)

    ws = WS()
    connection = QwenASRConnection(ws, Settings())

    async def receive():
        return {"type": "session.updated"}

    connection.receive = receive
    await connection.configure(None)
    await connection.append(b"1234")
    await connection.finish()
    assert ws.sent[0]["session"]["input_audio_format"] == "pcm"
    assert ws.sent[0]["session"]["sample_rate"] == 16000
    assert ws.sent[1]["type"] == "input_audio_buffer.append"
    assert ws.sent[2]["type"] == "session.finish"
    assert all(e["type"] != "input_audio_buffer.commit" for e in ws.sent)


def test_finish_timeout_and_backpressure_preserve_business_isolation(client):
    client, app, session = client

    class Stuck(FakeUpstream):
        async def append(self, pcm):
            await asyncio.Event().wait()

        async def finish(self):
            pass

    class StuckProvider:
        @asynccontextmanager
        async def connect(self, language):
            yield Stuck()

    app.state.asr_provider = StuckProvider()
    data = allocate(client, session).json()["data"]
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        for _ in range(23):
            ws.send_bytes(b"\0" * 3200)
        assert ws.receive_json()["code"] == "ASR_BACKPRESSURE"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    app.state.settings.asr_finish_timeout = 0.01
    data = allocate(client, session).json()["data"]
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "finish"})
        assert ws.receive_json()["code"] == "ASR_FINISH_TIMEOUT"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_duration_limit_accepts_inflight_audio_then_finishes(client):
    client, app, session = client
    app.state.settings.asr_session_max_seconds = 1
    data = allocate(client, session).json()["data"]
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        limit = ws.receive_json()
        assert limit["code"] == "ASR_DURATION_LIMIT" and limit["incomplete"] is False
        ws.send_bytes(b"\0" * 3200)
        ws.send_json({"type": "finish"})
        ws.send_json({"type": "finish"})
        kinds = []
        while True:
            event = ws.receive_json()
            kinds.append(event["type"])
            if event["type"] == "finished":
                break
        assert kinds == ["partial", "final", "finished"]


def test_expired_and_wrong_session_do_not_open_provider(client):
    client, app, session = client
    data = allocate(client, session).json()["data"]
    from starlette.testclient import WebSocketDenialResponse

    with pytest.raises(WebSocketDenialResponse) as error:
        with client.websocket_connect(
            data["ws_path"].replace(session, str(uuid4())),
            headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"},
        ):
            pass
    assert error.value.status_code == 404 and app.state.asr_provider.upstream is None

    async def expire():
        async with app.state.session_factory() as db:
            row = await db.get(ASRSession, data["asr_session_id"])
            row.created_at = "2020-01-01T00:00:00+00:00"
            await db.commit()

    client.portal.call(expire)
    with pytest.raises(WebSocketDenialResponse) as error:
        with client.websocket_connect(
            data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
        ):
            pass
    assert error.value.status_code == 403 and app.state.asr_provider.upstream is None


def test_cancel_unconnected_reservation_retry_and_ownership(client):
    client, app, session = client
    data = allocate(client, session).json()["data"]
    assert allocate(client, session).status_code == 409
    path = f"/api/sessions/{session}/audio/{data['asr_session_id']}"
    headers = {"Origin": "http://127.0.0.1:5199", "Content-Type": "application/json"}
    assert client.delete(path.replace(session, str(uuid4())), headers=headers).status_code == 404
    assert allocate(client, session).status_code == 409
    assert client.delete(path, headers=headers).json()["data"]["state"] == "discarded"
    assert client.delete(path, headers=headers).status_code == 200
    assert allocate(client, session).status_code == 201
    assert app.state.asr_provider.upstream is None


def test_cancel_does_not_steal_connected_recording(client):
    client, app, session = client
    data = allocate(client, session).json()["data"]
    path = f"/api/sessions/{session}/audio/{data['asr_session_id']}"
    with client.websocket_connect(
        data["ws_path"], headers={"host": "127.0.0.1:8099", "origin": "http://127.0.0.1:5199"}
    ) as ws:
        assert ws.receive_json()["type"] == "ready"
        assert client.delete(path, headers={"Origin": "http://127.0.0.1:5199", "Content-Type": "application/json"}).status_code == 409
        assert allocate(client, session).status_code == 409
        ws.send_bytes(b"\0" * 3200)
        assert ws.receive_json()["type"] == "partial"
        assert ws.receive_json()["type"] == "final"
        ws.send_json({"type": "finish"})
        assert ws.receive_json()["type"] == "finished"
