"""ASR 分配与双向流状态机。终态仅更新 ASRSession，绝不提交业务文字。"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime

import anyio
from fastapi import WebSocket, WebSocketDisconnect
from src.adapters.asr import BailianASRProvider
from src.adapters.base import ProviderError
from src.config.settings import Settings
from src.db.models import ASRSession, utcnow
from src.models.contracts import AudioCreate, BusinessError
from src.repositories.store import Store


def expired(row: ASRSession, config: Settings) -> bool:
    return (
        datetime.now(UTC) - datetime.fromisoformat(row.created_at)
    ).total_seconds() >= config.asr_connect_ttl_seconds


class ASRService:
    def __init__(self, store: Store, config: Settings):
        self.store, self.config = store, config

    async def cancel_reservation(self, session_id: str, asr_id: str) -> dict:
        """Only a never-connected reservation is cancellable over HTTP; live streams own their WS."""
        row = await self.store.require(ASRSession, asr_id, session_id)
        if row.state == "created":
            row.state, row.error_code, row.finished_at = (
                "discarded", "ASR_CLIENT_CANCELLED", utcnow()
            )
        elif row.state in {"connecting", "streaming", "finishing"}:
            raise BusinessError("录音已连接，请在原录音窗口停止", "AUDIO_ACTIVE")
        return {"asr_session_id": row.id, "state": row.state}

    async def create(self, session_id: str, data: AudioCreate) -> dict:
        cfg = self.config
        if not cfg.bailian_api_key or not cfg.bailian_asr_ws_url:
            raise BusinessError(
                "实时语音服务未配置，可先输入文字",
                "ASR_NOT_CONFIGURED",
                503,
                "DEPENDENCY_UNAVAILABLE",
            )
        await self.store.check_revision(session_id, data.expected_revision)
        for row in await self.store.list(ASRSession, session_id=session_id):
            if row.state == "created" and expired(row, cfg):
                row.state, row.error_code, row.finished_at = "failed", "ASR_EXPIRED", utcnow()
            elif row.state in {"created", "connecting", "streaming", "finishing"}:
                raise BusinessError("当前会话已有录音，请结束后重试", "AUDIO_ACTIVE")
        row = await self.store.add(
            ASRSession(session_id=session_id, state="created", language=data.language)
        )
        return {
            "asr_session_id": row.id,
            "session_id": session_id,
            "ws_path": f"/ws/sessions/{session_id}/audio/{row.id}",
            "state": "created",
            "expires_in_seconds": cfg.asr_connect_ttl_seconds,
        }


async def stream_audio(
    websocket: WebSocket, session_id: str, asr_id: str, language: str | None = None
):
    app, cfg = websocket.app, websocket.app.state.settings
    seq = 0
    started = time.monotonic()
    terminal = "failed"
    terminal_code: str | None = "ASR_DISCONNECTED"
    provider = getattr(app.state, "asr_provider", None) or BailianASRProvider(cfg)

    async def update(state: str, error_code: str | None = None):
        async with app.state.write_lock, app.state.session_factory() as db:
            row = await Store(db).require(ASRSession, asr_id, session_id)
            row.state = state
            row.error_code = error_code
            if state in {"finished", "failed", "discarded"}:
                row.finished_at, row.duration_seconds = utcnow(), time.monotonic() - started
            await db.commit()

    async def emit(kind: str, **values):
        nonlocal seq
        seq += 1
        await websocket.send_json({"type": kind, "asr_session_id": asr_id, "seq": seq, **values})

    tasks: list[asyncio.Task] = []
    try:
        async with provider.connect(language) as upstream:
            await update("streaming")
            await emit("ready")
            bytes_limit = cfg.asr_sample_rate * 2 * cfg.asr_buffer_seconds
            chunk_limit = cfg.asr_sample_rate * 2 * cfg.asr_chunk_ms // 1000
            audio: asyncio.Queue = asyncio.Queue(maxsize=max(1, bytes_limit // max(1, chunk_limit)))
            buffered = 0
            finishing = asyncio.Event()
            finished = asyncio.Event()
            finish_requested = asyncio.Event()
            final_items: set[str] = set()
            last_preview: dict[str, tuple[str, str]] = {}

            async def receive_client():
                nonlocal buffered, terminal
                while True:
                    event = await websocket.receive()
                    if event["type"] == "websocket.disconnect":
                        raise WebSocketDisconnect(event.get("code", 1000))
                    if event.get("bytes") is not None:
                        pcm = event["bytes"]
                        if (
                            finishing.is_set()
                            or finish_requested.is_set()
                            or not pcm
                            or len(pcm) % 2
                            or len(pcm) > chunk_limit
                        ):
                            raise ProviderError(
                                "ASR_PROTOCOL_ERROR", "音频格式或发送状态不符合 PCM16 协议"
                            )
                        if buffered + len(pcm) > bytes_limit or audio.full():
                            raise ProviderError(
                                "ASR_BACKPRESSURE", "音频缓冲已满，停止识别，请检查末句"
                            )
                        buffered += len(pcm)
                        audio.put_nowait(pcm)
                    else:
                        text = event.get("text", "")
                        if len(text.encode()) > cfg.max_request_bytes:
                            raise ProviderError("ASR_PROTOCOL_ERROR", "控制消息过长")
                        try:
                            control = json.loads(text)
                        except (ValueError, TypeError):
                            raise ProviderError(
                                "ASR_PROTOCOL_ERROR", "无法识别录音控制消息"
                            ) from None
                        if not isinstance(control, dict) or set(control) != {"type"}:
                            raise ProviderError("ASR_PROTOCOL_ERROR", "无法识别录音控制消息")
                        if control["type"] == "discard":
                            terminal = "discarded"
                            finished.set()
                            return
                        if control["type"] == "finish":
                            # 正常收尾和时长保护可能同时到达，finish 是幂等控制。
                            finish_requested.set()
                        else:
                            raise ProviderError("ASR_PROTOCOL_ERROR", "重复或未知录音控制消息")

            async def send_audio():
                nonlocal buffered
                while not finishing.is_set():
                    if finish_requested.is_set() and audio.empty():
                        finishing.set()
                        await update("finishing")
                        await asyncio.wait_for(upstream.finish(), cfg.asr_finish_timeout)
                        return
                    try:
                        pcm = await asyncio.wait_for(audio.get(), cfg.asr_chunk_ms / 1000)
                    except TimeoutError:
                        continue
                    try:
                        await asyncio.wait_for(upstream.append(pcm), cfg.asr_buffer_seconds)
                    except TimeoutError:
                        raise ProviderError(
                            "ASR_BACKPRESSURE", "上游处理过慢，请检查末句"
                        ) from None
                    finally:
                        buffered -= len(pcm)

            async def receive_upstream():
                nonlocal terminal
                while True:
                    event = await upstream.receive()
                    kind = event.get("type")
                    item_id = event.get("item_id")
                    if kind == "conversation.item.input_audio_transcription.text":
                        if not isinstance(item_id, str) or item_id in final_items:
                            continue
                        text, stash = event.get("text", ""), event.get("stash", "")
                        if not isinstance(text, str) or not isinstance(stash, str):
                            raise ProviderError("ASR_INVALID_RESPONSE", "识别字幕格式错误")
                        if last_preview.get(item_id) != (text, stash):
                            last_preview[item_id] = (text, stash)
                            await emit("partial", item_id=item_id, text=text, stash=stash)
                    elif kind == "conversation.item.input_audio_transcription.completed":
                        if not isinstance(item_id, str) or item_id in final_items:
                            continue
                        transcript = event.get("transcript")
                        if not isinstance(transcript, str):
                            raise ProviderError("ASR_INVALID_RESPONSE", "识别完成事件格式错误")
                        final_items.add(item_id)
                        last_preview.pop(item_id, None)
                        await emit("final", item_id=item_id, transcript=transcript)
                    elif kind == "session.finished":
                        if not finishing.is_set():
                            raise ProviderError("ASR_DISCONNECTED", "识别提前结束，请检查末句")
                        terminal = "finished"
                        await update("finished")
                        await emit("finished", complete=True)
                        finished.set()
                        return
                    elif kind in {"error", "conversation.item.input_audio_transcription.failed"}:
                        raise ProviderError(
                            "ASR_TRANSCRIPTION_FAILED", "实时识别失败，已有文字已保留"
                        )
                    # 300 秒范围内仍约束条目数，避免供应商异常无界累积。
                    if len(final_items) + len(last_preview) > cfg.max_text_chars:
                        raise ProviderError("ASR_EVENT_LIMIT", "识别事件超过上限，已有文字已保留")

            async def limits():
                try:
                    await asyncio.wait_for(finish_requested.wait(), cfg.asr_session_max_seconds)
                except TimeoutError:
                    await emit(
                        "error",
                        code="ASR_DURATION_LIMIT",
                        message="本段已达时长上限，正在保留文字；需要时可继续录制",
                        incomplete=False,
                    )
                    # 给客户端停采音及在途 PCM 一个有界窗口，之后才提交上游 finish。
                    try:
                        await asyncio.wait_for(finish_requested.wait(), cfg.asr_buffer_seconds)
                    except TimeoutError:
                        finish_requested.set()
                await asyncio.wait_for(
                    finishing.wait(), cfg.asr_finish_timeout + cfg.asr_buffer_seconds
                )
                await asyncio.wait_for(finished.wait(), cfg.asr_finish_timeout)

            tasks = [
                asyncio.create_task(fn())
                for fn in (receive_client, send_audio, receive_upstream, limits)
            ]
            done_wait = asyncio.create_task(finished.wait())
            tasks.append(done_wait)
            active = set(tasks)
            while not finished.is_set():
                done, active = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            terminal_code = None
    except WebSocketDisconnect:
        terminal, terminal_code = "discarded", "ASR_CLIENT_DISCONNECTED"
    except (ProviderError, TimeoutError) as error:
        terminal = "failed"
        terminal_code = error.code if isinstance(error, ProviderError) else "ASR_FINISH_TIMEOUT"
        try:
            await emit(
                "error",
                code=terminal_code,
                message=error.message
                if isinstance(error, ProviderError)
                else "识别收尾超时，已有文字已保留，请检查末句",
                incomplete=True,
            )
        except (WebSocketDisconnect, RuntimeError):
            pass
    finally:
        with anyio.CancelScope(shield=True):
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await update(terminal, terminal_code)
            try:
                code = (
                    1000
                    if terminal in {"finished", "discarded"}
                    else (1008 if terminal_code == "ASR_PROTOCOL_ERROR" else 1011)
                )
                await websocket.close(code=code)
            except (RuntimeError, WebSocketDisconnect):
                pass
