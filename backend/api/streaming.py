"""对话接口的 SSE 事件生成器，供统一入口与四个分支入口复用。"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from fastapi.sse import ServerSentEvent

from backend.api.schemas import ChatRequest
from backend.application.chat import ChatService
from backend.application.chat.events import EVENT_ERROR
from backend.domain.intent import IntentName

logger = logging.getLogger("qa_ticket.streaming")


def _json_data(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


async def stream_events(
    chat_service: ChatService,
    req: ChatRequest,
    requested_intent: IntentName | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """把应用事件转换为 SSE；普通异常转为终止性 error 事件。"""
    try:
        async for event, payload in chat_service.stream(
            req.message,
            req.thread_id,
            requested_intent=requested_intent,
        ):
            yield ServerSentEvent(event=event, raw_data=_json_data(payload))
    except Exception as exc:
        # CancelledError 继承 BaseException，不会被这里误捕获为业务错误。
        logger.exception("SSE 事件流异常: thread_id=%s", req.thread_id)
        data = {
            "type": exc.__class__.__name__,
            "message": str(exc) or "流式响应异常",
        }
        yield ServerSentEvent(event=EVENT_ERROR, raw_data=_json_data(data))
