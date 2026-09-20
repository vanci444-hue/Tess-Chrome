"""分配及连接实时 ASR；HTTP 使用 PyCore，WebSocket 使用专用事件协议。"""

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Request, WebSocket
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, get_settings, idempotency_key
from src.config.settings import Settings
from src.db.models import ASRSession
from src.models.contracts import AudioCreate, AudioCreated, BusinessError
from src.repositories.store import Store
from src.services.asr import ASRService, expired, stream_audio

router = APIRouter(tags=["audio"])


@router.post(
    "/api/sessions/{session_id}/audio", status_code=201, response_model=APIResponse[AudioCreated]
)
async def create_audio(
    session_id: UUID,
    data: AudioCreate,
    request: Request,
    key: str = Depends(idempotency_key),
    db: AsyncSession = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    store = Store(db)

    async def action():
        return await ASRService(store, config).create(str(session_id), data)

    result = await store.idempotent(key, f"audio:{session_id}", data.model_dump(), action)
    row = await store.require(ASRSession, result["asr_session_id"], str(session_id))
    if row.state != "created" or expired(row, config):
        raise BusinessError("该录音连接已使用或失效，请显式开始新一段录音", "ASR_EXPIRED")
    return success_response(result, message="ok", request_id=request.state.request_id)


@router.delete("/api/sessions/{session_id}/audio/{asr_session_id}")
async def cancel_audio_reservation(
    session_id: UUID,
    asr_session_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    # get_db serializes this with the WS claim: an already connected recording cannot be stolen.
    result = await ASRService(Store(db), config).cancel_reservation(
        str(session_id), str(asr_session_id)
    )
    return success_response(result, message="ok", request_id=request.state.request_id)


@router.websocket("/ws/sessions/{session_id}/audio/{asr_session_id}")
async def audio_socket(websocket: WebSocket, session_id: str, asr_session_id: str):
    cfg = websocket.app.state.settings
    try:
        host = urlsplit("http://" + websocket.headers.get("host", "")).hostname
    except ValueError:
        host = None
    if host not in cfg.allowed_hosts or websocket.headers.get("origin") not in cfg.origins:
        await websocket.send_denial_response(JSONResponse({"code": "FORBIDDEN"}, status_code=403))
        return
    async with websocket.app.state.write_lock, websocket.app.state.session_factory() as db:
        row = await Store(db).get(ASRSession, asr_session_id)
        if not row or row.session_id != session_id:
            await websocket.send_denial_response(
                JSONResponse({"code": "ASR_NOT_FOUND"}, status_code=404)
            )
            return
        if row.state != "created" or expired(row, cfg):
            await websocket.send_denial_response(
                JSONResponse({"code": "ASR_EXPIRED"}, status_code=403)
            )
            return
        row.state = "connecting"
        language = row.language
        await db.commit()
    await websocket.accept()
    await stream_audio(websocket, session_id, asr_session_id, language)
