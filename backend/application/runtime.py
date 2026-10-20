"""运行时装配：把基础设施层的实现拼成一份可用的运行时。

这个文件只做装配，不含任何业务动作与 HTTP 逻辑：
    create_runtime()    调用各工厂，组装 LLM / 工具 / 检索 / 记忆 / 工单存储 / 图
    AgentRuntime        持有装配结果，供用例层与接口层取用（describe() 用来说清装配了什么）

「一轮对话怎么跑」在 application/chat/service.py，「建单/催单/转人工」在
application/tickets/service.py——它们只依赖这里产出的对象。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.application.agent import build_graph, create_tools
from backend.application.knowledge import KnowledgeService
from backend.application.orders import OrderService
from backend.application.tickets import TicketService
from backend.infrastructure.config import settings
from backend.infrastructure.llm import create_llm
from backend.infrastructure.memory import create_checkpointer
from backend.infrastructure.observability import MetricsCollector
from backend.infrastructure.persistence import create_ticket_store
from backend.infrastructure.persistence.factory import create_knowledge_catalog, create_order_store
from backend.infrastructure.retrieval import create_retriever

logger = logging.getLogger("qa_ticket.runtime")


@dataclass
class AgentRuntime:
    """一次进程启动内共享的 Agent 运行时（装配结果的持有者）。"""

    graph: Any
    llm: Any
    tickets: TicketService
    metrics: MetricsCollector
    orders: OrderService
    knowledge: KnowledgeService
    tools: list[Any] = field(default_factory=list)
    retriever: Any | None = None
    checkpointer: Any | None = None
    store: Any | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
            "model": settings.llm_model or "",
            "tools": [getattr(tool, "name", str(tool)) for tool in self.tools],
            "tickets": self.tickets.count(),
            "orders": self.orders.count(),
            "kb_articles": self.knowledge.count(),
            "kb_documents": self.retriever.document_count() if hasattr(self.retriever, "document_count") else 0,
            "kb_chunks": self.retriever.chunk_count() if hasattr(self.retriever, "chunk_count") else 0,
            "checkpointer": settings.checkpointer if self.checkpointer else None,
            "retriever": settings.retriever if self.retriever else None,
            "ticket_store": settings.ticket_store if self.store else None,
        }


def create_runtime() -> AgentRuntime:
    """按当前配置装配运行时。

    装配顺序即依赖顺序：存储 → 工单用例 → 工具 → 图 → 运行时。
    """
    llm = create_llm()
    checkpointer = create_checkpointer()
    store = create_ticket_store()
    tickets = TicketService(store)
    metrics = MetricsCollector()
    orders = OrderService(create_order_store())
    knowledge = KnowledgeService(create_knowledge_catalog())
    # 对话侧只暴露订单查询；售后工单不再进入 Agent（代码保留，可通过 include_tickets=True 恢复）
    tools = create_tools(tickets, orders, include_tickets=False)
    retriever = create_retriever()

    graph = build_graph(
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        order_service=orders,
    )
    logger.info(
        "Agent 运行时装配完成: %s",
        {
            "provider": settings.llm_provider,
            "tools": [getattr(tool, "name", str(tool)) for tool in tools],
            "checkpointer": settings.checkpointer,
            "retriever": settings.retriever if retriever else None,
            "kb_chunks": retriever.chunk_count() if hasattr(retriever, "chunk_count") else 0,
            "ticket_store": settings.ticket_store,
            "tickets": store.count(),
        },
    )
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tickets=tickets,
        metrics=metrics,
        orders=orders,
        knowledge=knowledge,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
    )
