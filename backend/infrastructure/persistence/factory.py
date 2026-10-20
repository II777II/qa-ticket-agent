"""工单存储工厂：按 TICKET_STORE 创建存储实现。"""

from __future__ import annotations

from backend.infrastructure.config import settings
from backend.infrastructure.persistence.kb_catalog import JsonKnowledgeCatalog
from backend.infrastructure.persistence.order_store import JsonOrderStore
from backend.infrastructure.persistence.json_store import JsonTicketStore


def create_ticket_store() -> JsonTicketStore:
    kind = settings.ticket_store

    if kind == "json":
        return JsonTicketStore(settings.ticket_store_file)

    if kind == "postgres":
        raise NotImplementedError(
            "TICKET_STORE=postgres 尚未接入：需要先装 sqlalchemy + psycopg，"
            "并在 docker/docker-compose.yml 里打开 postgres 服务。"
        )

    raise ValueError(f"未知的 TICKET_STORE: {kind!r}，可选 json / postgres")


def create_order_store() -> JsonOrderStore:
    kind = settings.order_store
    if kind == "json":
        return JsonOrderStore(settings.orders_file)
    if kind == "postgres":
        raise NotImplementedError(
            "ORDER_STORE=postgres 尚未接入：按 docs/sql/postgres_schema.sql 建表后，"
            "新增 infrastructure/persistence/postgres_order_store.py（满足 OrderStore 协议）即可。"
        )
    raise ValueError(f"未知的 ORDER_STORE: {kind!r}，可选 json / postgres")


def create_knowledge_catalog() -> JsonKnowledgeCatalog:
    return JsonKnowledgeCatalog(settings.kb_articles_file, settings.kb_root / "categories.json")
