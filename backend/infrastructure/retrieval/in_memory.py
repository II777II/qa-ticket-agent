"""进程内知识检索：HTML 按 h2 切块，关键词命中数排序。"""

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

CONTEXT_HEADER = "【参考资料】"
CONTEXT_FOOTER = "【参考资料结束】"
SUPPORTED_SUFFIXES = {".md", ".txt", ".html"}
LATIN_WORD = re.compile(r"[a-zA-Z0-9_]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]")
STOP_WORDS = {
    "什么",
    "怎么",
    "如何",
    "可以",
    "是否",
    "这个",
    "那个",
    "比较",
    "请问",
    "帮我",
}


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    result = {word for word in LATIN_WORD.findall(lowered) if word not in STOP_WORDS}
    chars = "".join(CJK.findall(lowered))
    result.update(
        token
        for token in (chars[index : index + 2] for index in range(max(len(chars) - 1, 0)))
        if token not in STOP_WORDS
    )
    if len(chars) == 1:
        result.add(chars)
    return result


def _html_text(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?is)<(br|/p|/div|/li|/h\d)[^>]*>", "\n", fragment)
    fragment = re.sub(r"(?s)<[^>]+>", " ", fragment)
    lines = [line.strip() for line in unescape(fragment).splitlines()]
    return "\n".join(line for line in lines if line)


def _split_sections(path: Path) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() != ".html":
        title = path.stem
        blocks = [block.strip() for block in re.split(r"(?m)^##\s+", raw) if block.strip()]
        if len(blocks) == 1:
            return [(title, _html_text(blocks[0]))]
        return [
            (f"{title} · {block.splitlines()[0].strip()}", _html_text(block)) for block in blocks[1:]
        ]

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
    """关键词检索器，接口兼容 LangChain BaseRetriever。"""

    docs_dir: Path = Field(description="知识库目录")
    top_k: int = Field(default=3, description="返回片段数")

    _chunks: list[_Chunk] = PrivateAttr(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.docs_dir.exists():
            return
        for path in sorted(self.docs_dir.rglob("*")):
            if (
                not path.is_file()
                or path.suffix.lower() not in SUPPORTED_SUFFIXES
                or path.name.lower() in {"readme.md", "index.html"}
            ):
                continue
            for title, text in _split_sections(path):
                self._chunks.append(
                    _Chunk(
                        path.name,
                        title,
                        text,
                        _tokens(f"{title} {text}"),
                        _tokens(title),
                    )
                )

    @property
    def chunks(self) -> list[_Chunk]:
        return self._chunks

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
            if hits > 0:
                title_hits = len(query_tokens & chunk.title_tokens)
                scored.append((float(hits + title_hits * 2), chunk))
        scored.sort(key=lambda item: (-item[0], item[1].source, item[1].title))
        return [
            Document(
                page_content=chunk.text,
                metadata={
                    "index": rank,
                    "source": chunk.source,
                    "title": chunk.title,
                    "score": score,
                },
            )
            for rank, (score, chunk) in enumerate(scored[: max(limit, 0)], start=1)
        ]


def format_context(documents: Sequence[Document]) -> str:
    lines = [CONTEXT_HEADER]
    for index, document in enumerate(documents, start=1):
        title = document.metadata.get("title", "")
        source = document.metadata.get("source", "")
        lines.extend([f"[{index}] {source} · {title}", document.page_content.strip(), ""])
    lines.append(CONTEXT_FOOTER)
    return "\n".join(lines)
