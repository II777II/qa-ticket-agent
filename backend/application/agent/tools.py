"""Agent 工具适配：只暴露订单查询这一只读能力。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from backend.application.orders import OrderService
from backend.application.orders.service import order_summary
from backend.domain.orders import ORDER_STATUS_LABELS

STATUS_BY_LABEL = {label: code for code, label in ORDER_STATUS_LABELS.items()}


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def create_tools(orders: OrderService) -> list[BaseTool]:
    @tool("query_order")
    def query_order(order_no: str = "", keyword: str = "", status: str = "") -> str:
        """查询电商订单，可传订单号、姓名/手机号/商品关键词和中文订单状态。"""
        status_code = None
        if status:
            status_code = STATUS_BY_LABEL.get(status.strip())
            if status_code is None:
                return _dump(
                    {
                        "ok": False,
                        "action": "query_order",
                        "message": f"未知订单状态 {status!r}",
                    }
                )

        if order_no:
            record = orders.get(order_no)
            results = [record] if record is not None else []
        else:
            results = orders.search(q=keyword, status=status_code, limit=5)

        if not results:
            return _dump(
                {
                    "ok": False,
                    "action": "query_order",
                    "message": "没有找到匹配的订单，请提供订单号、姓名或手机号",
                }
            )
        return _dump(
            {
                "ok": True,
                "action": "query_order",
                "orders": [order_summary(order) for order in results],
                "message": f"查到 {len(results)} 笔订单",
            }
        )

    return [query_order]
