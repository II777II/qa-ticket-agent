"""工单存储工厂：按 TICKET_STORE 创建存储实现。"""

from __future__ import annotations

from backend.config import settings
from backend.stores.json_store import JsonTicketStore


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
