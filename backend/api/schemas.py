"""接口层数据结构：HTTP 请求体与响应体。

事件名本身（start / intent / token / order / service_draft / citation / done / error）定义在
application/contracts/chat_events.py；SSE 报文由 FastAPI 内置 EventSourceResponse 与
ServerSentEvent 编码。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.domain.intent import ServiceType
from backend.domain.rules import TicketCategory, TicketPriority


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
    orders: int = 0
    kb_articles: int = 0
    kb_documents: int = 0
    kb_chunks: int = 0
    git_sha: str = ""
    git_date: str = ""
    extensions: list[str] = Field(default_factory=list)


class CitationPayload(BaseModel):
    """citation 事件的载荷：模型这句回答的依据来自哪篇文档的哪一小节。"""

    index: int = Field(description="回答里的标注编号，如 [1]")
    source: str = Field(description="文件名，如 vpn-691.md")
    title: str = Field(description="小节标题")
    snippet: str = Field(default="", description="命中片段前 160 字，供前端悬浮展示")
    score: float | None = Field(default=None, description="检索打分，调参时看它")


class KnowledgeHit(BaseModel):
    """知识库检索面板的一条命中（与 citation 事件同源）。"""

    index: int
    source: str
    title: str
    snippet: str = ""
    score: float | None = None
    coverage: float | None = None


class ServiceConfirmRequest(BaseModel):
    """用户在前端业务办理面板确认后的提交载荷。"""

    order_no: str = Field(pattern=r"^SO\d{12}$", description="关联订单号")
    contact: str = Field(min_length=2, max_length=120, description="回访联系人")
    service_type: ServiceType = Field(description="退货、换货、维修等业务类型")
    category: TicketCategory = Field(description="售后工单分类")
    priority: TicketPriority = Field(default="中", description="业务优先级")
    description: str = Field(min_length=10, max_length=2000, description="用户确认后的问题描述")


class ServiceConfirmResponse(BaseModel):
    ok: bool = True
    ticket_id: str
    status: str
    duplicated: bool = False
    message: str = ""


class MetricsKpi(BaseModel):
    requests: int = 0
    tokens: int = 0
    avg_first_token_ms: float = 0.0
    p95_first_token_ms: int = 0
    avg_latency_ms: float = 0.0
    error_rate: float = 0.0


class DayMetric(BaseModel):
    date: str
    requests: int = 0
    tokens: int = 0
    avg_latency_ms: float = 0.0


class ModelMetric(BaseModel):
    model: str
    calls: int = 0
    tokens: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 100.0


class IntentMetric(BaseModel):
    intent: str
    calls: int = 0
    tokens: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 100.0


class MetricsSummary(BaseModel):
    """后台管理页的数据源：KPI + 按天趋势 + 按模型明细。"""

    days: int = 7
    generated_at: str = ""
    kpis: MetricsKpi = Field(default_factory=MetricsKpi)
    by_day: list[DayMetric] = Field(default_factory=list)
    by_model: list[ModelMetric] = Field(default_factory=list)
    by_intent: list[IntentMetric] = Field(default_factory=list)


# 工单实体与业务规则已下沉到领域层（backend/domain/）：
#   实体  -> backend.domain.models
#   规则  -> backend.domain.rules
# 本模块只保留接口层 DTO 与 SSE 事件定义。
