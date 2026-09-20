"""客户身份与历史报告入口。"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import APIResponse, success_response
from src.api.deps import get_db, get_settings, idempotency_key
from src.config.settings import Settings, settings
from src.db.models import IdempotencyRecord
from src.models.contracts import (
    BusinessError,
    CRMExtractInput,
    CRMExtractRead,
    CustomerCreate,
    CustomerPage,
    CustomerRead,
    CustomerUpdate,
    ReportPage,
)
from src.repositories.store import Store, digest
from src.services.customers import CustomerService
from src.services.sessions import SessionService

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post("/extract", response_model=APIResponse[CRMExtractRead])
async def extract(data: CRMExtractInput, request: Request,
                  key: str = Depends(idempotency_key), config: Settings = Depends(get_settings)):
    extractor = getattr(request.app.state, "crm_extractor", None)
    if extractor is None:
        raise BusinessError("CRM 自动提取尚未配置，可改为手动填写", "LLM_NOT_CONFIGURED", 503,
                            "DEPENDENCY_UNAVAILABLE")
    body = data.model_dump()
    # CRM 专用锁仅串行 CRM；外部模型等待期间不持有全局业务写锁。
    async with request.app.state.crm_lock:
        async with request.app.state.session_factory() as db:
            existing = await db.get(IdempotencyRecord, key)
            if existing:
                if existing.operation != "crm_extract" or existing.body_hash != digest(body):
                    raise BusinessError("同一请求标识不能用于不同内容", "IDEMPOTENCY_CONFLICT")
                return success_response(existing.response, message="ok",
                                        request_id=request.state.request_id)
        proposed = await extractor(data.text, config)
        async with request.app.state.write_lock:
            async with request.app.state.session_factory() as db:
                store = Store(db)
                async def action():
                    return await CustomerService(store, config).save_extraction(
                        proposed["proposed"], proposed.get("historical_facts", []))
                result = await store.idempotent(key, "crm_extract", body, action)
                # 校验放在提交之前，失败不留下无法回读的半成品预览。
                result = CRMExtractRead.model_validate(result).model_dump()
                await db.commit()
    return success_response(result, message="ok", request_id=request.state.request_id)


@router.get("", response_model=APIResponse[CustomerPage])
async def list_customers(request: Request, q: str | None = None, cursor: str | None = None,
                         limit: int = Query(settings.list_page_size, ge=1, le=settings.list_max_page_size),
                         db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await CustomerService(Store(db), config).list(q, cursor, limit),
                            message="ok", request_id=request.state.request_id)


@router.post("", status_code=201, response_model=APIResponse[CustomerRead])
async def create_customer(data: CustomerCreate, request: Request,
                          key: str = Depends(idempotency_key), db: AsyncSession = Depends(get_db),
                          config: Settings = Depends(get_settings)):
    store = Store(db)
    async def action():
        return await CustomerService(store, config).create(data)
    return success_response(await store.idempotent(key, "customer_create",
        data.model_dump(mode="json"), action), message="ok", request_id=request.state.request_id)


@router.patch("/{customer_id}", response_model=APIResponse[CustomerRead])
async def update_customer(customer_id: UUID, data: CustomerUpdate, request: Request,
                          db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await CustomerService(Store(db), config).update(str(customer_id), data),
                            message="ok", request_id=request.state.request_id)


@router.get("/{customer_id}/reports", response_model=APIResponse[ReportPage])
async def history(customer_id: UUID, request: Request, cursor: str | None = None,
                  limit: int = Query(settings.list_page_size, ge=1, le=settings.list_max_page_size),
                  db: AsyncSession = Depends(get_db), config: Settings = Depends(get_settings)):
    return success_response(await SessionService(Store(db), config).history(str(customer_id), cursor, limit),
                            message="ok", request_id=request.state.request_id)
