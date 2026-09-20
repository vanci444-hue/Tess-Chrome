"""用户主动确认后清空本机演示记录；不读取或改写 API 配置。"""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from pycore.api.responses import success_response
from src.api.deps import get_db, get_settings
from src.config.settings import Settings
from src.db.models import ASRSession, Base, Capture, Run, Session
from src.models.contracts import BusinessError
from src.repositories.store import Store
from src.services.reports import ReportService

router = APIRouter(prefix="/api/demo", tags=["demo"])

# 场景 6 路径 B：客户离场后已补 Decision Context，生成时不再追问销售。
DEMO_REPORT_SUMMARY = {
    "comparing": "Option 1 白色长续航，与 Option 2 对照方案——今天讨论的两套 Model Y 候选",
    "confirmed": [
        "关注：白色长续航与座舱空间；月供与家充不确定性；接送便利优先",
        "已解决：金融方案已对照候选讲清；超充中后段掉功率已解释并获理解",
        "权衡：保长续航则月供更紧；预算紧时可用后驱换空间，但会牺牲续航偏好",
        "Must-have：白色与当前轮毂意向；可妥协：后驱 vs 长续航仍可谈",
    ],
    "pending": [
        "小区装桩可行性仍待核实（勿写死）",
        "与家人最终拍板",
    ],
}


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


@router.post("/sessions/{session_id}/prepare-report")
async def demo_prepare_report(
    session_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    config: Settings = Depends(get_settings),
):
    """演示专用：按场景 6 完成态摘要直接落草稿，不走模型、不追问销售。"""
    store = Store(db)
    session = await store.require(Session, str(session_id))
    active = await store.list(Capture, session_id=str(session_id), active=True)
    if not active:
        raise BusinessError("至少需要一个候选方案才能生成报告", "NO_CAPTURE", 400)
    draft = await ReportService(store, config).save_draft(
        str(session_id), session.revision, summary=DEMO_REPORT_SUMMARY
    )
    return success_response(
        draft,
        message="演示报告草稿已就绪",
        request_id=request.state.request_id,
    )
