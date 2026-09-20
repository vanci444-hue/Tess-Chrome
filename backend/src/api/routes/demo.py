"""用户主动确认后清空本机演示记录；不读取或改写 API 配置。"""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import success_response
from src.api.deps import get_db
from src.db.models import ASRSession, Base, Run
from src.models.contracts import BusinessError

router = APIRouter(prefix="/api/demo", tags=["demo"])


class ResetRequest(BaseModel):
    confirmation: Literal["RESET_DEMO"]


@router.post("/reset")
async def reset_demo(body: ResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # 写锁和事务由 get_db 统一管理；有活跃任务时不删除其上下文。
    run = await db.scalar(select(Run.id).where(Run.status.in_(["queued", "running"])).limit(1))
    audio = await db.scalar(select(ASRSession.id).where(
        ASRSession.state.in_(["created", "connecting", "streaming", "finishing"])).limit(1))
    if run or audio or request.app.state.crm_lock.locked():
        raise BusinessError("请先结束正在进行的录音或生成任务，再刷新 Demo", "DEMO_BUSY", 409)
    # 按外键依赖倒序删除，失败时整笔回滚；保留表结构和配置文件。
    for table in reversed(Base.metadata.sorted_tables):
        await db.execute(delete(table))
    return success_response({"reset": True}, message="演示记录已清空",
                            request_id=request.state.request_id)
