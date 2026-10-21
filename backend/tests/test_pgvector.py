"""Offline tests for the LangChain PGVector adapter."""

from __future__ import annotations

from dataclasses import replace

from langchain_core.documents import Document

import backend.infrastructure.vector_store as vector_store


class _Store:
    def similarity_search_with_score(self, _query: str, k: int):
        assert k == 2
        return [(Document(page_content="退款规则", metadata={"source": "KB-EC-0020.html", "title": "退款"}), 0.2)]


def test_mock_embeddings_respect_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(vector_store, "settings", replace(
        vector_store.settings,
        embedding_provider="mock",
        embedding_dimensions=8,
    ))
    assert len(vector_store.create_embeddings().embed_query("退款")) == 8


def test_pgvector_retriever_maps_scores_and_metadata() -> None:
    retriever = vector_store.PgVectorRetriever(
        store=_Store(),
        engine=None,
        collection_name="test",
        top_k=2,
    )
    documents = retriever.invoke("退款多久到账")
    assert documents[0].metadata == {
        "source": "KB-EC-0020.html",
        "title": "退款",
        "index": 1,
        "score": 0.8,
    }


def test_database_url_normalizes_psycopg_driver(monkeypatch) -> None:
    monkeypatch.setattr(vector_store, "settings", replace(
        vector_store.settings,
        database_url="postgresql://user:pass@db:5432/kb",
    ))
    assert vector_store._database_url() == "postgresql+psycopg://user:pass@db:5432/kb"
