"""本次会话、不可变候选及事实确认。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, get_settings, idempotency_key
from src.config.settings import Settings, settings
from src.models.contracts import (
    CaptureCreate,
    CaptureSaved,
    CaptureUpdate,
    CaptureUpdated,
    ContextUpdate,
    ContextUpdated,
    EventInject,
    EventInjected,
    SessionCreate,
    SessionDetail,
    SessionPage,
    SessionRead,
)
from src.repositories.store import Store
from src.services.assets import AssetService
from src.services.captures import CaptureService
from src.services.events import EventService
from src.services.facts import FactService
from src.services.sessions import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", status_code=201, response_model=APIResponse[SessionRead])
async def create_session(data: SessionCreate, request: Request,
                         key: str = Depends(idempotency_key), db: AsyncSession = Depends(get_db),
                         config: Settings = Depends(get_settings)):
    store = Store(db)
    async def action():
        return await SessionService(store, config).create(data)
    return success_response(await store.idempotent(key, "session_create", data.model_dump(mode="json"), action),
                            message="ok", request_id=request.state.request_id)


@router.get("", response_model=APIResponse[SessionPage])
async def list_sessions(customer_id: UUID, request: Request, cursor: str | None = None,
                        limit: int = Query(settings.list_page_size, ge=1, le=settings.list_max_page_size),
                        db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await SessionService(Store(db), config).list(str(customer_id), cursor, limit),
                            message="ok", request_id=request.state.request_id)


@router.get("/{session_id}", response_model=APIResponse[SessionDetail])
async def detail(session_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
                 config: Settings = Depends(get_settings)):
    return success_response(await SessionService(Store(db), config).detail(str(session_id)),
                            message="ok", request_id=request.state.request_id)


@router.post("/{session_id}/captures", status_code=201, response_model=APIResponse[CaptureSaved])
async def capture(session_id: UUID, data: CaptureCreate, request: Request,
                  key: str = Depends(idempotency_key), db: AsyncSession = Depends(get_db),
                  config: Settings = Depends(get_settings)):
    store = Store(db)
    async def action():
        return await CaptureService(store, config).create(str(session_id), data)
    return success_response(await store.idempotent(key, f"capture:{session_id}",
        data.model_dump(mode="json"), action), message="ok", request_id=request.state.request_id)


@router.patch("/{session_id}/captures/{capture_id}", response_model=APIResponse[CaptureUpdated])
async def update_capture(session_id: UUID, capture_id: UUID, data: CaptureUpdate, request: Request,
                         db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await CaptureService(Store(db), config).update(str(session_id), str(capture_id), data),
                            message="ok", request_id=request.state.request_id)


@router.patch("/{session_id}/context", response_model=APIResponse[ContextUpdated])
async def update_context(session_id: UUID, data: ContextUpdate, request: Request,
                         db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await FactService(Store(db), config).update(str(session_id), data),
                            message="ok", request_id=request.state.request_id)


@router.post("/{session_id}/events", response_model=APIResponse[EventInjected])
async def inject_events(session_id: UUID, data: EventInject, request: Request,
                        key: str = Depends(idempotency_key), db: AsyncSession = Depends(get_db),
                        config: Settings = Depends(get_settings)):
    store = Store(db)
    async def action():
        return await EventService(store, config).inject(str(session_id), data)
    return success_response(await store.idempotent(key, f"events:{session_id}", data.model_dump(), action),
                            message="ok", request_id=request.state.request_id)


@router.get("/{session_id}/assets/{asset_id}", response_class=FileResponse)
async def session_asset(session_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db),
                        config: Settings = Depends(get_settings)):
    path, mime, sha = await AssetService(Store(db), config).resolve(str(asset_id), session_id=str(session_id))
    return FileResponse(path, media_type=mime, headers={"ETag": f'"{sha}"'})
