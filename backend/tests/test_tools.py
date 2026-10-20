"""工具用例：注册、参数校验、返回值；重点是「防幻觉乱建单」那层校验。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from langchain_core.tools import BaseTool

from backend.application.agent.tools import create_tools as _create_tools
from backend.application.orders import OrderService
from backend.application.tickets import TicketService
from backend.infrastructure.persistence.factory import create_order_store
from backend.infrastructure.persistence.json_store import JsonTicketStore


def create_tools(store: JsonTicketStore) -> list[BaseTool]:
    """测试适配：工具现在依赖工单用例，这里包一层，保持用例里的旧调用签名。"""
    return _create_tools(TicketService(store), OrderService(create_order_store()))


def _by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_registers_expected_tools(store: JsonTicketStore) -> None:
    tools = create_tools(store)
    assert [tool.name for tool in tools] == [
        "create_ticket",
        "query_ticket",
        "escalate_to_human",
        "query_order",
    ]
    # 工具描述会进模型上下文，必须写清楚使用条件
    for tool in tools:
        assert tool.description.strip()


def test_create_ticket_returns_payload(store: JsonTicketStore) -> None:
    tool = _by_name(create_tools(store), "create_ticket")
    payload = json.loads(
        tool.invoke(
            {
                "title": "物流三天没有更新",
                "description": "包裹显示已揽收，但物流三天没有更新，联系快递未果。",
                "category": "配送与物流",
                "priority": "高",
                "contact": "zhang.san@corp.com",
            }
        )
    )
    assert payload["ok"] is True
    assert payload["action"] == "create_ticket"
    assert payload["ticket"]["id"].startswith("TK-")
    assert payload["ticket"]["status"] == "待受理"
    assert store.count() == 1


def test_create_ticket_rejects_invalid_category(store: JsonTicketStore) -> None:
    """分类不在枚举里就直接报错——这是挡住幻觉脏数据的第一道闸。"""
    tool = _by_name(create_tools(store), "create_ticket")
    with pytest.raises(ValidationError):
        tool.invoke(
            {
                "title": "服务器冒烟了",
                "description": "机房闻到焦味，报警器响了。",
                "category": "服务器坏了",
                "priority": "紧急",
                "contact": "zhang.san@corp.com",
            }
        )
    assert store.count() == 0


def test_create_ticket_rejects_short_description(store: JsonTicketStore) -> None:
    tool = _by_name(create_tools(store), "create_ticket")
    with pytest.raises(ValidationError):
        tool.invoke(
            {
                "title": "打印机坏了",
                "description": "坏了",
                "category": "商品与质量",
                "priority": "中",
                "contact": "zhang.san@corp.com",
            }
        )


def test_query_ticket_by_id(store: JsonTicketStore) -> None:
    tools = create_tools(store)
    created = json.loads(
        _by_name(tools, "create_ticket").invoke(
            {
                "title": "邮箱容量满了",
                "description": "收不到新邮件，提示超过配额。",
                "category": "发票与报销",
                "priority": "中",
                "contact": "li.si@corp.com",
            }
        )
    )
    ticket_id = created["ticket"]["id"]
    payload = json.loads(_by_name(tools, "query_ticket").invoke({"ticket_id": ticket_id}))
    assert payload["ok"] is True
    assert payload["tickets"][0]["id"] == ticket_id


def test_query_ticket_urge_records_timeline(store: JsonTicketStore) -> None:
    tools = create_tools(store)
    created = json.loads(
        _by_name(tools, "create_ticket").invoke(
            {
                "title": "打印机驱动装不上",
                "description": "Win11 装驱动报签名校验失败，已卸载旧驱动。",
                "category": "商品与质量",
                "priority": "中",
                "contact": "li.si@corp.com",
            }
        )
    )
    ticket_id = created["ticket"]["id"]
    payload = json.loads(_by_name(tools, "query_ticket").invoke({"ticket_id": ticket_id, "urge": True}))
    actions = [event["action"] for event in payload["tickets"][0]["events"]]
    assert "用户催单" in actions


def test_query_ticket_without_identifiers(store: JsonTicketStore) -> None:
    payload = json.loads(_by_name(create_tools(store), "query_ticket").invoke({}))
    assert payload["ok"] is False
    assert "工单号或联系人" in payload["message"]


def test_query_unknown_ticket_returns_friendly_error(store: JsonTicketStore) -> None:
    payload = json.loads(_by_name(create_tools(store), "query_ticket").invoke({"ticket_id": "TK-19700101-0001"}))
    assert payload["ok"] is False
    assert "没有找到工单" in payload["message"]


def test_escalate_to_human_changes_status(store: JsonTicketStore) -> None:
    tools = create_tools(store)
    created = json.loads(
        _by_name(tools, "create_ticket").invoke(
            {
                "title": "商品外壳有裂痕",
                "description": "收到的商品外壳有明显裂痕，已拍照，需要换货。",
                "category": "商品与质量",
                "priority": "高",
                "contact": "wang.wu@corp.com",
            }
        )
    )
    ticket_id = created["ticket"]["id"]
    payload = json.loads(
        _by_name(tools, "escalate_to_human").invoke({"ticket_id": ticket_id, "reason": "问题仍未恢复，用户要求转人工"})
    )
    assert payload["ok"] is True
    assert payload["ticket"]["status"] == "处理中"
    assert payload["ticket"]["events"][-1]["action"] == "转人工"


def test_escalate_unknown_ticket(store: JsonTicketStore) -> None:
    payload = json.loads(
        _by_name(create_tools(store), "escalate_to_human").invoke({"ticket_id": "TK-19700101-0001", "reason": "转人工"})
    )
    assert payload["ok"] is False
    assert "先建单" in payload["message"]


def test_query_order_by_order_no(store: JsonTicketStore) -> None:
    sample = OrderService(create_order_store()).search(limit=1)[0]
    payload = json.loads(_by_name(create_tools(store), "query_order").invoke({"order_no": sample.order_no}))
    assert payload["ok"] is True
    assert payload["orders"][0]["order_no"] == sample.order_no
    assert payload["orders"][0]["status"]


def test_query_order_by_customer_name(store: JsonTicketStore) -> None:
    payload = json.loads(_by_name(create_tools(store), "query_order").invoke({"keyword": "张三"}))
    assert payload["ok"] is True
    assert payload["orders"]
    assert all(order["customer"] == "张三" for order in payload["orders"])


def test_query_order_not_found(store: JsonTicketStore) -> None:
    payload = json.loads(_by_name(create_tools(store), "query_order").invoke({"keyword": "不存在的人"}))
    assert payload["ok"] is False
    assert "订单号" in payload["message"]
