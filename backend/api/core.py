"""FastAPI application, schemas, routes and SSE encoding."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import EventSourceResponse, FileResponse
from fastapi.sse import ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.application.core import AgentRuntime, ChatService, create_runtime
from backend.domain.core import ServiceType, TicketCategory, TicketCreate, TicketPriority
from backend.infrastructure.core import git_version, settings, setup_logging

logger = logging.getLogger("qa_ticket.api")
router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = "default"


class ServiceConfirmRequest(BaseModel):
    order_no: str = Field(pattern=r"^SO\d{12}$")
    contact: str = Field(min_length=2, max_length=120)
    service_type: ServiceType
    category: TicketCategory
    priority: TicketPriority = "中"
    description: str = Field(min_length=10, max_length=2000)


def get_runtime(request: Request) -> AgentRuntime:
    return request.app.state.runtime


def get_chat(request: Request) -> ChatService:
    return ChatService(get_runtime(request))


async def stream_events(chat: ChatService, req: ChatRequest, requested_intent=None) -> AsyncIterator[ServerSentEvent]:
    try:
        async for event, payload in chat.stream(req.message, req.thread_id, requested_intent=requested_intent):
            yield ServerSentEvent(event=event, raw_data=json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logger.exception("SSE 事件流异常")
        data = {"type": exc.__class__.__name__, "message": str(exc) or "流式响应异常"}
        yield ServerSentEvent(event="error", raw_data=json.dumps(data, ensure_ascii=False))


def _chat_endpoint(intent=None):
    async def endpoint(req: ChatRequest, chat: ChatService = Depends(get_chat)):
        async for event in stream_events(chat, req, intent):
            yield event
    return endpoint


router.add_api_route("/chat", _chat_endpoint(), methods=["POST"], tags=["chat"], response_class=EventSourceResponse)
for _intent in ("read", "write", "human"):
    router.add_api_route(
        f"/branch/{_intent}", _chat_endpoint(_intent), methods=["POST"],
        tags=["intent-branches"], response_class=EventSourceResponse,
    )


@router.post("/branch/service/confirm", tags=["service-actions"])
async def confirm_service(req: ServiceConfirmRequest, runtime: AgentRuntime = Depends(get_runtime)):
    if runtime.orders.get(req.order_no) is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {req.order_no}")
    record, duplicated = runtime.tickets.create(TicketCreate(
        title=f"{req.service_type}办理 · {req.order_no}",
        description=req.description, category=req.category, priority=req.priority, contact=req.contact,
    ))
    return {
        "ok": True, "ticket_id": record.id, "status": record.status, "duplicated": duplicated,
        "message": "已提交" if not duplicated else "已存在相同业务，复用原单",
    }


@router.get("/health", tags=["system"])
async def health(runtime: AgentRuntime = Depends(get_runtime)):
    info = runtime.describe()
    return {key: info[key] for key in ("provider", "mock", "checkpointer", "retriever", "ticket_store")} | {"status": "ok"}


@router.get("/api/agent-info", tags=["system"])
async def agent_info(runtime: AgentRuntime = Depends(get_runtime)):
    version = git_version()
    return runtime.describe() | {
        "status": "ok", "rag_top_k": settings.rag_top_k, "git_sha": version["sha"],
        "git_date": version["date"], "extensions": ["compose:docker/docker-compose.yml"],
    }


@router.get("/api/orders", tags=["orders"])
async def orders(q: str = "", status: int | None = None, user_id: int | None = None,
                 limit: int = 20, runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.orders.search(q=q, status=status, user_id=user_id, limit=limit)


@router.get("/api/kb/categories", tags=["knowledge"])
async def categories(runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.knowledge.categories()


@router.get("/api/kb/articles", tags=["knowledge"])
async def articles(q: str = "", category: str = "", limit: int = 50,
                   runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.knowledge.search(q=q, category=category, limit=limit)


@router.get("/api/kb/search", tags=["knowledge"])
async def kb_search(q: str, top_k: int = 5, runtime: AgentRuntime = Depends(get_runtime)):
    if runtime.retriever is None or not q.strip():
        return []
    documents = runtime.retriever.search(q, top_k=top_k)
    return [{
        "index": int(d.metadata.get("index", i)), "source": str(d.metadata.get("source", "")),
        "title": str(d.metadata.get("title", "")), "snippet": d.page_content.strip()[:200],
        "score": d.metadata.get("score"),
    } for i, d in enumerate(documents, 1)]


@router.get("/api/metrics/summary", tags=["metrics"])
async def metrics(days: int = 7, runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.metrics.summary(days=days)


@router.get("/", tags=["system"])
async def root():
    index = settings.frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "name": "qa-ticket-agent", "docs": "/docs", "health": "/health", "chat": "POST /chat",
        "branches": {x: f"POST /branch/{x}" for x in ("read", "write", "human")},
    }


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
        version="0.1.0", lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    app.include_router(router)
    if (settings.frontend_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")
    if settings.kb_root.is_dir():
        app.mount("/kb", StaticFiles(directory=settings.kb_root), name="kb")
    return app


app = create_app()
