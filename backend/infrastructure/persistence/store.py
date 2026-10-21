"""JSON 持久化：工单写入、订单读取和知识库目录。"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from backend.domain.knowledge import KnowledgeArticle, KnowledgeCategory
from backend.domain.models import TicketCreate, TicketRecord
from backend.domain.orders import OrderRecord
from backend.domain.rules import duplicate_of, next_ticket_id
from backend.infrastructure.config import settings

logger = logging.getLogger("qa_ticket.store")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JsonTicketStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._tickets: dict[str, TicketRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            broken = self.path.with_name(f"{self.path.stem}.broken-{datetime.now():%Y%m%d%H%M%S}.json")
            logger.warning("工单文件损坏(%s)，移至 %s", exc, broken.name)
            try:
                self.path.replace(broken)
            except OSError:
                pass
            return
        for item in raw.get("tickets", []) if isinstance(raw, dict) else raw:
            try:
                record = TicketRecord(**item)
                self._tickets[record.id] = record
            except Exception:
                logger.warning("跳过无法解析的工单: %s", item)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _now(),
            "tickets": [record.model_dump() for record in self._tickets.values()],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def count(self) -> int:
        return len(self._tickets)

    def create(self, payload: TicketCreate) -> tuple[TicketRecord, bool]:
        with self._lock:
            existing = duplicate_of(list(self._tickets.values()), payload)
            if existing:
                return existing, True
            now = _now()
            record = TicketRecord(
                id=next_ticket_id(self._tickets),
                status="待受理",
                created_at=now,
                **payload.model_dump(),
            )
            self._tickets[record.id] = record
            self._save()
            return record, False


class JsonOrderStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._orders: list[OrderRecord] = []
        self._by_no: dict[str, OrderRecord] = {}
        if self.path.is_file():
            for item in json.loads(self.path.read_text(encoding="utf-8")):
                record = OrderRecord(**item)
                self._orders.append(record)
                self._by_no[record.order_no.upper()] = record

    def get(self, order_no: str) -> OrderRecord | None:
        return self._by_no.get(order_no.strip().upper())

    def search(
        self,
        *,
        q: str = "",
        status: int | None = None,
        user_id: int | None = None,
        limit: int = 20,
    ) -> list[OrderRecord]:
        key = q.strip().lower()
        rows = []
        for order in self._orders:
            if status is not None and order.order_status != status:
                continue
            if user_id is not None and order.user_id != user_id:
                continue
            if key:
                text = " ".join(
                    [
                        order.order_no,
                        str(order.user_id),
                        *(str(value) for value in (order.user or {}).values()),
                        *(item.product_name for item in order.items),
                    ]
                ).lower()
                if key not in text:
                    continue
            rows.append(order)
        return sorted(rows, key=lambda order: order.created_at, reverse=True)[: max(limit, 0)]

    def count(self) -> int:
        return len(self._orders)


class JsonKnowledgeCatalog:
    def __init__(self, articles_file: Path, categories_file: Path) -> None:
        self._articles = (
            [KnowledgeArticle(**item) for item in json.loads(articles_file.read_text(encoding="utf-8"))]
            if articles_file.is_file()
            else []
        )
        self._categories = (
            [KnowledgeCategory(**item) for item in json.loads(categories_file.read_text(encoding="utf-8"))]
            if categories_file.is_file()
            else []
        )

    def categories(self) -> list[KnowledgeCategory]:
        return sorted(self._categories, key=lambda item: item.sort_no)

    def get(self, article_no: str) -> KnowledgeArticle | None:
        wanted = article_no.strip().upper()
        return next((item for item in self._articles if item.article_no.upper() == wanted), None)

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]:
        key = q.strip().lower()
        category_key = category.strip().lower()
        rows = []
        for article in self._articles:
            if category_key and category_key not in {
                article.category_code.lower(),
                article.category_name.lower(),
                str(article.category_id),
            }:
                continue
            if key:
                text = " ".join([article.title, article.summary, article.article_no, *article.tags]).lower()
                if key not in text:
                    continue
            rows.append(article)
        return sorted(rows, key=lambda item: (item.is_top, item.sort_weight), reverse=True)[: max(limit, 0)]

    def count(self) -> int:
        return len(self._articles)


def create_ticket_store() -> JsonTicketStore:
    if settings.ticket_store == "json":
        return JsonTicketStore(settings.ticket_store_file)
    if settings.ticket_store == "postgres":
        raise NotImplementedError("TICKET_STORE=postgres 尚未接入")
    raise ValueError(f"未知的 TICKET_STORE: {settings.ticket_store!r}")


def create_order_store() -> JsonOrderStore:
    if settings.order_store == "json":
        return JsonOrderStore(settings.orders_file)
    if settings.order_store == "postgres":
        raise NotImplementedError("ORDER_STORE=postgres 尚未接入")
    raise ValueError(f"未知的 ORDER_STORE: {settings.order_store!r}")


def create_knowledge_catalog() -> JsonKnowledgeCatalog:
    return JsonKnowledgeCatalog(settings.kb_articles_file, settings.kb_root / "categories.json")
