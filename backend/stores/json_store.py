"""工单存储的 JSON 文件实现。

选 JSON 而不是数据库，是为了 POC 阶段「零依赖、看得见、能改」：
演示完打开 backend/data/tickets.json 就能看到工单，也能手改状态再继续演。

两个工程细节：
1. 写盘用「临时文件 + os.replace」，避免写到一半进程被杀导致文件损坏；
2. 加线程锁——FastAPI 的同步接口跑在线程池里，工具又可能被并发调用。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from backend.domain.models import TicketCreate, TicketEvent, TicketRecord
from backend.domain.rules import duplicate_of, next_ticket_id, validate_status

logger = logging.getLogger("qa_ticket.store")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class JsonTicketStore:
    """工单的读写入口。内存里保存一份索引，每次变更整体落盘。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._tickets: dict[str, TicketRecord] = {}
        self._load()

    # ---------------- 初始化 ----------------
    def _load(self) -> None:
        if not self.path.exists():
            logger.info("工单文件不存在，将从空开始: %s", self.path)
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # 演示环境里容错优先：坏文件不阻断启动，改名留证据
            broken = self.path.with_name(f"{self.path.stem}.broken-{datetime.now():%Y%m%d%H%M%S}.json")
            logger.warning("工单文件解析失败(%s)，已改名为 %s 并重新开始", exc, broken.name)
            try:
                self.path.replace(broken)
            except OSError:
                pass
            return

        records = raw.get("tickets", []) if isinstance(raw, dict) else raw
        for item in records:
            try:
                record = TicketRecord(**item)
            except Exception as exc:  # 单条脏数据不影响其他工单
                logger.warning("跳过无法解析的工单: %s (%s)", item, exc)
                continue
            self._tickets[record.id] = record
        logger.info("已加载 %d 张工单: %s", len(self._tickets), self.path)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _now(),
            "tickets": [record.model_dump() for record in self._tickets.values()],
        }
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)  # 原子替换，避免半截文件

    def _next_id(self) -> str:
        return next_ticket_id(self._tickets)

    # ---------------- 读 ----------------
    def get(self, ticket_id: str) -> TicketRecord | None:
        return self._tickets.get(ticket_id.strip().upper())

    def list(
        self,
        *,
        status: str | None = None,
        contact: str | None = None,
        limit: int | None = 20,
    ) -> list[TicketRecord]:
        records = sorted(self._tickets.values(), key=lambda r: r.created_at, reverse=True)
        if status:
            records = [r for r in records if r.status == status]
        if contact:
            key = contact.strip().lower()
            records = [r for r in records if key in r.contact.lower()]
        return records[:limit] if limit else records

    def count(self) -> int:
        return len(self._tickets)

    # ---------------- 写 ----------------
    def create(self, payload: TicketCreate, *, source: str = "agent") -> tuple[TicketRecord, bool]:
        """建单。返回 (工单, 是否命中了重复建单)。

        同一个联系人 + 同标题 + 未关闭，视为重复建单：不新建，直接返回已有工单，
        免得模型多轮重复调用把工单表刷爆。
        """
        with self._lock:
            existing = duplicate_of(list(self._tickets.values()), payload)
            if existing is not None:
                return existing, True

            now = _now()
            record = TicketRecord(
                id=self._next_id(),
                status="待受理",
                source=source,
                created_at=now,
                updated_at=now,
                events=[
                    TicketEvent(at=now, action="创建工单", note=payload.description[:120], actor=source)
                ],
                **payload.model_dump(),
            )
            self._tickets[record.id] = record
            self._save()
            logger.info("新建工单 %s [%s/%s]", record.id, record.category, record.priority)
            return record, False

    def add_event(
        self,
        ticket_id: str,
        action: str,
        *,
        note: str = "",
        actor: str = "agent",
        status: str | None = None,
    ) -> TicketRecord | None:
        """追加时间线，可选同时改状态（催单、补充信息、转人工都走这里）。"""
        with self._lock:
            record = self._tickets.get(ticket_id.strip().upper())
            if record is None:
                return None
            if status is not None:
                validate_status(status)

            now = _now()
            record.events.append(TicketEvent(at=now, action=action, note=note, actor=actor))
            record.updated_at = now
            if status is not None:
                record.status = status
            self._save()
            return record
