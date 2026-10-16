"""工具用例：注册、参数校验、返回值；重点是「防幻觉乱建单」那层校验。"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from langchain_core.tools import BaseTool

from backend.application.agent.tools import create_tools as _create_tools
from backend.application.tickets import TicketService
from backend.infrastructure.persistence.json_store import JsonTicketStore


def create_tools(store: JsonTicketStore) -> list[BaseTool]:
    """测试适配：工具现在依赖工单用例，这里包一层，保持用例里的旧调用签名。"""
    return _create_tools(TicketService(store))


def _by_name(tools, name):
    return next(tool for tool in tools if tool.name == name)


def test_registers_expected_tools(store: JsonTicketStore) -> None:
    tools = create_tools(store)
    assert [tool.name for tool in tools] == ["create_ticket", "query_ticket", "escalate_to_human"]
    # 工具描述会进模型上下文，必须写清楚使用条件
    for tool in tools:
        assert tool.description.strip()


def test_create_ticket_returns_payload(store: JsonTicketStore) -> None:
    tool = _by_name(create_tools(store), "create_ticket")
    payload = json.loads(
        tool.invoke(
            {
                "title": "VPN 连不上报 691",
                "description": "整个部门从今天早上开始连不上，已确认内网可访问。",
                "category": "网络与VPN",
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
                "category": "办公设备",
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
                "category": "邮件与协作",
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
                "category": "办公设备",
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
                "title": "业务系统打不开",
                "description": "打开门户后报表模块一直转圈，已换浏览器复现。",
                "category": "业务系统",
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
