"""T007装配入口；不自动修改共享main，也不在导入时启动后台任务。"""
from contextlib import asynccontextmanager
from typing import Any


def install_agent(app: Any, *, provider: Any = None, registry: Any = None):
    from src.api.routes.runs import draft_editor
    from src.services.agent.crm import extract_crm
    from src.services.agent.runtime import AgentRunner

    manager = AgentRunner(app, provider=provider, registry=registry)
    app.state.agent_runner = manager
    app.state.draft_editor = draft_editor
    app.state.crm_extractor = extract_crm
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            try:
                yield state
            finally:
                await manager.close()

    app.router.lifespan_context = lifespan
    return manager
