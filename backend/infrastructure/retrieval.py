"""In-process HTML retrieval and reference formatting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Sequence

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, PrivateAttr

from backend.infrastructure.config import settings

CONTEXT_HEADER = "【参考资料】"
CONTEXT_FOOTER = "【参考资料结束】"
LATIN_WORD = re.compile(r"[a-zA-Z0-9_]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]")
STOP_WORDS = {"什么", "怎么", "如何", "可以", "是否", "这个", "那个", "比较", "请问", "帮我"}


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    chars = "".join(CJK.findall(lowered))
    result = set(LATIN_WORD.findall(lowered))
    result.update(chars[i:i + 2] for i in range(max(len(chars) - 1, 0)))
    if len(chars) == 1:
        result.add(chars)
    return result - STOP_WORDS


def _html_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?is)<(br|/p|/div|/li|/h\d)[^>]*>", "\n", fragment)
    text = unescape(re.sub(r"(?s)<[^>]+>", " ", fragment))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _split_sections(path: Path) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"<title>(.*?)</title>", raw, flags=re.S | re.I)
    title = unescape(title_match.group(1)).split(" - ")[0].strip() if title_match else path.stem
    parts = re.split(r"(?is)<h2[^>]*>(.*?)</h2>", raw)
    if len(parts) == 1:
        body = _html_text(parts[0])
        return [(title, body)] if body else []
    sections = []
    for index in range(1, len(parts), 2):
        heading = _html_text(parts[index])
        body = _html_text(parts[index + 1] if index + 1 < len(parts) else "")
        if body:
            sections.append((f"{title} · {heading}" if heading else title, body))
    return sections


@dataclass(slots=True)
class _Chunk:
    source: str
    title: str
    text: str
    tokens: set[str]
    title_tokens: set[str]


class InMemoryRetriever(BaseRetriever):
    docs_dir: Path = Field()
    top_k: int = Field(default=3)
    _chunks: list[_Chunk] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.docs_dir.is_dir():
            return
        for path in sorted(self.docs_dir.glob("*.html")):
            if path.name.lower() == "index.html":
                continue
            for title, text in _split_sections(path):
                self._chunks.append(
                    _Chunk(path.name, title, text, _tokens(f"{title} {text}"), _tokens(title))
                )

    def document_count(self) -> int:
        return len({chunk.source for chunk in self._chunks})

    def chunk_count(self) -> int:
        return len(self._chunks)

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
        query_tokens = _tokens(query)
        scored = []
        for chunk in self._chunks:
            hits = len(query_tokens & chunk.tokens)
            if hits:
                scored.append((float(hits + 2 * len(query_tokens & chunk.title_tokens)), chunk))
        scored.sort(key=lambda item: (-item[0], item[1].source, item[1].title))
        return [
            Document(
                page_content=chunk.text,
                metadata={"index": index, "source": chunk.source, "title": chunk.title, "score": score},
            )
            for index, (score, chunk) in enumerate(scored[:max(limit, 0)], 1)
        ]


def format_context(documents: Sequence[Document]) -> str:
    lines = [CONTEXT_HEADER]
    for index, document in enumerate(documents, 1):
        lines.extend([
            f"[{index}] {document.metadata.get('source', '')} · {document.metadata.get('title', '')}",
            document.page_content.strip(),
            "",
        ])
    lines.append(CONTEXT_FOOTER)
    return "\n".join(lines)


def create_retriever() -> BaseRetriever | None:
    if settings.retriever == "memory":
        retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
        return retriever if retriever.chunk_count() else None
    if settings.retriever == "pgvector":
        from backend.infrastructure.vector_store import create_pgvector_retriever

        return create_pgvector_retriever()
    raise ValueError(f"未知的 RETRIEVER: {settings.retriever!r}")
