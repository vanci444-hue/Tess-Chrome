"""PyCore 应用入口；只注册已存在的业务路由，扩展模块显式装配。"""
import asyncio
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from pycore.api import APIConfig, APIServer
from pycore.api.responses import error_response
from pycore.core import Logger, LoggerConfig, LogLevel, get_logger
from src.api.routes import customers, demo, health, reports, sessions
from src.config.settings import PROJECT_ROOT, Settings, settings
from src.db.session import close_db, create_database, init_db
from src.models.contracts import BusinessError

Logger.configure(LoggerConfig(level=LogLevel.INFO, app_name="tess-chrome", json_format=False))
logger = get_logger()


def failure(request: Request, message: str, code: str, status: int, **metadata: Any) -> JSONResponse:
    response, http_status = error_response(message, code, status,
        request_id=getattr(request.state, "request_id", None), **metadata)
    return JSONResponse(response.model_dump(mode="json"), status_code=http_status)


def create_app(config: Settings | None = None, extra_routers: Sequence[APIRouter] = ()):
    config = config or settings
    engine, session_factory = create_database(config)
    server = APIServer(APIConfig(title="Tess-Chrome 本机服务", version="1.0.0",
        host=config.host, port=config.port, debug=config.debug,
        cors_origins=config.origins, cors_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        cors_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"]))

    async def startup():
        await init_db(engine)

    async def shutdown():
        await close_db(engine)

    server.on_startup(startup)
    server.on_shutdown(shutdown)
    app = server.app
    # 底座 /health 是裸响应；本项目健康契约唯一入口为 /api/health。
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/health"]
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.write_lock = asyncio.Lock()
    app.state.crm_lock = asyncio.Lock()
    app.state.crm_extractor = None
    app.state.draft_editor = None

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        try:
            hostname = urlsplit("http://" + request.headers.get("host", "")).hostname
        except ValueError:
            hostname = None
        if hostname not in config.allowed_hosts:
            return failure(request, "仅允许本机访问", "FORBIDDEN", 403, reason="INVALID_HOST")
        origin = request.headers.get("origin")
        if origin is not None and origin not in config.origins:
            return failure(request, "此网页来源未获允许", "FORBIDDEN", 403, reason="INVALID_ORIGIN")
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            if not origin or origin not in config.origins:
                return failure(request, "写入需要已配置的插件或网页来源", "FORBIDDEN", 403,
                               reason="ORIGIN_REQUIRED")
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return failure(request, "请求必须使用 JSON", "VALIDATION_ERROR", 400,
                               reason="JSON_REQUIRED")
            body = await request.body()
            if len(body) > config.max_request_bytes:
                return failure(request, "提交内容过长", "VALIDATION_ERROR", 400,
                               reason="REQUEST_TOO_LARGE")
        try:
            response = await call_next(request)
        except Exception as error:
            # 仅记录异常类别，不写请求正文、密钥或完整第三方响应。
            logger.error("本机请求处理失败", error_type=type(error).__name__,
                         request_id=request.state.request_id)
            return failure(request, "本机服务处理失败，请重试", "INTERNAL_ERROR", 500)
        logger.info("本机请求处理完成", method=request.method, status=response.status_code,
                    request_id=request.state.request_id)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(BusinessError)
    async def business_error(request: Request, error: BusinessError):
        return failure(request, error.message, error.code, error.status, **error.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # 不返回 Pydantic 的 input，避免泄露 CRM 或联系方式。
        fields = [".".join(str(x) for x in issue["loc"]) for issue in error.errors()]
        return failure(request, "请求字段格式不正确，请检查后重试", "VALIDATION_ERROR", 400,
                       reason="INVALID_REQUEST", fields=fields)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException):
        return failure(request, "请求的资源不存在" if error.status_code == 404 else "请求无法处理",
                       "NOT_FOUND" if error.status_code == 404 else "VALIDATION_ERROR", error.status_code)

    for router in (customers.router, sessions.router, reports.router, health.router, demo.router, *extra_routers):
        server.include_router(router)
    static = PROJECT_ROOT / config.frontend_dist / "assets"
    if static.is_dir():
        app.mount("/assets", StaticFiles(directory=static), name="report-assets")
    return app


def create_demo_app(config: Settings | None = None, *, provider: Any = None, registry: Any = None):
    """正式装配唯一入口；测试可显式注入 Provider，生产始终使用真实 Adapter。"""
    from src.api.routes import audio, runs
    from src.services.agent import install_agent

    app = create_app(config, extra_routers=(runs.router, audio.router))
    install_agent(app, provider=provider, registry=registry)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/index.html", response_class=HTMLResponse, include_in_schema=False)
    async def workspace():
        index = PROJECT_ROOT / app.state.settings.frontend_dist / "index.html"
        if index.is_file():
            return HTMLResponse(index.read_text())
        return HTMLResponse("<html lang='zh-CN'><meta charset='utf-8'><p>请先运行 scripts/build-demo.sh 构建界面。</p></html>", status_code=503)

    return app


app = create_demo_app()
