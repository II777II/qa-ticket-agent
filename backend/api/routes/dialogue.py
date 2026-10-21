"""对话路由：自动分类入口与五路显式意图分支。"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import EventSourceResponse
from fastapi.sse import ServerSentEvent

from backend.api.deps import get_chat
from backend.api.schemas import ChatRequest
from backend.api.streaming import stream_events
from backend.application.chat import ChatService
from backend.domain.intent import IntentName

router = APIRouter()


def _endpoint(intent: IntentName | None):
    async def endpoint(
        req: ChatRequest,
        chat_service: ChatService = Depends(get_chat),
    ) -> AsyncIterator[ServerSentEvent]:
        async for event in stream_events(chat_service, req, requested_intent=intent):
            yield event

    return endpoint


router.add_api_route(
    "/chat",
    _endpoint(None),
    methods=["POST"],
    response_class=EventSourceResponse,
    summary="流式对话（SSE，自动识别五路意图）",
    tags=["chat"],
    name="chat",
)

for _intent, _label in (
    ("knowledge", "知识库问答"),
    ("query", "订单查询"),
    ("service", "售后业务草稿"),
    ("logistics", "物流 Agent + Tools"),
    ("fallback", "兜底"),
):
    router.add_api_route(
        f"/branch/{_intent}",
        _endpoint(_intent),
        methods=["POST"],
        response_class=EventSourceResponse,
        summary=f"{_label}分支（SSE）",
        tags=["intent-branches"],
        name=f"branch_{_intent}",
    )
