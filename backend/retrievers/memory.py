"""进程内检索：把知识库文档切块，用「中文 bigram + 英文单词」词频打分取 top_k。

为什么不用向量库/嵌入模型：POC 要的是「不联网、不装额外依赖、结果可解释」。
关键词打分在 IT 服务台这种术语集中的场景够用（VPN、691、驱动、SLA 都是强特征词），
而且命中哪一段、为什么命中一清二楚，演示时好讲。

想验证它的短板也很容易：换个说法（同义词）就可能检不到——这正是生产环境要上
嵌入向量 + 混合检索 + 重排的原因。
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, PrivateAttr

CONTEXT_HEADER = "【参考资料】"
CONTEXT_FOOTER = "【参考资料结束】"

SUPPORTED_SUFFIXES = {".md", ".txt"}
LATIN_WORD = re.compile(r"[a-zA-Z0-9_]{2,}")
CJK = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> list[str]:
    """粗粒度分词：英文按单词，中文按二元组（不需要 jieba 之类的依赖）。"""
    lowered = text.lower()
    result = LATIN_WORD.findall(lowered)
    cjk_chars = "".join(CJK.findall(lowered))
    result.extend(cjk_chars[i : i + 2] for i in range(max(len(cjk_chars) - 1, 0)))
    if len(cjk_chars) == 1:
        result.append(cjk_chars)
    return result


def _split_sections(path: Path) -> list[tuple[str, str]]:
    """按 Markdown 二级标题切小节；没有二级标题的按空行切段。

    一级标题（# xxx）当作文档标题，标题与首个二级标题之间的「更新日期 / 维护」
    这类元信息直接丢掉——它们对检索没价值，留着只会挤掉正文占一个引用位。
    """
    text = path.read_text(encoding="utf-8").strip()
    sections: list[tuple[str, str]] = []
    doc_title = path.stem
    current_title: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_title is None:
            return
        body = "\n".join(buffer).strip()
        if body:
            title = doc_title if current_title == doc_title else f"{doc_title} · {current_title}"
            sections.append((title, body))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            buffer = []
            current_title = stripped[3:].strip() or current_title
            continue
        if stripped.startswith("# ") and current_title is None and not buffer:
            doc_title = stripped[2:].strip() or doc_title
            continue
        if current_title is not None:
            buffer.append(line)
    flush()

    if not sections:  # 纯文本、没有二级标题时退化成按空行切段
        blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
        sections = [(doc_title, block) for block in blocks]
    return sections


class _Chunk:
    __slots__ = ("source", "title", "text", "tokens", "length")

    def __init__(self, source: str, title: str, text: str) -> None:
        self.source = source
        self.title = title
        self.text = text
        self.tokens = _tokens(f"{title} {text}")
        self.length = max(len(self.tokens), 1)


class InMemoryRetriever(BaseRetriever):
    """LangChain 标准的 BaseRetriever 实现，可被 retriever.invoke(query) 调用。"""

    docs_dir: Path = Field(description="知识库目录")
    top_k: int = Field(default=3, description="返回片段数")
    min_score: float = Field(default=0.08, description="低于这个分数视为没检到")

    _chunks: list[_Chunk] = PrivateAttr(default_factory=list)
    _idf: dict[str, float] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self._load()

    # ---------------- 加载与索引 ----------------
    def _load(self) -> None:
        if not self.docs_dir.exists():
            return
        for path in sorted(self.docs_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if path.name.lower() == "readme.md":  # 目录说明不算知识
                continue
            for title, body in _split_sections(path):
                self._chunks.append(_Chunk(path.name, title, body))

        # 逆文档频率：命中「VPN」比对「的」更有信息量
        total = len(self._chunks)
        df: dict[str, int] = {}
        for chunk in self._chunks:
            for token in set(chunk.tokens):
                df[token] = df.get(token, 0) + 1
        self._idf = {token: math.log((total + 1) / (count + 0.5)) + 1 for token, count in df.items()}

    @property
    def chunks(self) -> list[_Chunk]:
        return self._chunks

    def document_count(self) -> int:
        return len({chunk.source for chunk in self._chunks})

    def chunk_count(self) -> int:
        return len(self._chunks)

    # ---------------- 检索 ----------------
    def _score(self, query_tokens: list[str], chunk: _Chunk) -> float:
        if not query_tokens:
            return 0.0
        counts: dict[str, int] = {}
        for token in chunk.tokens:
            counts[token] = counts.get(token, 0) + 1

        score = 0.0
        for token in set(query_tokens):
            tf = counts.get(token, 0)
            if not tf:
                continue
            idf = self._idf.get(token, 1.0)
            score += idf * (1 + math.log(tf))
        # 除以长度平方根，避免长小节靠「词多」占便宜
        return score / math.sqrt(chunk.length)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        query_tokens = _tokens(query)
        scored = [(self._score(query_tokens, chunk), chunk) for chunk in self._chunks]
        scored = [(score, chunk) for score, chunk in scored if score >= self.min_score]
        scored.sort(key=lambda item: item[0], reverse=True)

        documents: list[Document] = []
        for rank, (score, chunk) in enumerate(scored[: self.top_k], start=1):
            documents.append(
                Document(
                    page_content=chunk.text,
                    metadata={
                        "index": rank,
                        "source": chunk.source,
                        "title": chunk.title,
                        "score": round(score, 4),
                    },
                )
            )
        return documents


def format_context(documents: list[Document]) -> str:
    """拼成给模型看的参考资料块。mock 模型也会读这个块，所以格式要稳定。"""
    lines = [CONTEXT_HEADER]
    for position, document in enumerate(documents, start=1):
        metadata = document.metadata
        lines.append(f"[{position}] {metadata.get('source')} · {metadata.get('title')}")
        lines.append(document.page_content.strip())
        lines.append("")
    lines.append(CONTEXT_FOOTER)
    return "\n".join(lines)
