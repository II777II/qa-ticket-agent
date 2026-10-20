"""Agent 四路分支路由：显式进入 knowledge / query / service / fallback。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat
from backend.api.routes.chat import stream_response
from backend.api.schemas import ChatRequest
from backend.application.chat import ChatService

router = APIRouter(prefix="/branch", tags=["agent-routes"])


@router.post("/knowledge", summary="知识库问答分支（SSE）")
async def knowledge(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> StreamingResponse:
    return stream_response(chat_service, req, requested_intent="knowledge")


@router.post("/query", summary="订单查询分支（SSE）")
async def query(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> StreamingResponse:
    return stream_response(chat_service, req, requested_intent="query")


@router.post("/service", summary="售后业务草稿分支（SSE）")
async def service(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> StreamingResponse:
    return stream_response(chat_service, req, requested_intent="service")


@router.post("/fallback", summary="兜底分支（SSE）")
async def fallback(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> StreamingResponse:
    return stream_response(chat_service, req, requested_intent="fallback")
