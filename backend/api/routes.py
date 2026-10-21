"""HTTP and SSE routes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import EventSourceResponse, FileResponse
from fastapi.sse import ServerSentEvent

from backend.api.schemas import ChatRequest, LlmConfigRequest, ServiceConfirmRequest
from backend.application.chat import ChatService
from backend.application.runtime import AgentRuntime
from backend.domain.core import ORDER_NO_RE, TicketCreate
from backend.infrastructure.config import LLM_MODELS, git_version, settings
from backend.infrastructure.llm import create_llm

logger = logging.getLogger("qa_ticket.api")
router = APIRouter()


def get_runtime(request: Request) -> AgentRuntime:
    return request.app.state.runtime


def get_chat(request: Request) -> ChatService:
    return ChatService(get_runtime(request))


async def stream_events(
    chat: ChatService,
    req: ChatRequest,
    requested_intent=None,
) -> AsyncIterator[ServerSentEvent]:
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
        f"/branch/{_intent}",
        _chat_endpoint(_intent),
        methods=["POST"],
        tags=["intent-branches"],
        response_class=EventSourceResponse,
    )


@router.post("/branch/service/confirm", tags=["service-actions"])
async def confirm_service(req: ServiceConfirmRequest, runtime: AgentRuntime = Depends(get_runtime)):
    if runtime.orders.get(req.order_no) is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {req.order_no}")
    record, duplicated = runtime.tickets.create(TicketCreate(
        title=f"{req.service_type}办理 · {req.order_no}",
        description=req.description,
        category=req.category,
        priority=req.priority,
        contact=req.contact,
    ))
    return {
        "ok": True,
        "ticket_id": record.id,
        "status": record.status,
        "duplicated": duplicated,
        "message": "已提交" if not duplicated else "已存在相同业务，复用原单",
    }


@router.get("/health", tags=["system"])
async def health(runtime: AgentRuntime = Depends(get_runtime)):
    info = runtime.describe()
    return {
        key: info[key]
        for key in ("provider", "mock", "checkpointer", "retriever", "ticket_store")
    } | {"status": "ok"}


@router.get("/api/agent-info", tags=["system"])
async def agent_info(runtime: AgentRuntime = Depends(get_runtime)):
    version = git_version()
    return runtime.describe() | {
        "status": "ok",
        "rag_top_k": settings.rag_top_k,
        "git_sha": version["sha"],
        "git_date": version["date"],
        "extensions": ["compose:docker/docker-compose.yml"],
    }


@router.post("/api/llm/config", tags=["system"])
async def configure_llm(req: LlmConfigRequest, runtime: AgentRuntime = Depends(get_runtime)):
    provider, model = req.provider, req.model.strip()
    key = req.api_key.get_secret_value().strip() if req.api_key else ""
    try:
        llm = create_llm(provider=provider, api_key=key, model=model, base_url=req.base_url.strip())
        if provider != "mock":
            await asyncio.to_thread(llm.invoke, "只回复 OK")
    except Exception as exc:
        logger.warning("LLM 配置验证失败: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="API Key 验证失败或模型不可用") from None
    runtime.configure_llm(llm, provider, model or LLM_MODELS.get(provider, "mock"))
    return runtime.describe()


@router.get("/api/orders", tags=["orders"])
async def orders(
    order_no: str = "",
    user_id: int | None = None,
    limit: int = 20,
    runtime: AgentRuntime = Depends(get_runtime),
):
    order_no = order_no.strip().upper()
    if order_no:
        if not ORDER_NO_RE.fullmatch(order_no):
            raise HTTPException(status_code=400, detail="订单号格式应为 SO + 12 位数字")
        record = runtime.orders.get(order_no)
        return [record] if record else []
    if user_id is None:
        raise HTTPException(status_code=400, detail="必须提供 user_id 或 order_no")
    return runtime.orders.search(user_id=user_id, limit=limit)


@router.get("/api/kb/categories", tags=["knowledge"])
async def categories(runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.knowledge.categories()


@router.get("/api/kb/articles", tags=["knowledge"])
async def articles(
    q: str = "",
    category: str = "",
    limit: int = 50,
    runtime: AgentRuntime = Depends(get_runtime),
):
    return runtime.knowledge.search(q=q, category=category, limit=limit)


@router.get("/api/kb/search", tags=["knowledge"])
async def kb_search(q: str, top_k: int = 5, runtime: AgentRuntime = Depends(get_runtime)):
    if runtime.retriever is None or not q.strip():
        return []
    documents = runtime.retriever.search(q, top_k=top_k)
    return [{
        "index": int(document.metadata.get("index", index)),
        "source": str(document.metadata.get("source", "")),
        "title": str(document.metadata.get("title", "")),
        "snippet": document.page_content.strip()[:200],
        "score": document.metadata.get("score"),
    } for index, document in enumerate(documents, 1)]


@router.get("/api/metrics/summary", tags=["metrics"])
async def metrics(days: int = 7, runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.metrics.summary(days=days)


@router.get("/api/evaluation/summary", tags=["metrics"])
async def evaluation(runtime: AgentRuntime = Depends(get_runtime)):
    return runtime.evaluate()


@router.get("/", tags=["system"])
async def root():
    index = settings.frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "name": "qa-ticket-agent",
        "docs": "/docs",
        "health": "/health",
        "chat": "POST /chat",
        "branches": {name: f"POST /branch/{name}" for name in ("read", "write", "human")},
    }
