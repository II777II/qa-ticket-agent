"""工单用例：建单、查询、催单、转人工。

这一层把「业务动作」从工具适配里拿出来：工具层只负责把模型给的参数翻译成调用、
把结果序列化成 JSON；至于「催单要记成谁触发的、转人工要把状态推到哪一档」，
属于业务口径，写在这里。

存储通过 Protocol 注入，所以 JSON 文件换成 Postgres 时这一层不用改。
"""

from __future__ import annotations

from typing import Protocol

from backend.domain import TicketCreate, TicketRecord


class TicketStore(Protocol):
    """工单存储需要满足的接口。"""

    def get(self, ticket_id: str) -> TicketRecord | None: ...

    def list(
        self,
        *,
        status: str | None = None,
        contact: str | None = None,
        limit: int | None = 20,
    ) -> list[TicketRecord]: ...

    def count(self) -> int: ...

    def create(self, payload: TicketCreate, *, source: str = "agent") -> tuple[TicketRecord, bool]: ...

    def add_event(
        self,
        ticket_id: str,
        action: str,
        *,
        note: str = "",
        actor: str = "agent",
        status: str | None = None,
    ) -> TicketRecord | None: ...


class TicketService:
    """工单的业务动作集合（工单领域规则的调用入口）。"""

    def __init__(self, store: TicketStore) -> None:
        self._store = store

    def create(self, payload: TicketCreate, *, source: str = "agent") -> tuple[TicketRecord, bool]:
        """建单。返回 (工单, 是否命中重复建单)；重复判定在领域层。"""
        return self._store.create(payload, source=source)

    def find(self, ticket_id: str) -> TicketRecord | None:
        return self._store.get(ticket_id)

    def list(
        self,
        *,
        status: str | None = None,
        contact: str | None = None,
        limit: int | None = 20,
    ) -> list[TicketRecord]:
        return self._store.list(status=status, contact=contact, limit=limit)

    def count(self) -> int:
        return self._store.count()

    def urge(self, ticket_id: str) -> TicketRecord | None:
        """催单：由用户触发的，所以在时间线上记为 user。"""
        return self._store.add_event(ticket_id, "用户催单", note="通过对话催单", actor="user")

    def escalate(self, ticket_id: str, reason: str) -> TicketRecord | None:
        """转人工：记一条时间线，并把状态推进到「处理中」。"""
        return self._store.add_event(ticket_id, "转人工", note=reason, actor="agent", status="处理中")
