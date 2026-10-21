"""Runtime composition, model switching and fixed evaluation cases."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from backend.application.graph import build_graph
from backend.domain.core import is_order_query, rule_classify
from backend.infrastructure.config import EVAL_CASES_FILE, LLM_MODELS, settings
from backend.infrastructure.llm import create_checkpointer, create_llm
from backend.infrastructure.observability import LangfuseTracing, MetricsCollector, create_langfuse_tracing
from backend.infrastructure.retrieval import create_retriever
from backend.infrastructure.storage import create_knowledge_catalog, create_order_store, create_ticket_store


@dataclass
class AgentRuntime:
    graph: Any
    llm: Any
    tickets: Any
    metrics: MetricsCollector
    orders: Any
    knowledge: Any
    retriever: Any | None = None
    checkpointer: Any | None = None
    store: Any | None = None
    tracing: LangfuseTracing | None = None
    provider: str = ""
    model: str = ""

    def describe(self) -> dict[str, Any]:
        provider = self.provider or settings.llm_provider
        return {
            "provider": provider,
            "mock": provider == "mock",
            "model": self.model or settings.llm_model,
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
        self.tracing and self.tracing.shutdown()

    def configure_llm(self, llm: Any, provider: str, model: str) -> None:
        self.llm, self.provider, self.model = llm, provider, model
        self.graph = build_graph(
            llm=llm,
            retriever=self.retriever,
            checkpointer=self.checkpointer,
            order_service=self.orders,
        )

    def evaluate(self) -> dict[str, Any]:
        cases = json.loads(EVAL_CASES_FILE.read_text(encoding="utf-8"))
        rows = []
        for case in cases:
            question, expected = case["query"], case["expected_intent"]
            actual = rule_classify(question).intent
            tool = ("order_query" if is_order_query(question) else "knowledge_search") if actual == "read" else None
            source = case.get("expected_source")
            docs = self.retriever.search(question, top_k=3) if source and self.retriever else []
            sources = [doc.metadata.get("source", "") for doc in docs]
            rows.append({
                **case,
                "actual_intent": actual,
                "actual_tool": tool,
                "retrieved_sources": sources,
                "intent_ok": actual == expected,
                "tool_ok": tool == case.get("expected_tool") if case.get("expected_tool") else None,
                "rag_hit": source in sources if source else None,
            })
        rate = lambda values: round(sum(values) / len(values) * 100, 1) if values else 100.0
        return {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "classifier": "rules",
            "total": len(rows),
            "intent_accuracy": rate([row["intent_ok"] for row in rows]),
            "tool_accuracy": rate([row["tool_ok"] for row in rows if row["tool_ok"] is not None]),
            "rag_hit_rate": rate([row["rag_hit"] for row in rows if row["rag_hit"] is not None]),
            "rows": rows,
        }


def create_runtime() -> AgentRuntime:
    llm, checkpointer = create_llm(), create_checkpointer()
    store, orders, knowledge, retriever = (
        create_ticket_store(), create_order_store(), create_knowledge_catalog(), create_retriever(),
    )
    graph = build_graph(
        llm=llm,
        retriever=retriever,
        checkpointer=checkpointer,
        order_service=orders,
    )
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tickets=store,
        metrics=MetricsCollector(),
        orders=orders,
        knowledge=knowledge,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
        tracing=create_langfuse_tracing(),
        provider=settings.llm_provider,
        model=settings.llm_model or LLM_MODELS.get(settings.llm_provider, "mock"),
    )
