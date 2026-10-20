"""订单存储（JSON 实现，对应 Postgres 的订单表）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.domain.orders import OrderRecord

logger = logging.getLogger("qa_ticket.order_store")


class JsonOrderStore:
    """启动时把 orders.json 读进内存；POC 只读，不做写操作。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._orders: list[OrderRecord] = []
        self._by_no: dict[str, OrderRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            logger.warning("订单文件不存在: %s", self.path)
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        for item in payload:
            record = OrderRecord(**item)
            self._orders.append(record)
            self._by_no[record.order_no.upper()] = record
        logger.info("已加载 %d 条订单: %s", len(self._orders), self.path)

    def get(self, order_no: str) -> OrderRecord | None:
        return self._by_no.get(order_no.strip().upper())

    def search(
        self,
        *,
        q: str = "",
        status: int | None = None,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[OrderRecord]:
        key = q.strip().lower()
        results = []
        for order in self._orders:
            if status is not None and order.order_status != status:
                continue
            if user_id is not None and order.user_id != user_id:
                continue
            if key:
                haystack = [order.order_no.lower(), str(order.user_id)]
                if order.user:
                    haystack.extend(str(value).lower() for value in order.user.values())
                haystack.extend(item.product_name.lower() for item in order.items)
                if not any(key in text for text in haystack):
                    continue
            results.append(order)
        results.sort(key=lambda order: order.created_at, reverse=True)
        return results[: max(limit, 0)]

    def count(self) -> int:
        return len(self._orders)
