"""领域规则：按天单号和重复建单。"""

from __future__ import annotations

from datetime import date

from backend.domain.core import (
    TicketCreate, TicketRecord, duplicate_of, extract_order_keyword, is_order_query,
    next_ticket_id, rule_classify,
)

TODAY = date(2026, 10, 16)


def _record(ticket_id: str, contact: str = "a@corp.com") -> TicketRecord:
    return TicketRecord(
        id=ticket_id,
        title="打印机无法连接",
        description="办公室打印机驱动安装失败，无法正常打印。",
        category="商品与质量",
        priority="高",
        contact=contact,
        created_at="2026-10-16 09:00:00",
    )


def test_next_ticket_id_starts_at_one() -> None:
    assert next_ticket_id([], today=TODAY) == "TK-20261016-0001"


def test_next_ticket_id_increments_within_day() -> None:
    existing = ["TK-20261016-0001", "TK-20261016-0002", "TK-20261015-0007"]
    assert next_ticket_id(existing, today=TODAY) == "TK-20261016-0003"


def test_next_ticket_id_ignores_other_days_and_dirty_ids() -> None:
    existing = ["TK-20261015-0009", "不是单号", "TK-20261016-x"]
    assert next_ticket_id(existing, today=TODAY) == "TK-20261016-0001"


def test_duplicate_uses_contact_and_title() -> None:
    existing = [_record("TK-20261016-0001")]
    payload = TicketCreate(
        title="打印机无法连接",
        description="办公室打印机驱动安装失败，无法正常打印。",
        category="商品与质量",
        priority="高",
        contact="A@CORP.com",
    )
    assert duplicate_of(existing, payload) is existing[0]


def test_duplicate_ignores_different_contact_or_title() -> None:
    existing = [_record("TK-20261016-0001")]
    other = TicketCreate(
        title="打印机无法连接",
        description="另一个同事也遇到打印机无法连接。",
        category="商品与质量",
        priority="中",
        contact="b@corp.com",
    )
    assert duplicate_of(existing, other) is None


def test_three_way_rule_classifier() -> None:
    assert rule_classify("退款多久到账").intent == "read"
    assert rule_classify("订单 SO202609150020 商品损坏，申请换货").intent == "write"
    assert rule_classify("我要投诉并转人工").intent == "human"


def test_read_tool_rules_distinguish_order_and_knowledge() -> None:
    assert is_order_query("帮我查询张三的订单")
    assert not is_order_query("退货退款和发票怎么处理")
    assert extract_order_keyword("查看张三订单") == "张三"
