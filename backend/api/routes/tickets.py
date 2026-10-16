"""工单路由：列表与详情（前端看板用）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_runtime
from backend.application.runtime import AgentRuntime
from backend.domain import TicketRecord

router = APIRouter(tags=["tickets"])


@router.get("/api/tickets", response_model=list[TicketRecord], summary="工单列表")
async def list_tickets(
    status: str | None = None,
    contact: str | None = None,
    limit: int = 20,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[TicketRecord]:
    return runtime.tickets.list(status=status, contact=contact, limit=limit)


@router.get("/api/tickets/{ticket_id}", response_model=TicketRecord, summary="工单详情")
async def get_ticket(ticket_id: str, runtime: AgentRuntime = Depends(get_runtime)) -> TicketRecord:
    record = runtime.tickets.find(ticket_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")
    return record
