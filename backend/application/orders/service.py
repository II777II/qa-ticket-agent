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
