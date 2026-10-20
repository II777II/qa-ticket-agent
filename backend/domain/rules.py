"""工单业务规则：枚举、状态校验、重复判定、按天单号。

规则集中在这里之后，「改一个业务口径只改一处」才成立——此前这三类规则散在
schemas.py（枚举）、stores/json_store.py（去重与状态校验）、tools.py（建单流程）三处。
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Iterable, Literal, Sequence, get_args

from backend.domain.errors import UnknownStatusError

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
TicketStatus = Literal["待受理", "处理中", "待用户确认", "已关闭"]

TICKET_CATEGORIES: tuple[str, ...] = get_args(TicketCategory)
TICKET_PRIORITIES: tuple[str, ...] = get_args(TicketPriority)
TICKET_STATUSES: tuple[str, ...] = get_args(TicketStatus)

CLOSED_STATUS: str = "已关闭"
INITIAL_STATUS: str = "待受理"


def validate_status(status: str) -> str:
    """校验状态取值；非法就抛领域异常，错误文案由领域层统一负责。"""
    if status not in TICKET_STATUSES:
        raise UnknownStatusError(f"未知工单状态: {status!r}，可选 {TICKET_STATUSES}")
    return status


def is_closed(status: str) -> bool:
    return status == CLOSED_STATUS


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
        if record.contact.strip().lower() == contact and record.title.strip() == title and not is_closed(record.status):
            return record
    return None
