"""工单存储用例：编号、去重、时间线、状态校验、落盘与容错。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.domain import TicketCreate, UnknownStatusError
from backend.infrastructure.persistence.json_store import JsonTicketStore


def test_create_assigns_daily_sequence_id(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    first, duplicated = store.create(sample_ticket)
    second, _ = store.create(sample_ticket.model_copy(update={"title": "另一台打印机也装不上"}))
    assert duplicated is False
    assert re.fullmatch(r"TK-\d{8}-0001", first.id)
    assert second.id.endswith("-0002")
    assert first.status == "待受理"
    assert [event.action for event in first.events] == ["创建工单"]


def test_duplicate_open_ticket_is_reused(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    """同一联系人 + 同标题 + 未关闭 = 重复建单，返回已有工单而不是新建。"""
    first, _ = store.create(sample_ticket)
    again, duplicated = store.create(sample_ticket)
    assert duplicated is True
    assert again.id == first.id
    assert store.count() == 1


def test_closed_ticket_allows_new_one(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    first, _ = store.create(sample_ticket)
    store.add_event(first.id, "关闭工单", status="已关闭")
    second, duplicated = store.create(sample_ticket)
    assert duplicated is False
    assert second.id != first.id
    assert store.count() == 2


def test_add_event_appends_timeline_and_status(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    record, _ = store.create(sample_ticket)
    updated = store.add_event(record.id, "转人工", note="用户要求", status="处理中")
    assert updated is not None
    assert updated.status == "处理中"
    assert [event.action for event in updated.events] == ["创建工单", "转人工"]
    assert updated.updated_at >= record.created_at


def test_invalid_status_rejected(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    record, _ = store.create(sample_ticket)
    # 领域层把非法状态也类型化了，不再是裸 ValueError
    with pytest.raises(UnknownStatusError):
        store.add_event(record.id, "乱改状态", status="随便写个状态")


def test_get_is_case_insensitive(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    record, _ = store.create(sample_ticket)
    assert store.get(record.id.lower()) is not None
    assert store.get("TK-19700101-0001") is None


def test_add_event_on_unknown_ticket_returns_none(store: JsonTicketStore) -> None:
    assert store.add_event("TK-19700101-0001", "转人工") is None


def test_list_filters(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    first, _ = store.create(sample_ticket)
    store.create(sample_ticket.model_copy(update={"title": "物流三天不更新", "category": "配送与物流"}))
    store.add_event(first.id, "转人工", status="处理中")

    assert len(store.list()) == 2
    assert len(store.list(status="处理中")) == 1
    assert len(store.list(contact="zhang.san")) == 2
    assert store.list(contact="nobody@corp.com") == []
    assert len(store.list(limit=1)) == 1


def test_persisted_and_reloaded(tmp_path: Path, sample_ticket: TicketCreate) -> None:
    """落盘后新建实例能读回同样的数据（进程重启不丢单）。"""
    path = tmp_path / "tickets.json"
    store = JsonTicketStore(path)
    record, _ = store.create(sample_ticket)
    store.add_event(record.id, "用户催单")

    reloaded = JsonTicketStore(path)
    fetched = reloaded.get(record.id)
    assert fetched is not None
    assert fetched.title == sample_ticket.title
    assert len(fetched.events) == 2
    assert path.with_suffix(".json.tmp").exists() is False  # 原子写不留临时文件


def test_corrupt_file_is_quarantined(tmp_path: Path) -> None:
    """坏文件不阻断启动：改名留证据后从空开始。"""
    path = tmp_path / "tickets.json"
    path.write_text("{ 这不是合法 JSON", encoding="utf-8")
    store = JsonTicketStore(path)
    assert store.count() == 0
    assert list(tmp_path.glob("tickets.broken-*.json"))


def test_skips_invalid_record_but_keeps_others(tmp_path: Path) -> None:
    path = tmp_path / "tickets.json"
    payload = {
        "tickets": [
            {"id": "坏数据"},
            {
                "id": "TK-20260101-0001",
                "title": "邮箱收不到外部邮件",
                "description": "从上周开始外部发件人全部被拦。",
                "category": "发票与报销",
                "priority": "中",
                "contact": "li.si@corp.com",
                "created_at": "2026-01-01 09:00:00",
                "updated_at": "2026-01-01 09:00:00",
            },
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    store = JsonTicketStore(path)
    assert store.count() == 1
    assert store.get("TK-20260101-0001") is not None
