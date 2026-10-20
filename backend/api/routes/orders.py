"""订单查询路由：订单列表与详情（电商订单查询页）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import get_runtime
from backend.application.runtime import AgentRuntime
from backend.domain.orders import OrderRecord

router = APIRouter(tags=["orders"])


@router.get("/api/orders", response_model=list[OrderRecord], summary="订单查询")
async def list_orders(
    q: str = "",
    status: int | None = None,
    user_id: int | None = None,
    limit: int = 20,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[OrderRecord]:
    return runtime.orders.search(q=q, status=status, user_id=user_id, limit=limit)


@router.get("/api/orders/{order_no}", response_model=OrderRecord, summary="订单详情")
async def get_order(order_no: str, runtime: AgentRuntime = Depends(get_runtime)) -> OrderRecord:
    order = runtime.orders.get(order_no)
    if order is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {order_no}")
    return order
