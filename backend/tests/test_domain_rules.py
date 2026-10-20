"""领域规则用例：单号、状态校验、重复建单判定。"""

from __future__ import annotations

from datetime import date

import pytest

from backend.domain import (
    TicketCreate,
    TicketRecord,
    UnknownStatusError,
    duplicate_of,
    is_closed,
    next_ticket_id,
    validate_status,
)

TODAY = date(2026, 10, 16)


def _record(ticket_id: str, title: str = "VPN 连不上报 691", contact: str = "a@corp.com", status: str = "待受理"):
    return TicketRecord(
        id=ticket_id,
        title=title,
        description="整个部门都连不上，已确认内网可访问。",
        category="配送与物流",
        priority="高",
        contact=contact,
        status=status,
        created_at="2026-10-16 09:00:00",
        updated_at="2026-10-16 09:00:00",
    )


def test_next_ticket_id_starts_at_one() -> None:
    assert next_ticket_id([], today=TODAY) == "TK-20261016-0001"


def test_next_ticket_id_increments_within_day() -> None:
    existing = ["TK-20261016-0001", "TK-20261016-0002", "TK-20261015-0007"]
    assert next_ticket_id(existing, today=TODAY) == "TK-20261016-0003"


def test_next_ticket_id_ignores_other_days_and_dirty_ids() -> None:
    existing = ["TK-20261015-0009", "不是单号", "TK-20261016-x"]
    assert next_ticket_id(existing, today=TODAY) == "TK-20261016-0001"


def test_validate_status_accepts_known_values() -> None:
    for status in ("待受理", "处理中", "待用户确认", "已关闭"):
        assert validate_status(status) == status


def test_validate_status_rejects_unknown_value() -> None:
    with pytest.raises(UnknownStatusError):
        validate_status("随便写的状态")


def test_is_closed() -> None:
    assert is_closed("已关闭") is True
    assert is_closed("处理中") is False


def test_duplicate_of_matches_same_contact_and_title() -> None:
    existing = [_record("TK-20261016-0001")]
    payload = TicketCreate(
        title="VPN 连不上报 691",
        description="整个部门都连不上，已确认内网可访问。",
        category="配送与物流",
        priority="高",
        contact="A@CORP.com",  # 大小写不同也算同一个人
    )
    assert duplicate_of(existing, payload) is existing[0]


def test_duplicate_of_ignores_closed_ticket() -> None:
    existing = [_record("TK-20261016-0001", status="已关闭")]
    payload = TicketCreate(
        title="VPN 连不上报 691",
        description="整个部门都连不上，已确认内网可访问。",
        category="配送与物流",
        priority="高",
        contact="a@corp.com",
    )
    assert duplicate_of(existing, payload) is None


def test_duplicate_of_ignores_different_contact_or_title() -> None:
    existing = [_record("TK-20261016-0001")]
    other_contact = TicketCreate(
        title="VPN 连不上报 691",
        description="另一个同事也连不上。",
        category="配送与物流",
        priority="中",
        contact="b@corp.com",
    )
    other_title = TicketCreate(
        title="打印机装不上驱动",
        description="Win11 报签名校验失败。",
        category="商品与质量",
        priority="中",
        contact="a@corp.com",
    )
    assert duplicate_of(existing, other_contact) is None
    assert duplicate_of(existing, other_title) is None
