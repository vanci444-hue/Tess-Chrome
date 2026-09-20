"""从 PyCore DB 会话模板扩展；显式事务与隔离测试引擎。"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, inspect, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pycore.core import get_logger
from src.config.settings import Settings, settings
from src.db.models import ASRSession, Base, Run, utcnow

logger = get_logger()


def create_database(config: Settings):
    engine = create_async_engine(config.database_url, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_constraints(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine, async_sessionmaker(engine, class_=AsyncSession,
                                     expire_on_commit=False, autoflush=False)


engine, async_session_maker = create_database(settings)


async def init_db(target_engine: AsyncEngine = engine) -> None:
    async with target_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all 不修改旧表：仅在缺列时追加 nullable language，保留原记录。
        columns = await conn.run_sync(
            lambda connection: {column["name"] for column in inspect(connection).get_columns("asr_sessions")})
        if "language" not in columns:
            await conn.exec_driver_sql("ALTER TABLE asr_sessions ADD COLUMN language VARCHAR")
            logger.info("语音会话表已兼容新增语言字段")
        # 重启后的运行不自动重放外部调用，避免重复收费。
        await conn.execute(update(Run).where(Run.status.in_(["queued", "running"])).values(
            status="interrupted", finished_at=utcnow(),
            error={"code": "PROCESS_RESTARTED", "message": "服务已重启，请明确重新开始"}))
        # 进程重启后原实时连接已不存在；仅关闭未终结记录，不重放或重连音频。
        await conn.execute(update(ASRSession).where(ASRSession.state.in_(
            ["created", "connecting", "streaming", "finishing"])).values(
                state="failed", error_code="ASR_INTERRUPTED", finished_at=utcnow()))
    logger.info("本地数据库初始化完成")


async def close_db(target_engine: AsyncEngine = engine) -> None:
    await target_engine.dispose()
    logger.info("本地数据库连接已关闭")


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
