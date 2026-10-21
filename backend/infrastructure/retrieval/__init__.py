"""知识检索实现与工厂。"""

from __future__ import annotations

import logging

from langchain_core.retrievers import BaseRetriever

from backend.infrastructure.config import settings
from backend.infrastructure.retrieval.in_memory import (
    InMemoryRetriever,
)


logger = logging.getLogger("qa_ticket.retriever")


def create_retriever() -> BaseRetriever | None:
    if settings.retriever == "memory":
        retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
        if retriever.chunk_count() == 0:
            logger.warning("知识库为空，RAG 降级为不检索")
            return None
        return retriever
    if settings.retriever == "pgvector":
        raise NotImplementedError("RETRIEVER=pgvector 尚未接入")
    raise ValueError(f"未知的 RETRIEVER: {settings.retriever!r}")


__all__ = [
    "create_retriever",
]
