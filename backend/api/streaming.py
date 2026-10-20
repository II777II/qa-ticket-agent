"""对话接口的 SSE 响应封装，供统一入口与四个分支入口复用。"""

from __future__ import annotations

from fastapi.responses import StreamingResponse

from backend.api.schemas import ChatRequest, sse
from backend.application.chat import ChatService
from backend.domain.intent import IntentName


def stream_response(
    chat_service: ChatService,
    req: ChatRequest,
    requested_intent: IntentName | None = None,
) -> StreamingResponse:
    """把一轮对话编码成 SSE。"""

    async def event_stream():
        async for event, payload in chat_service.stream(
            req.message,
            req.thread_id,
            requested_intent=requested_intent,
        ):
            yield sse(event, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 走 Nginx 时禁用缓冲，否则 SSE 会攒一批才下发
            "X-Accel-Buffering": "no",
        },
    )
