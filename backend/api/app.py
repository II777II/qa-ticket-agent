"""FastAPI 应用组装。

只做「把应用拼起来」这几件事：生命周期、中间件、路由注册、可选的前端静态托管。
具体路由在 api/routes/，请求响应模型在 api/schemas.py，业务在 application/——
所以这个文件应当长期保持在这个体量。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import dialogue as dialogue_routes
from backend.api.routes import knowledge as knowledge_routes
from backend.api.routes import metrics as metrics_routes
from backend.api.routes import orders as order_routes
from backend.api.routes import system as system_routes
from backend.application.runtime import create_runtime
from backend.infrastructure.config import settings
from backend.infrastructure.logging import setup_logging

logger = logging.getLogger("qa_ticket.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = create_runtime()
    app.state.runtime = runtime
    logger.info("后端就绪: http://%s:%s/docs", settings.host, settings.port)
    try:
        yield
    finally:
        runtime.shutdown()
        app.state.runtime = None


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title="电商智能助手 POC",
        description="自然语言提问 -> LLM 意图识别 -> 知识库 / 订单 / 售后 / 物流 / 兜底五路。",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system_routes.router)
    app.include_router(dialogue_routes.router)
    app.include_router(order_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(metrics_routes.router)

    # 前端构建产物存在时挂上静态资源（首页由 system 路由返回 index.html）；API 路由不受影响
    assets_dir = settings.frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # 知识库 HTML 页面：/kb/index.html 与 /kb/pages/KB-EC-0001.html
    if settings.kb_root.is_dir():
        app.mount("/kb", StaticFiles(directory=settings.kb_root), name="kb")

    return app


app = create_app()
