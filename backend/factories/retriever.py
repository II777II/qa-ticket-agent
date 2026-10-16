"""检索工厂：按 RETRIEVER 创建检索器。

知识库目录为空时返回 None——图里就不做检索注入，也不会产生「未命中」的空引用。
"""

from __future__ import annotations

import logging

from langchain_core.retrievers import BaseRetriever

from backend.config import settings
from backend.retrievers.memory import InMemoryRetriever

logger = logging.getLogger("qa_ticket.factory.retriever")


def create_retriever() -> BaseRetriever | None:
    kind = settings.retriever

    if kind == "memory":
        retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
        if retriever.chunk_count() == 0:
            logger.warning("知识库目录里没有可用文档，RAG 降级为「不检索」: %s", settings.kb_dir)
            return None
        logger.info(
            "知识库已加载: %d 篇文档 / %d 个片段 (%s)",
            retriever.document_count(),
            retriever.chunk_count(),
            settings.kb_dir,
        )
        return retriever

    if kind == "pgvector":
        raise NotImplementedError(
            "RETRIEVER=pgvector 尚未接入：需要先装 langchain-postgres，"
            "并在 docker/docker-compose.yml 里打开 pgvector 服务、填好 DATABASE_URL。"
        )

    raise ValueError(f"未知的 RETRIEVER: {kind!r}，可选 memory / pgvector")
