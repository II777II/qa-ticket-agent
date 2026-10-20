"""对话根路由：统一入口，并挂载四个显式分支子路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat
from backend.api.routes import agent as agent_routes
from backend.api.schemas import ChatRequest
from backend.api.streaming import stream_response
from backend.application.chat import ChatService

router = APIRouter(tags=["chat"])
router.include_router(agent_routes.router)


@router.post("/chat", summary="流式对话（SSE，自动识别四路意图）")
async def chat(req: ChatRequest, chat_service: ChatService = Depends(get_chat)) -> StreamingResponse:
    return stream_response(chat_service, req)
