"""百炼实时 ASR 事件适配；音频只流经有界内存，不写磁盘。"""

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import aiohttp
from src.adapters.base import ProviderError
from src.config.settings import Settings


class QwenASRConnection:
    def __init__(self, websocket, config: Settings):
        self.ws, self.config = websocket, config

    async def send(self, kind: str, **values):
        await self.ws.send_json({"event_id": str(uuid4()), "type": kind, **values})

    async def configure(self, language: str | None):
        session = {
            "input_audio_format": "pcm",
            "sample_rate": self.config.asr_sample_rate,
            "turn_detection": {
                "type": "server_vad",
                "threshold": self.config.asr_vad_threshold,
                "silence_duration_ms": self.config.asr_vad_silence_ms,
            },
        }
        if language:
            session["input_audio_transcription"] = {"language": language}
        await self.send("session.update", session=session)
        async with asyncio.timeout(self.config.asr_connect_timeout):
            while True:
                event = await self.receive()
                if event.get("type") == "session.updated":
                    return
                if event.get("type") == "error":
                    raise ProviderError("ASR_CONFIG_REJECTED", "实时语音配置未被接受")

    async def append(self, pcm: bytes):
        await self.send("input_audio_buffer.append", audio=base64.b64encode(pcm).decode("ascii"))

    async def finish(self):
        await self.send("session.finish")

    async def receive(self) -> dict:
        message = await self.ws.receive()
        if message.type != aiohttp.WSMsgType.TEXT:
            raise ProviderError("ASR_DISCONNECTED", "识别连接中断，已有文字已保留，请检查末句")
        try:
            event = json.loads(message.data)
            if not isinstance(event, dict):
                raise ValueError()
            return event
        except (ValueError, TypeError):
            raise ProviderError("ASR_INVALID_RESPONSE", "识别响应格式错误") from None


class BailianASRProvider:
    def __init__(self, config: Settings):
        self.config = config

    @asynccontextmanager
    async def connect(self, language: str | None):
        cfg = self.config
        if not cfg.bailian_api_key or not cfg.bailian_asr_ws_url:
            raise ProviderError("ASR_NOT_CONFIGURED", "实时语音服务未配置，可先输入文字")
        if urlsplit(cfg.bailian_asr_ws_url).scheme != "wss":
            raise ProviderError("ASR_URL_INVALID", "实时语音上游必须使用 WSS")
        separator = "&" if "?" in cfg.bailian_asr_ws_url else "?"
        url = cfg.bailian_asr_ws_url + separator + urlencode({"model": cfg.asr_model})
        try:
            async with aiohttp.ClientSession(
                trust_env=False,
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=cfg.asr_connect_timeout),
            ) as client:
                async with client.ws_connect(
                    url,
                    headers={"Authorization": f"Bearer {cfg.bailian_api_key}"},
                    max_msg_size=cfg.max_request_bytes,
                ) as websocket:
                    connection = QwenASRConnection(websocket, cfg)
                    await connection.configure(language)
                    yield connection
        except (aiohttp.ClientError, OSError):
            raise ProviderError("ASR_CONNECTION_ERROR", "实时语音连接失败") from None
        except TimeoutError:
            raise ProviderError("ASR_TIMEOUT", "实时语音连接或收尾超时，已有文字已保留") from None
