"""工单领域实体（纯数据，不含存取逻辑）。

`TicketCreate` 是用户确认后提交售后业务时使用的领域输入模型。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.rules import INITIAL_STATUS, TicketCategory, TicketPriority, TicketStatus


class TicketEvent(BaseModel):
    """工单时间线的一条记录：建单、补充信息、催单、转人工都落这里。"""

    at: str
    action: str
    note: str = ""
    actor: str = "agent"


class TicketCreate(BaseModel):
    """售后业务提交入参。"""

    title: str = Field(
        min_length=4,
        max_length=60,
        description="一句话概括问题，例：无法连接 VPN 报错 691",
    )
    description: str = Field(
        min_length=10,
        description="现象、影响范围、已尝试的操作、报错原文；不要写「同上」这类指代",
    )
    category: TicketCategory = Field(description="工单分类")
    priority: TicketPriority = Field(
        description="紧急=业务中断或影响全员，高=影响多人/部门，中=单人受阻，低=咨询或优化建议"
    )
    contact: str = Field(
        min_length=2,
        description="联系人（手机号/邮箱/会员号），售后专员据此回访；用户没给就先追问",
    )


class TicketRecord(TicketCreate):
    """落库后的完整工单。"""

    id: str
    status: TicketStatus = INITIAL_STATUS
    source: str = "agent"
    created_at: str
    updated_at: str
    events: list[TicketEvent] = Field(default_factory=list)
