"""显式意图分支路由：knowledge / query / service / logistics / fallback。"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import EventSourceResponse
from fastapi.sse import ServerSentEvent

from backend.api.deps import get_chat
from backend.api.schemas import ChatRequest
from backend.api.streaming import stream_events
from backend.application.chat import ChatService

router = APIRouter(prefix="/branch", tags=["intent-branches"])


@router.post("/knowledge", summary="知识库问答分支（SSE）", response_class=EventSourceResponse)
async def knowledge(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req, requested_intent="knowledge"):
        yield event


@router.post("/query", summary="订单查询分支（SSE）", response_class=EventSourceResponse)
async def query(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req, requested_intent="query"):
        yield event


@router.post("/service", summary="售后业务草稿分支（SSE）", response_class=EventSourceResponse)
async def service(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req, requested_intent="service"):
        yield event


@router.post("/logistics", summary="物流 Agent + Tools 分支（SSE）", response_class=EventSourceResponse)
async def logistics(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req, requested_intent="logistics"):
        yield event


@router.post("/fallback", summary="兜底分支（SSE）", response_class=EventSourceResponse)
async def fallback(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req, requested_intent="fallback"):
        yield event
