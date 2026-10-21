"""领域规则：按天单号和重复建单。"""

from __future__ import annotations

from datetime import date

from backend.domain.core import TicketCreate, TicketRecord, duplicate_of, next_ticket_id

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
