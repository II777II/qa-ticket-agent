"""接口层数据结构：HTTP 请求体 + SSE 事件。

SSE 事件名固定成下面这几类，前端 streamChat 按事件名分发；
阶段二、四新增「工具」「引用」「建单」事件时，前端只需要多写一个 case。
"""

from __future__ import annotations

import json
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

EVENT_START = "start"          # 一轮开始（带头像信息：用的哪个模型、是否演示模式）
EVENT_TOKEN = "token"          # 自然语言增量
EVENT_TOOL = "tool"            # 阶段二：工具调用与返回
EVENT_CITATION = "citation"    # 阶段四：RAG 引用出处
EVENT_TICKET = "ticket"        # 阶段二：建单结果
EVENT_DONE = "done"            # 一轮结束
EVENT_ERROR = "error"          # 出错（前端据此展示兜底提示）


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="用户这一轮说的话")
    thread_id: str = Field(default="default", description="会话 ID，短期记忆按它隔离")
    user_id: str | None = Field(default=None, description="工单联系人标识，阶段二使用")


class HealthResponse(BaseModel):
    status: str
    provider: str
    mock: bool
    checkpointer: str | None = None
    retriever: str | None = None
    ticket_store: str | None = None


class AgentInfoResponse(HealthResponse):
    """给前端「Agent 配置」面板用：展示当前 POC 开了哪些能力。"""

    model: str = ""
    rag_top_k: int = 0
    tickets: int = 0
    kb_documents: int = 0
    kb_chunks: int = 0
    extensions: list[str] = Field(default_factory=list)


def sse(event: str, data: dict[str, Any]) -> str:
    """把一次事件编码成 SSE 报文。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class CitationPayload(BaseModel):
    """citation 事件的载荷：模型这句回答的依据来自哪篇文档的哪一小节。"""

    index: int = Field(description="回答里的标注编号，如 [1]")
    source: str = Field(description="文件名，如 vpn-691.md")
    title: str = Field(description="小节标题")
    snippet: str = Field(default="", description="命中片段前 160 字，供前端悬浮展示")
    score: float | None = Field(default=None, description="检索打分，调参时看它")


# ------------------------------------------------------------------
# 工单模型
#
# 分类和优先级用 Literal 声明：它们会变成工具参数 JSON Schema 里的 enum，
# 模型想编个「服务器坏了」这种分类时会被挡在校验层，不会写进工单。
# ------------------------------------------------------------------

TicketCategory = Literal["账号与权限", "网络与VPN", "办公设备", "邮件与协作", "业务系统", "其他"]
TicketPriority = Literal["紧急", "高", "中", "低"]
TicketStatus = Literal["待受理", "处理中", "待用户确认", "已关闭"]

TICKET_CATEGORIES: tuple[str, ...] = get_args(TicketCategory)
TICKET_PRIORITIES: tuple[str, ...] = get_args(TicketPriority)
TICKET_STATUSES: tuple[str, ...] = get_args(TicketStatus)


class TicketEvent(BaseModel):
    """工单时间线的一条记录：建单、补充信息、催单、转人工都落这里。"""

    at: str
    action: str
    note: str = ""
    actor: str = "agent"


class TicketCreate(BaseModel):
    """建单入参（也是 create_ticket 工具的参数 schema）。"""

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
        description="联系人（工号或邮箱），工程师据此回访；用户没给就先用工具前追问",
    )


class TicketRecord(TicketCreate):
    """落库后的完整工单。"""

    id: str
    status: TicketStatus = "待受理"
    source: str = "agent"
    created_at: str
    updated_at: str
    events: list[TicketEvent] = Field(default_factory=list)
