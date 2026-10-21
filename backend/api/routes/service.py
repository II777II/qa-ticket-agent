"""业务动作路由：用户确认后的售后业务提交。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_runtime
from backend.api.schemas import ServiceConfirmRequest, ServiceConfirmResponse
from backend.application.runtime import AgentRuntime
from backend.domain import TicketCreate

router = APIRouter(prefix="/branch/service", tags=["service-actions"])


@router.post("/confirm", response_model=ServiceConfirmResponse, summary="确认并提交业务办理")
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
