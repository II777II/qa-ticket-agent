"""FastAPI application assembly and lifecycle."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.application.runtime import create_runtime
from backend.infrastructure.config import settings, setup_logging

logger = logging.getLogger("qa_ticket.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = create_runtime()
    logger.info("后端就绪: http://%s:%s/docs", settings.host, settings.port)
    try:
        yield
    finally:
        app.state.runtime.shutdown()
        app.state.runtime = None


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="电商智能助手 POC",
        description="自然语言提问 -> read / write / human 三路；read 内确定性调用知识库或订单工具。",
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
    app.include_router(router)
    if (settings.frontend_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")
    if settings.kb_root.is_dir():
        app.mount("/kb", StaticFiles(directory=settings.kb_root), name="kb")
    return app


app = create_app()
