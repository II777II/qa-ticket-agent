"""订单查询用例：给接口层与 Agent 工具共用。"""

from __future__ import annotations

from typing import Protocol

from backend.domain.orders import OrderRecord


class OrderStore(Protocol):
    def get(self, order_no: str) -> OrderRecord | None: ...

    def search(
        self,
        *,
        q: str = "",
        status: int | None = None,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[OrderRecord]: ...

    def count(self) -> int: ...


class OrderService:
    def __init__(self, store: OrderStore) -> None:
        self._store = store

    def get(self, order_no: str) -> OrderRecord | None:
        return self._store.get(order_no)

    def search(self, **filters) -> list[OrderRecord]:
        return self._store.search(**filters)

    def count(self) -> int:
        return self._store.count()


def order_summary(order: OrderRecord) -> dict:
    """工具与路由节点共用的订单摘要（SSE order 事件的载荷）。"""
    return {
        "order_no": order.order_no,
        "status": order.status_label,
        "pay_status": order.pay_status_label,
        "customer": (order.user or {}).get("name") or order.user_id,
        "payable_amount": order.payable_amount,
        "paid_amount": order.paid_amount,
        "refund_amount": order.refund_amount,
        "created_at": order.created_at,
        "items": [
            {"name": item.product_name, "spec": item.sku_spec, "quantity": item.quantity, "price": item.price}
            for item in order.items
        ],
    }
