"""对话路由：把应用层的事件流编码成 SSE。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat
from backend.api.schemas import ChatRequest, sse
from backend.application.chat import ChatService

router = APIRouter(tags=["chat"])


@router.post("/chat", summary="流式对话（SSE）")
async def chat(req: ChatRequest, chat_service: ChatService = Depends(get_chat)) -> StreamingResponse:
    async def event_stream():
        async for event, payload in chat_service.stream(req.message, req.thread_id):
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
