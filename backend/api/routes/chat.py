"""统一对话入口：自动识别意图并进入五路之一。"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import EventSourceResponse
from fastapi.sse import ServerSentEvent

from backend.api.deps import get_chat
from backend.api.schemas import ChatRequest
from backend.api.streaming import stream_events
from backend.application.chat import ChatService

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    summary="流式对话（SSE，自动识别五路意图）",
    response_class=EventSourceResponse,
)
async def chat(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> AsyncIterator[ServerSentEvent]:
    async for event in stream_events(chat_service, req):
        yield event
