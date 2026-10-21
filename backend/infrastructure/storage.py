"""JSON persistence adapters for tickets, orders and the knowledge catalog."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.domain.core import (
    KnowledgeArticle, KnowledgeCategory, OrderRecord, TicketCreate, TicketRecord,
    duplicate_of, next_ticket_id,
)
from backend.infrastructure.config import settings


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _models(path: Path, model: type[Any]) -> list[Any]:
    return [model(**item) for item in _read_json(path, [])]


class JsonTicketStore:
    def __init__(self, path: Path) -> None:
        self.path, self._lock, self._tickets = path, threading.Lock(), {}
        try:
            raw = _read_json(path, {})
        except (OSError, json.JSONDecodeError) as exc:
            broken = path.with_name(f"{path.stem}.broken-{datetime.now():%Y%m%d%H%M%S}.json")
            logging.getLogger("qa_ticket.store").warning("工单文件损坏(%s)，移至 %s", exc, broken.name)
            try:
                path.replace(broken)
            except OSError:
                pass
            return
        for item in raw.get("tickets", []) if isinstance(raw, dict) else raw:
            try:
                record = TicketRecord(**item)
                self._tickets[record.id] = record
            except Exception:
                continue

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        payload = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tickets": [x.model_dump() for x in self._tickets.values()],
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def count(self) -> int:
        return len(self._tickets)

    def create(self, payload: TicketCreate) -> tuple[TicketRecord, bool]:
        with self._lock:
            if existing := duplicate_of(list(self._tickets.values()), payload):
                return existing, True
            record = TicketRecord(
                id=next_ticket_id(self._tickets),
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                **payload.model_dump(),
            )
            self._tickets[record.id] = record
            self._save()
            return record, False


class JsonOrderStore:
    def __init__(self, path: Path) -> None:
        self._orders = _models(path, OrderRecord)
        self._by_no = {x.order_no.upper(): x for x in self._orders}

    def get(self, order_no: str) -> OrderRecord | None:
        return self._by_no.get(order_no.strip().upper())

    def search(self, *, user_id: int | None = None, limit: int = 20) -> list[OrderRecord]:
        if user_id is None:
            return []
        rows = [order for order in self._orders if order.user_id == user_id]
        return sorted(rows, key=lambda order: order.created_at, reverse=True)[:max(limit, 0)]

    def count(self) -> int:
        return len(self._orders)


class JsonKnowledgeCatalog:
    def __init__(self, articles_file: Path, categories_file: Path) -> None:
        self._articles = _models(articles_file, KnowledgeArticle)
        self._categories = _models(categories_file, KnowledgeCategory)

    def categories(self) -> list[KnowledgeCategory]:
        return sorted(self._categories, key=lambda x: x.sort_no)

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]:
        key, category, rows = q.strip().lower(), category.strip().lower(), []
        for article in self._articles:
            keys = {article.category_code.lower(), article.category_name.lower(), str(article.category_id)}
            text = " ".join([article.title, article.summary, article.article_no, *article.tags]).lower()
            if (not category or category in keys) and (not key or key in text):
                rows.append(article)
        return sorted(rows, key=lambda x: (x.is_top, x.sort_weight), reverse=True)[:max(limit, 0)]

    def count(self) -> int:
        return len(self._articles)


def _json_store(value: str, name: str, build):
    if value == "json":
        return build()
    if value == "postgres":
        raise NotImplementedError(f"{name}=postgres 尚未接入")
    raise ValueError(f"未知的 {name}: {value!r}")


def create_ticket_store() -> JsonTicketStore:
    return _json_store(settings.ticket_store, "TICKET_STORE", lambda: JsonTicketStore(settings.data_dir / "tickets.json"))


def create_order_store() -> JsonOrderStore:
    return _json_store(settings.order_store, "ORDER_STORE", lambda: JsonOrderStore(settings.orders_file))


def create_knowledge_catalog() -> JsonKnowledgeCatalog:
    return JsonKnowledgeCatalog(settings.kb_articles_file, settings.kb_root / "categories.json")
