"""外部合同采用隔离 HTTP 替身；不声称真实供应商已联调。"""

import json

import httpx
import pytest
from src.adapters.amap import AmapProvider, search_link
from src.adapters.base import ProviderError
from src.adapters.llm import BailianLLMProvider
from src.config.settings import Settings


async def test_missing_configuration_never_generates_mock_success():
    with pytest.raises(ProviderError, match="未配置"):
        await BailianLLMProvider(Settings()).complete([])
    with pytest.raises(ProviderError, match="未配置"):
        await AmapProvider(Settings()).search_region("望京", "北京")


async def test_llm_exact_model_standard_tool_calls_no_retry():
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.7-plus",
                "id": "r1",
                "usage": {"total_tokens": 10},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "calculate_energy", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
            },
        )

    provider = BailianLLMProvider(
        Settings(bailian_api_key="test", bailian_base_url="https://example.test/v1"),
        httpx.MockTransport(handle),
    )
    result = await provider.complete(
        [{"role": "user", "content": "test"}], [{"type": "function", "function": {}}]
    )
    assert result["tool_calls"][0]["id"] == "c1"
    assert calls[0]["model"] == "qwen3.7-plus" and calls[0]["stream"] is False
    assert len(calls) == 1 and provider.last_response_metadata["id"] == "r1"


async def test_map_relevance_filter_distance_numeric_dedup_and_image_error():
    def handle(request):
        path = request.url.path
        if path.endswith("around"):
            return httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {
                            "id": "store",
                            "name": "Tesla体验店",
                            "type": "汽车销售",
                            "distance": "1",
                            "location": "116.4,40",
                        },
                        {
                            "id": "far",
                            "name": "特斯拉超级充电站",
                            "distance": "1000",
                            "location": "116.41,40",
                        },
                        {
                            "id": "near",
                            "name": "Tesla充电站",
                            "distance": "200",
                            "location": "116.42,40",
                        },
                        {
                            "id": "out",
                            "name": "Tesla充电站",
                            "distance": "6000",
                            "location": "116.42,40",
                        },
                    ],
                },
            )
        return httpx.Response(200, json={"status": "0", "info": "bad key"})

    provider = AmapProvider(Settings(amap_web_service_key="test"), httpx.MockTransport(handle))
    stations = await provider.stations({"longitude": 116.4, "latitude": 40}, 5000)
    assert [s["id"] for s in stations] == ["near", "far"]
    assert [s["number"] for s in stations] == [1, 2]
    with pytest.raises(ProviderError, match="图片"):
        await provider.static_map({"longitude": 116.4, "latitude": 40}, stations)
    link = search_link("望京地铁站", "北京")["url"]
    assert "key=" not in link and "center=" not in link and "callnative=0" in link
    with pytest.raises(ProviderError):
        search_link("13800000000", "北京")


async def test_map_same_name_keeps_all_candidates_and_gcj_coordinates():
    def handle(request):
        return httpx.Response(
            200,
            json={
                "status": "1",
                "pois": [
                    {
                        "id": "a",
                        "name": "望京",
                        "cityname": "北京",
                        "location": "116.4,40",
                        "address": "区域A",
                    },
                    {
                        "id": "b",
                        "name": "望京",
                        "cityname": "北京",
                        "location": "116.5,40.1",
                        "address": "区域B",
                    },
                ],
            },
        )

    p = AmapProvider(Settings(amap_web_service_key="test"), httpx.MockTransport(handle))
    candidates = await p.search_region("望京", "北京")
    assert len(candidates) == 2 and candidates[0]["center_gcj02"]["longitude"] == 116.4


async def test_httpx_info_log_redacts_query_key(caplog):
    import logging

    marker = "synthetic-test-marker-for-log-check"

    def handle(request):
        return httpx.Response(200, json={"status": "1", "pois": []})

    provider = AmapProvider(Settings(amap_web_service_key=marker), httpx.MockTransport(handle))
    with caplog.at_level(logging.INFO, logger="httpx"):
        await provider.search_region("望京", "北京")
    assert caplog.records and marker not in caplog.text
    assert "[REDACTED]" in caplog.text
