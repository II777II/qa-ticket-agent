"""检索用例：加载、切块、命中、阈值、排序、参考资料格式。"""

from __future__ import annotations

from pathlib import Path

from backend.infrastructure.config import settings
from backend.infrastructure.retrieval.in_memory import (
    CONTEXT_FOOTER,
    CONTEXT_HEADER,
    _split_sections,
    format_context,
)


def test_loads_all_kb_documents(retriever) -> None:
    """5 篇知识库文档全部入库，且都能切出片段。"""
    assert retriever.document_count() == 5
    assert retriever.chunk_count() >= 10


def test_chunking_drops_document_metadata() -> None:
    """`# 标题` 当文档名，`## 小节` 才切片；「更新日期/维护」这类元信息不该成为片段。"""
    sections = _split_sections(settings.kb_dir / "vpn-691.md")
    titles = [title for title, _ in sections]
    assert all("更新日期" not in title for title in titles)
    assert any(title.endswith("常见错误码含义") for title in titles)


def test_hits_vpn_document(retriever) -> None:
    """提问里的错误码与关键词能命中对应文档，且排第一。"""
    documents = retriever.invoke("VPN 连不上，提示 691 错误怎么办")
    assert documents
    assert documents[0].metadata["source"] == "vpn-691.md"
    assert documents[0].metadata["index"] == 1


def test_hits_account_document(retriever) -> None:
    documents = retriever.invoke("域账号被锁了怎么解锁")
    sources = [document.metadata["source"] for document in documents]
    assert "account-password.md" in sources


def test_respects_top_k(retriever) -> None:
    documents = retriever.invoke("打印机驱动装不上，邮箱容量也不够")
    assert len(documents) <= retriever.top_k


def test_scores_are_descending(retriever) -> None:
    documents = retriever.invoke("邮箱容量满了收不到信")
    scores = [document.metadata["score"] for document in documents]
    assert scores == sorted(scores, reverse=True)


def test_unrelated_question_returns_nothing(retriever) -> None:
    """低于阈值就当作没检到——宁可不给资料，也别塞一段无关内容给模型。"""
    assert retriever.invoke("今天午饭吃什么比较好") == []


def test_context_block_format(retriever) -> None:
    documents = retriever.invoke("VPN 报错 809 是什么原因")
    context = format_context(documents)
    assert context.startswith(CONTEXT_HEADER)
    assert context.rstrip().endswith(CONTEXT_FOOTER)
    assert "[1]" in context and "vpn-691.md" in context


def test_empty_dir_degrades_to_no_chunks(tmp_path: Path) -> None:
    """知识库目录为空时不该报错，只是检不到（工厂会据此降级为不检索）。"""
    from backend.infrastructure.retrieval.in_memory import InMemoryRetriever

    empty = InMemoryRetriever(docs_dir=tmp_path, top_k=3)
    assert empty.chunk_count() == 0
    assert empty.invoke("VPN 连不上") == []
