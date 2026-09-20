"""审核与固定发布；公开读取不重新查询当前客户信息。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, get_settings, idempotency_key
from src.config.settings import PROJECT_ROOT, Settings
from src.models.contracts import (
    DraftUpdate,
    DraftUpdated,
    PublishInput,
    PublishRead,
    ReportSnapshot,
)
from src.repositories.store import Store
from src.services.assets import AssetService
from src.services.reports import ReportService

router = APIRouter(tags=["reports"])


@router.patch("/api/sessions/{session_id}/drafts/{draft_id}", response_model=APIResponse[DraftUpdated])
async def update_draft(session_id: UUID, draft_id: UUID, data: DraftUpdate, request: Request,
                       db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    if data.change_request and getattr(request.app.state, "draft_editor", None):
        # T005 可注册异步受理函数；返回已持久化 run，避免模型同步阻塞请求。
        return await request.app.state.draft_editor(str(session_id), str(draft_id), data, request, db)
    return success_response(await ReportService(Store(db), config).update(str(session_id), str(draft_id), data),
                            message="ok", request_id=request.state.request_id)


@router.post("/api/sessions/{session_id}/reports", status_code=201, response_model=APIResponse[PublishRead])
async def publish(session_id: UUID, data: PublishInput, request: Request,
                   key: str = Depends(idempotency_key), db: AsyncSession = Depends(get_db),
                   config: Settings = Depends(get_settings)):
    store = Store(db)
    async def action():
        return await ReportService(store, config).publish(str(session_id), data)
    return success_response(await store.idempotent(key, f"publish:{session_id}",
        data.model_dump(mode="json"), action), message="ok", request_id=request.state.request_id)


@router.get("/api/reports/{report_id}", response_model=APIResponse[ReportSnapshot])
async def get_report(report_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
                     config: Settings = Depends(get_settings)):
    return success_response(await ReportService(Store(db), config).get(str(report_id)),
                            message="ok", request_id=request.state.request_id)


@router.get("/api/reports/{report_id}/assets/{asset_id}", response_class=FileResponse)
async def report_asset(report_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db),
                       config: Settings = Depends(get_settings)):
    path, mime, sha = await AssetService(Store(db), config).resolve(str(asset_id), report_id=str(report_id))
    return FileResponse(path, media_type=mime, headers={"ETag": f'"{sha}"'})


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_html(report_id: UUID, db: AsyncSession = Depends(get_db),
                      config: Settings = Depends(get_settings)):
    await ReportService(Store(db), config).get(str(report_id))
    index = PROJECT_ROOT / config.frontend_dist / "index.html"
    if index.is_file():
        return HTMLResponse(index.read_text())
    return HTMLResponse("<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<title>Tess Report</title><h1>报告已保存</h1>"
        "<p>完整报告界面尚未构建；已保存的数据可通过报告 API 读取。</p></html>")
