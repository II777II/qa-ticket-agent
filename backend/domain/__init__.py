"""领域层：业务实体与业务规则。

这一层不知道 FastAPI、LangChain、JSON 文件的存在：

    models.py   工单实体
    rules.py    分类/优先级、重复建单判定、按天单号

依赖方向只有一个：上层（application / api）依赖它，它不反向依赖上层。
"""

from backend.domain.models import TicketCreate, TicketRecord
from backend.domain.rules import (
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TicketCategory,
    TicketPriority,
    duplicate_of,
    next_ticket_id,
)

__all__ = [
    "TicketCreate",
    "TicketRecord",
    "TICKET_CATEGORIES",
    "TICKET_PRIORITIES",
    "TicketCategory",
    "TicketPriority",
    "duplicate_of",
    "next_ticket_id",
]
