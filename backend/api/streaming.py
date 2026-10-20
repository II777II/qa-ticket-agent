"""对话接口的 SSE 事件生成器，供统一入口与四个分支入口复用。"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi.sse import ServerSentEvent

from backend.api.schemas import ChatRequest
from backend.application.chat import ChatService
from backend.domain.intent import IntentName


async def stream_events(
    chat_service: ChatService,
    req: ChatRequest,
    requested_intent: IntentName | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """把应用事件转换为 FastAPI 路由层可识别的 ServerSentEvent。"""
    async for event, payload in chat_service.stream(
        req.message,
        req.thread_id,
        requested_intent=requested_intent,
    ):
        yield ServerSentEvent(event=event, data=payload)
