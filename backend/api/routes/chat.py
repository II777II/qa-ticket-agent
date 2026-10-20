"""对话路由：统一入口，把应用层的事件流编码成 SSE。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat
from backend.api.schemas import ChatRequest, sse
from backend.application.chat import ChatService
from backend.domain.intent import IntentName

router = APIRouter(tags=["chat"])


def stream_response(
    chat_service: ChatService,
    req: ChatRequest,
    requested_intent: IntentName | None = None,
) -> StreamingResponse:
    """把一轮对话编码成 SSE；统一入口和四个分支入口共用该响应契约。"""

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


@router.post("/chat", summary="流式对话（SSE，自动识别四路意图）")
async def chat(req: ChatRequest, chat_service: ChatService = Depends(get_chat)) -> StreamingResponse:
    return stream_response(chat_service, req)
