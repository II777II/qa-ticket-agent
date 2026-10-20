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
    """电商帮助中心 50 篇 HTML 全部入库，每篇按 h2 切出至少两个片段。"""
    assert retriever.document_count() == 50
    assert retriever.chunk_count() >= 100


def test_chunking_drops_document_metadata() -> None:
    """HTML 按 <h2> 切块，标题取 <title>，正文去标签。"""
    sections = _split_sections(settings.kb_dir / "KB-EC-0020.html")
    titles = [title for title, _ in sections]
    assert any("退款多久到账" in title for title in titles)
    assert any("操作步骤" in title for title in titles)
    assert all("<" not in body for _, body in sections)


def test_hits_refund_article(retriever) -> None:
    """退款问题命中对应 HTML 文章，且排第一。"""
    documents = retriever.invoke("退款多久到账")
    assert documents
    assert documents[0].metadata["source"] == "KB-EC-0020.html"
    assert documents[0].metadata["index"] == 1


def test_hits_coupon_article(retriever) -> None:
    documents = retriever.invoke("优惠券为什么不能用")
    sources = [document.metadata["source"] for document in documents]
    assert "KB-EC-0007.html" in sources


def test_respects_top_k(retriever) -> None:
    documents = retriever.invoke("退货退款和发票怎么处理")
    assert len(documents) <= retriever.top_k


def test_scores_are_descending(retriever) -> None:
    documents = retriever.invoke("退款多久到账，怎么开票")
    scores = [document.metadata["score"] for document in documents]
    assert scores == sorted(scores, reverse=True)


def test_unrelated_question_returns_nothing(retriever) -> None:
    """低于阈值就当作没检到——宁可不给资料，也别塞一段无关内容给模型。"""
    assert retriever.invoke("今天午饭吃什么比较好") == []


def test_context_block_format(retriever) -> None:
    documents = retriever.invoke("退款多久到账")
    context = format_context(documents)
    assert context.startswith(CONTEXT_HEADER)
    assert context.rstrip().endswith(CONTEXT_FOOTER)
    assert "[1]" in context and "KB-EC-0020.html" in context


def test_empty_dir_degrades_to_no_chunks(tmp_path: Path) -> None:
    """知识库目录为空时不该报错，只是检不到（工厂会据此降级为不检索）。"""
    from backend.infrastructure.retrieval.in_memory import InMemoryRetriever

    empty = InMemoryRetriever(docs_dir=tmp_path, top_k=3)
    assert empty.chunk_count() == 0
    assert empty.invoke("VPN 连不上") == []
