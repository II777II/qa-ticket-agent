"""Agent 四路分支路由：显式进入 knowledge / query / service / fallback。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.api.deps import get_chat, get_runtime
from backend.api.schemas import ChatRequest, ServiceConfirmRequest, ServiceConfirmResponse
from backend.api.streaming import stream_response
from backend.application.chat import ChatService
from backend.application.runtime import AgentRuntime
from backend.domain import TicketCreate

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


@router.post("/service/confirm", response_model=ServiceConfirmResponse, summary="确认并提交业务办理")
async def confirm_service(
    req: ServiceConfirmRequest,
    runtime: AgentRuntime = Depends(get_runtime),
) -> ServiceConfirmResponse:
    if runtime.orders.get(req.order_no) is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {req.order_no}")

    record, duplicated = runtime.tickets.create(
        TicketCreate(
            title=f"{req.service_type}办理 · {req.order_no}"[:60],
            description=req.description,
            category=req.category,
            priority=req.priority,
            contact=req.contact,
        ),
        source="service-panel",
    )
    message = "该业务已提交过，返回原工单。" if duplicated else "业务办理已提交。"
    return ServiceConfirmResponse(
        ticket_id=record.id,
        status=record.status,
        duplicated=duplicated,
        message=message,
    )


@router.post("/fallback", summary="兜底分支（SSE）")
async def fallback(
    req: ChatRequest,
    chat_service: ChatService = Depends(get_chat),
) -> StreamingResponse:
    return stream_response(chat_service, req, requested_intent="fallback")
