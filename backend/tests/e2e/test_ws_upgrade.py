"""官方 uvicorn 握手升级；隔离端口与临时库，不连接生产 8099。"""

import socket
import threading
import time
from uuid import uuid4

import httpx
import pytest
import uvicorn
from src.config.settings import Settings
from src.main import create_demo_app

ORIGIN = "http://127.0.0.1:5199"


class FakeUpstream:
    def __init__(self):
        self.queue = __import__("asyncio").Queue()

    async def append(self, pcm):
        return None

    async def finish(self):
        await self.queue.put({"type": "session.finished"})

    async def receive(self):
        return await self.queue.get()


class FakeProvider:
    def connect(self, language):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _inner():
            yield FakeUpstream()

        return _inner()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if port == 8099:
        return _free_port()
    return port


def test_official_uvicorn_websocket_upgrade(tmp_path):
    websockets = pytest.importorskip("websockets")
    port = _free_port()
    assert port != 8099
    config = Settings(
        database_path=str(tmp_path / "ws-qa.db"),
        upload_dir=str(tmp_path / "uploads"),
        bailian_api_key="test",
        bailian_asr_ws_url="wss://example.test/asr",
        report_origin=f"http://127.0.0.1:{port}",
        host="127.0.0.1",
        port=port,
    )
    app = create_demo_app(config)
    app.state.asr_provider = FakeProvider()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(80):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, "隔离 uvicorn 未就绪"
        origin = {"Origin": ORIGIN}
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
            customer = client.post(
                "/api/customers",
                json={"nickname": "QA", "email": "qa@example.com", "identity_confirmed": True},
                headers={**origin, "Idempotency-Key": str(uuid4())},
            )
            assert customer.status_code == 201, customer.text
            session = client.post(
                "/api/sessions",
                json={"customer_id": customer.json()["data"]["id"], "title": "WS"},
                headers={**origin, "Idempotency-Key": str(uuid4())},
            )
            assert session.status_code == 201, session.text
            sid = session.json()["data"]["id"]
            audio = client.post(
                f"/api/sessions/{sid}/audio",
                json={"expected_revision": 1},
                headers={**origin, "Idempotency-Key": str(uuid4())},
            )
            assert audio.status_code == 201, audio.text
            path = audio.json()["data"]["ws_path"]
        import asyncio

        async def handshake():
            async with websockets.connect(
                f"ws://127.0.0.1:{port}{path}",
                additional_headers={"Origin": ORIGIN, "Host": f"127.0.0.1:{port}"},
                open_timeout=5,
            ) as ws:
                first = await asyncio.wait_for(ws.recv(), timeout=5)
                return first

        first = asyncio.run(handshake())
        assert "Invalid response status" not in str(first)
        assert first
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        assert port != 8099
