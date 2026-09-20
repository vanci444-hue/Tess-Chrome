"""从 PyCore api/deps.py 模板扩展；本机 Demo 无账号认证。"""
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import Settings
from src.models.contracts import BusinessError


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def idempotency_key(value: UUID = Header(alias="Idempotency-Key")) -> str:
    return str(value)


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """单进程写入串行，计数/修订/报告卡片与幂等记录同事务提交。"""
    async def transaction():
        async with request.app.state.session_factory() as db:
            try:
                yield db
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
        async with request.app.state.write_lock:
            async for db in transaction():
                yield db
    else:
        async for db in transaction():
            yield db


def require_model(request: Request) -> None:
    config = get_settings(request)
    if not config.bailian_api_key or not config.bailian_base_url:
        raise BusinessError("尚未配置百炼模型，请先使用手动录入", "LLM_NOT_CONFIGURED", 503,
                            "DEPENDENCY_UNAVAILABLE")
