"""领域层：业务实体与业务规则。

这一层不知道 FastAPI、LangChain、JSON 文件的存在：

    models.py   工单实体（建单入参、工单记录、时间线事件）
    rules.py    分类/优先级/状态枚举、状态流转校验、重复建单判定、按天单号
    errors.py   领域异常

依赖方向只有一个：上层（application / api）依赖它，它不反向依赖上层。
"""

from backend.domain.errors import DomainError, TicketNotFoundError, UnknownStatusError
from backend.domain.models import TicketCreate, TicketEvent, TicketRecord
from backend.domain.rules import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    duplicate_of,
    is_closed,
    next_ticket_id,
    validate_status,
)

__all__ = [
    "DomainError",
    "TicketNotFoundError",
    "UnknownStatusError",
    "TicketCreate",
    "TicketEvent",
    "TicketRecord",
    "TICKET_CATEGORIES",
    "TICKET_PRIORITIES",
    "TICKET_STATUSES",
    "TicketCategory",
    "TicketPriority",
    "TicketStatus",
    "duplicate_of",
    "is_closed",
    "next_ticket_id",
    "validate_status",
]
