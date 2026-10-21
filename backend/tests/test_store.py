"""JSON 工单存储：编号、去重、持久化与容错。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.domain.core import TicketCreate
from backend.infrastructure.storage import JsonTicketStore


def test_create_assigns_daily_sequence_id(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    first, duplicated = store.create(sample_ticket)
    second, _ = store.create(sample_ticket.model_copy(update={"title": "另一台打印机也装不上"}))
    assert duplicated is False
    assert re.fullmatch(r"TK-\d{8}-0001", first.id)
    assert second.id.endswith("-0002")
    assert first.status == "待受理"


def test_duplicate_ticket_is_reused(store: JsonTicketStore, sample_ticket: TicketCreate) -> None:
    first, _ = store.create(sample_ticket)
    again, duplicated = store.create(sample_ticket)
    assert duplicated is True
    assert again.id == first.id
    assert store.count() == 1


def test_persisted_and_reloaded(tmp_path: Path, sample_ticket: TicketCreate) -> None:
    path = tmp_path / "tickets.json"
    store = JsonTicketStore(path)
    record, _ = store.create(sample_ticket)

    reloaded = JsonTicketStore(path)
    assert reloaded.count() == 1
    next_record, duplicated = reloaded.create(
        sample_ticket.model_copy(update={"title": "另一台打印机也装不上"})
    )
    assert duplicated is False
    assert record.id.endswith("-0001")
    assert next_record.id.endswith("-0002")
    assert path.with_suffix(".json.tmp").exists() is False


def test_corrupt_file_is_quarantined(tmp_path: Path) -> None:
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
            },
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert JsonTicketStore(path).count() == 1
