"""工单业务规则：分类、优先级、重复判定和按天单号。"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Iterable, Literal, Sequence

if TYPE_CHECKING:  # 只用于类型标注，避免与 models.py 形成运行时循环导入
    from backend.domain.models import TicketCreate, TicketRecord

TicketCategory = Literal[
    "订单与支付",
    "配送与物流",
    "退换与售后",
    "发票与报销",
    "商品与质量",
    "账户与安全",
    "其他",
]
TicketPriority = Literal["紧急", "高", "中", "低"]

def next_ticket_id(existing_ids: Iterable[str], today: date | None = None) -> str:
    """按天递增的单号：`TK-YYYYMMDD-0001`。"""
    prefix = f"TK-{(today or date.today()):%Y%m%d}-"
    used: list[int] = []
    for ticket_id in existing_ids:
        if not ticket_id.startswith(prefix):
            continue
        tail = ticket_id.rsplit("-", 1)[-1]
        if tail.isdigit():
            used.append(int(tail))
    return f"{prefix}{max(used) + 1 if used else 1:04d}"


def duplicate_of(existing: Sequence["TicketRecord"], payload: "TicketCreate") -> "TicketRecord | None":
    """同一个联系人 + 同标题 + 未关闭，视为重复建单。

    这是「防模型多轮重复建单把工单表刷爆」的兜底，规则放在领域层，
    存储实现（JSON / Postgres）只管调用，不用各写一遍。
    """
    contact = payload.contact.strip().lower()
    title = payload.title.strip()
    for record in existing:
        if record.contact.strip().lower() == contact and record.title.strip() == title:
            return record
    return None
