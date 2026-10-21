"""运行时装配：把模型、检索、存储、Agent 和可观测性拼成一份运行时。"""

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
from backend.infrastructure.observability import (
    LangfuseTracing,
    MetricsCollector,
    create_langfuse_tracing,
)
from backend.infrastructure.persistence import (
    create_knowledge_catalog,
    create_order_store,
    create_ticket_store,
)
from backend.infrastructure.retrieval import create_retriever

logger = logging.getLogger("qa_ticket.runtime")


@dataclass
class AgentRuntime:
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
    tracing: LangfuseTracing | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
            "model": settings.llm_model,
            "tools": [tool.name for tool in self.tools],
            "tickets": self.tickets.count(),
            "orders": self.orders.count(),
            "kb_articles": self.knowledge.count(),
            "kb_documents": getattr(self.retriever, "document_count", lambda: 0)(),
            "kb_chunks": getattr(self.retriever, "chunk_count", lambda: 0)(),
            "checkpointer": settings.checkpointer if self.checkpointer else None,
            "retriever": settings.retriever if self.retriever else None,
            "ticket_store": settings.ticket_store if self.store else None,
            "langfuse": self.tracing.status if self.tracing else "disabled",
        }

    def shutdown(self) -> None:
        if self.tracing:
            self.tracing.shutdown()


def create_runtime() -> AgentRuntime:
    llm = create_llm()
    checkpointer = create_checkpointer()
    store = create_ticket_store()
    orders = OrderService(create_order_store())
    knowledge = KnowledgeService(create_knowledge_catalog())
    retriever = create_retriever()
    tools = create_tools(orders)
    tracing = create_langfuse_tracing()
    graph = build_graph(
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        order_service=orders,
    )
    logger.info(
        "运行时就绪 provider=%s tools=%s chunks=%s",
        settings.llm_provider,
        [tool.name for tool in tools],
        getattr(retriever, "chunk_count", lambda: 0)(),
    )
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tickets=TicketService(store),
        metrics=MetricsCollector(),
        orders=orders,
        knowledge=knowledge,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
        tracing=tracing,
    )
