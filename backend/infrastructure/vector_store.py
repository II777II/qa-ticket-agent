"""LangChain PGVector store and retriever adapter."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings
from langchain_core.retrievers import BaseRetriever
from sqlalchemy import create_engine, text

from backend.infrastructure.config import settings

logger = logging.getLogger("qa_ticket.retriever")


def create_embeddings() -> Embeddings:
    if settings.embedding_provider == "mock":
        return DeterministicFakeEmbedding(size=settings.embedding_dimensions)
    if settings.embedding_provider == "openai":
        if not settings.embedding_api_key:
            raise RuntimeError("EMBEDDING_PROVIDER=openai 需要 EMBEDDING_API_KEY")
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url or None,
        )
    raise ValueError(f"未知的 EMBEDDING_PROVIDER: {settings.embedding_provider!r}")


def _database_url() -> str:
    url = settings.database_url.strip()
    if not url:
        raise RuntimeError("RETRIEVER=pgvector 需要 DATABASE_URL")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL 必须使用 postgresql:// 或 postgresql+psycopg://")
    return url


def create_pgvector_store(*, pre_delete_collection: bool = False):
    from langchain_postgres import PGVector

    engine = create_engine(_database_url(), pool_pre_ping=True)
    store = PGVector(
        embeddings=create_embeddings(),
        connection=engine,
        collection_name=settings.pgvector_collection,
        embedding_length=settings.embedding_dimensions,
        pre_delete_collection=pre_delete_collection,
        use_jsonb=True,
        create_extension=True,
    )
    return store, engine


class PgVectorRetriever(BaseRetriever):
    store: Any
    engine: Any
    collection_name: str
    top_k: int = 3

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        return self._rank(query, self.top_k)

    def search(self, query: str, top_k: int | None = None) -> list[Document]:
        return self._rank(query, top_k or self.top_k)

    def _rank(self, query: str, limit: int) -> list[Document]:
        matches = self.store.similarity_search_with_score(query, k=max(limit, 0))
        return [
            Document(
                page_content=document.page_content,
                metadata={
                    **document.metadata,
                    "index": index,
                    "score": round(1 - float(distance), 4),
                },
            )
            for index, (document, distance) in enumerate(matches, 1)
        ]

    def _count(self, expression: str) -> int:
        with self.engine.connect() as connection:
            value = connection.execute(text(
                f"""
                SELECT {expression}
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON c.uuid = e.collection_id
                WHERE c.name = :collection
                """
            ), {"collection": self.collection_name}).scalar()
        return int(value or 0)

    def document_count(self) -> int:
        return self._count("COUNT(DISTINCT e.cmetadata->>'source')")

    def chunk_count(self) -> int:
        return self._count("COUNT(*)")

    def close(self) -> None:
        self.engine.dispose()


def create_pgvector_retriever() -> PgVectorRetriever | None:
    store, engine = create_pgvector_store()
    retriever = PgVectorRetriever(
        store=store,
        engine=engine,
        collection_name=settings.pgvector_collection,
        top_k=settings.rag_top_k,
    )
    if retriever.chunk_count() == 0:
        logger.warning("pgvector 知识库为空，请先运行 ingest_pgvector")
        retriever.close()
        return None
    return retriever
