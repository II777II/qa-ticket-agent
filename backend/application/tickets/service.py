"""工单用例：用户确认后的创建与计数。"""

from __future__ import annotations

from typing import Protocol

from backend.domain import TicketCreate, TicketRecord


class TicketStore(Protocol):
    def count(self) -> int: ...

    def create(self, payload: TicketCreate) -> tuple[TicketRecord, bool]: ...


class TicketService:
    def __init__(self, store: TicketStore) -> None:
        self._store = store

    def create(self, payload: TicketCreate) -> tuple[TicketRecord, bool]:
        return self._store.create(payload)

    def count(self) -> int:
        return self._store.count()
