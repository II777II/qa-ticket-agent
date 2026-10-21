"""订单工具参数、返回值和失败提示测试。"""

from __future__ import annotations

import json

from langchain_core.tools import BaseTool

from backend.application.agent.tools import create_tools
from backend.application.orders import OrderService
from backend.infrastructure.persistence import create_order_store


def _orders() -> OrderService:
    return OrderService(create_order_store())


def _by_name(tools: list[BaseTool], name: str) -> BaseTool:
    return next(tool for tool in tools if tool.name == name)


def test_registers_only_query_order() -> None:
    tools = create_tools(_orders())
    assert [tool.name for tool in tools] == ["query_order"]
    assert tools[0].description.strip()


def test_query_order_by_order_no() -> None:
    orders = _orders()
    sample = orders.search(limit=1)[0]
    payload = json.loads(_by_name(create_tools(orders), "query_order").invoke({"order_no": sample.order_no}))
    assert payload["ok"] is True
    assert payload["orders"][0]["order_no"] == sample.order_no


def test_query_order_by_customer_name() -> None:
    payload = json.loads(_by_name(create_tools(_orders()), "query_order").invoke({"keyword": "张三"}))
    assert payload["ok"] is True
    assert all(order["customer"] == "张三" for order in payload["orders"])


def test_query_order_not_found() -> None:
    payload = json.loads(_by_name(create_tools(_orders()), "query_order").invoke({"keyword": "不存在的人"}))
    assert payload["ok"] is False
    assert "订单号" in payload["message"]
