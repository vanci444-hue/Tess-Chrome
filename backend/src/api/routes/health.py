"""配置状态不等于供应商可用性，不发起付费探测。"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, get_settings
from src.config.settings import Settings
from src.models.contracts import BusinessError, HealthRead
from src.services.reports import advisor

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=APIResponse[HealthRead])
async def health(request: Request, db: AsyncSession = Depends(get_db),
                  config: Settings = Depends(get_settings)):
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise BusinessError("本机数据服务未就绪", "DATABASE_UNAVAILABLE", 503,
                            "DEPENDENCY_UNAVAILABLE") from error
    capabilities = {
        "llm": "configured" if config.bailian_api_key and config.bailian_base_url else "missing",
        "asr": "configured" if config.bailian_api_key and config.bailian_asr_ws_url else "missing",
        "maps": "configured" if config.amap_web_service_key else "missing"}
    return success_response({"demo_advisor": advisor(), "status": "ready" if all(
        state == "configured" for state in capabilities.values()) else "degraded",
        "database": True, "capabilities": capabilities}, message="ok", request_id=request.state.request_id)
