"""集中访问本地业务实体；调用者持有事务，不在仓储内部提交。"""
from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Artifact,
    Base,
    Draft,
    IdempotencyRecord,
    Session,
    TimelineMessage,
)
from src.models.contracts import BusinessError

T = TypeVar("T", bound=Base)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


class Store:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, model: type[T], entity_id: str) -> T | None:
        return await self.db.get(model, entity_id)

    async def require(self, model: type[T], entity_id: str,
                      session_id: str | None = None) -> T:
        entity = await self.get(model, entity_id)
        if entity is None or (session_id is not None and
                              getattr(entity, "session_id", None) != session_id):
            raise BusinessError("记录不存在或不属于当前会话", f"{model.__name__.upper()}_NOT_FOUND",
                                404, "NOT_FOUND")
        return entity

    async def add(self, entity: T) -> T:
        self.db.add(entity)
        await self.db.flush()
        return entity

    async def list(self, model: type[T], **filters: Any) -> list[T]:
        query = select(model).filter_by(**filters)
        if hasattr(model, "created_at"):
            query = query.order_by(getattr(model, "created_at"), getattr(model, "id"))
        return list((await self.db.scalars(query)).all())

    async def check_revision(self, session_id: str, expected: int) -> Session:
        session = await self.require(Session, session_id)
        if session.revision != expected:
            raise BusinessError("信息已更新，请刷新确认内容", "STALE_REVISION",
                                current_revision=session.revision)
        return session

    async def bump(self, session: Session) -> builtins.list[str]:
        """任何计算输入变化后失效旧结果；历史快照保持原文。"""
        session.revision += 1
        invalidated = []
        for artifact in await self.list(Artifact, session_id=session.id):
            if artifact.status != "stale":
                artifact.status = "stale"
                invalidated.append(artifact.id)
        for draft in await self.list(Draft, session_id=session.id):
            draft.stale = True
            draft.requires_review = True
        await self.db.flush()
        return invalidated

    async def timeline(self, session_id: str, message_type: str, role: str,
                       content: dict[str, Any], source_ref: dict[str, str] | None = None,
                       report_id: str | None = None) -> TimelineMessage:
        if source_ref is not None:
            for row in await self.list(TimelineMessage, session_id=session_id):
                if row.type == message_type and row.source_ref == source_ref:
                    return row
        seq = await self.db.scalar(select(func.max(TimelineMessage.seq)).where(
            TimelineMessage.session_id == session_id))
        return await self.add(TimelineMessage(session_id=session_id, seq=(seq or 0) + 1,
            type=message_type, role=role, content=content, source_ref=source_ref,
            report_id=report_id))

    async def idempotent(self, key: str, operation: str, body: dict[str, Any],
                         action: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
        body_hash = digest(body)
        existing = await self.db.get(IdempotencyRecord, key)
        if existing:
            if existing.operation != operation or existing.body_hash != body_hash:
                raise BusinessError("同一请求标识不能用于不同内容", "IDEMPOTENCY_CONFLICT")
            return existing.response
        result = await action()
        self.db.add(IdempotencyRecord(key=key, operation=operation, body_hash=body_hash,
                                     response=result))
        await self.db.flush()
        return result
