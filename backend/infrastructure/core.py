"""Configuration, JSON adapters, retrieval, models and observability."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from html import unescape
from pathlib import Path
from typing import Any, Iterator, Sequence

from dotenv import load_dotenv
from langchain_core.callbacks import CallbackManagerForLLMRun, CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, PrivateAttr

from backend.domain.core import (
    KnowledgeArticle,
    KnowledgeCategory,
    OrderRecord,
    TicketCreate,
    TicketRecord,
    duplicate_of,
    next_ticket_id,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEMO_DIR = BACKEND_DIR / "data" / "demo" / "ecommerce"
load_dotenv(PROJECT_ROOT / ".env")
CONTEXT_HEADER = "【参考资料】"
CONTEXT_FOOTER = "【参考资料结束】"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _number(name: str, default: int | float, cast):
    try:
        return cast(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    host: str = _env("HOST", "127.0.0.1")
    port: int = _number("PORT", 5179, int)
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(x.strip() for x in _env("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if x.strip())
    )
    llm_provider: str = _env("LLM_PROVIDER", "mock").lower()
    llm_model: str = _env("LLM_MODEL")
    llm_api_key: str = _env("LLM_API_KEY")
    llm_base_url: str = _env("LLM_BASE_URL")
    llm_temperature: float = _number("LLM_TEMPERATURE", 0.2, float)
    llm_timeout: float = _number("LLM_TIMEOUT", 120.0, float)
    checkpointer: str = _env("CHECKPOINTER", "memory").lower()
    retriever: str = _env("RETRIEVER", "memory").lower()
    ticket_store: str = _env("TICKET_STORE", "json").lower()
    order_store: str = _env("ORDER_STORE", "json").lower()
    rag_top_k: int = _number("RAG_TOP_K", 3, int)
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(BACKEND_DIR / "data"))))
    orders_file: Path = field(default_factory=lambda: Path(_env("ORDERS_FILE", str(DEMO_DIR / "orders.json"))))
    kb_root: Path = field(default_factory=lambda: Path(_env("KB_ROOT", str(DEMO_DIR / "kb"))))
    kb_dir: Path = field(default_factory=lambda: Path(_env("KB_DIR", str(DEMO_DIR / "kb" / "pages"))))
    kb_articles_file: Path = field(default_factory=lambda: Path(_env(
        "KB_ARTICLES_FILE", str(DEMO_DIR / "kb" / "articles.json")
    )))
    frontend_dist: Path = field(default_factory=lambda: Path(_env(
        "FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist")
    )))
    langfuse_enabled: bool = _env("LANGFUSE_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    langfuse_public_key: str = _env("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = _env("LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = _env("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    @property
    def mock_mode(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@lru_cache(maxsize=1)
def git_version() -> dict[str, str]:
    try:
        run = lambda args: subprocess.run(
            args, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=3, check=False
        ).stdout.strip()
        return {
            "sha": run(["git", "rev-parse", "--short", "HEAD"]) or "unknown",
            "date": run(["git", "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M"]),
        }
    except (OSError, subprocess.SubprocessError):
        return {"sha": "unknown", "date": ""}


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _models(path: Path, model: type[Any]) -> list[Any]:
    return [model(**item) for item in _read_json(path, [])]


class JsonTicketStore:
    def __init__(self, path: Path) -> None:
        self.path, self._lock, self._tickets = path, threading.Lock(), {}
        try:
            raw = _read_json(path, {})
        except (OSError, json.JSONDecodeError) as exc:
            broken = path.with_name(f"{path.stem}.broken-{datetime.now():%Y%m%d%H%M%S}.json")
            logging.getLogger("qa_ticket.store").warning("工单文件损坏(%s)，移至 %s", exc, broken.name)
            try:
                path.replace(broken)
            except OSError:
                pass
            return
        for item in raw.get("tickets", []) if isinstance(raw, dict) else raw:
            try:
                record = TicketRecord(**item)
                self._tickets[record.id] = record
            except Exception:
                continue

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        payload = {"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "tickets": [x.model_dump() for x in self._tickets.values()]}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def count(self) -> int:
        return len(self._tickets)

    def create(self, payload: TicketCreate) -> tuple[TicketRecord, bool]:
        with self._lock:
            if existing := duplicate_of(list(self._tickets.values()), payload):
                return existing, True
            record = TicketRecord(
                id=next_ticket_id(self._tickets), created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                **payload.model_dump(),
            )
            self._tickets[record.id] = record
            self._save()
            return record, False


class JsonOrderStore:
    def __init__(self, path: Path) -> None:
        self._orders = _models(path, OrderRecord)
        self._by_no = {x.order_no.upper(): x for x in self._orders}

    def get(self, order_no: str) -> OrderRecord | None:
        return self._by_no.get(order_no.strip().upper())

    def search(self, *, q: str = "", status: int | None = None, user_id: int | None = None, limit: int = 20) -> list[OrderRecord]:
        key, rows = q.strip().lower(), []
        for order in self._orders:
            if status is not None and order.order_status != status or user_id is not None and order.user_id != user_id:
                continue
            text = " ".join([
                order.order_no, str(order.user_id),
                *(str(x) for x in (order.user or {}).values()),
                *(str(x.get("product_name", "")) for x in order.items),
            ]).lower()
            if not key or key in text:
                rows.append(order)
        return sorted(rows, key=lambda x: x.created_at, reverse=True)[:max(limit, 0)]

    def count(self) -> int:
        return len(self._orders)


class JsonKnowledgeCatalog:
    def __init__(self, articles_file: Path, categories_file: Path) -> None:
        self._articles = _models(articles_file, KnowledgeArticle)
        self._categories = _models(categories_file, KnowledgeCategory)

    def categories(self) -> list[KnowledgeCategory]:
        return sorted(self._categories, key=lambda x: x.sort_no)

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]:
        key, category, rows = q.strip().lower(), category.strip().lower(), []
        for article in self._articles:
            keys = {article.category_code.lower(), article.category_name.lower(), str(article.category_id)}
            text = " ".join([article.title, article.summary, article.article_no, *article.tags]).lower()
            if (not category or category in keys) and (not key or key in text):
                rows.append(article)
        return sorted(rows, key=lambda x: (x.is_top, x.sort_weight), reverse=True)[:max(limit, 0)]

    def count(self) -> int:
        return len(self._articles)


def _json_store(value: str, name: str, build):
    if value == "json":
        return build()
    if value == "postgres":
        raise NotImplementedError(f"{name}=postgres 尚未接入")
    raise ValueError(f"未知的 {name}: {value!r}")


def create_ticket_store() -> JsonTicketStore:
    return _json_store(settings.ticket_store, "TICKET_STORE", lambda: JsonTicketStore(settings.data_dir / "tickets.json"))


def create_order_store() -> JsonOrderStore:
    return _json_store(settings.order_store, "ORDER_STORE", lambda: JsonOrderStore(settings.orders_file))


def create_knowledge_catalog() -> JsonKnowledgeCatalog:
    return JsonKnowledgeCatalog(settings.kb_articles_file, settings.kb_root / "categories.json")


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
    return "\n".join(x for x in (line.strip() for line in unescape(re.sub(r"(?s)<[^>]+>", " ", fragment)).splitlines()) if x)


def _split_sections(path: Path) -> list[tuple[str, str]]:
    raw = path.read_text(encoding="utf-8")
    title_match = re.search(r"<title>(.*?)</title>", raw, flags=re.S | re.I)
    title = unescape(title_match.group(1)).split(" - ")[0].strip() if title_match else path.stem
    parts = re.split(r"(?is)<h2[^>]*>(.*?)</h2>", raw)
    if len(parts) == 1:
        body = _html_text(parts[0])
        return [(title, body)] if body else []
    sections = []
    for i in range(1, len(parts), 2):
        heading = _html_text(parts[i])
        body = _html_text(parts[i + 1] if i + 1 < len(parts) else "")
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
        if self.docs_dir.is_dir():
            for path in sorted(self.docs_dir.glob("*.html")):
                if path.name.lower() != "index.html":
                    for title, text in _split_sections(path):
                        self._chunks.append(_Chunk(path.name, title, text, _tokens(f"{title} {text}"), _tokens(title)))

    def document_count(self) -> int:
        return len({x.source for x in self._chunks})

    def chunk_count(self) -> int:
        return len(self._chunks)

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun | None = None) -> list[Document]:
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
        scored.sort(key=lambda x: (-x[0], x[1].source, x[1].title))
        return [Document(page_content=c.text, metadata={
            "index": i, "source": c.source, "title": c.title, "score": score,
        }) for i, (score, c) in enumerate(scored[:max(limit, 0)], 1)]


def format_context(documents: Sequence[Document]) -> str:
    lines = [CONTEXT_HEADER]
    for index, doc in enumerate(documents, 1):
        lines.extend([f"[{index}] {doc.metadata.get('source', '')} · {doc.metadata.get('title', '')}",
                      doc.page_content.strip(), ""])
    lines.append(CONTEXT_FOOTER)
    return "\n".join(lines)


def message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x if isinstance(x, str) else str(x.get("text", "")) for x in content if isinstance(x, (str, dict)))
    return str(content)


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _compose(self, messages: list[BaseMessage]) -> str:
        question = next((message_text(x.content) for x in reversed(messages) if isinstance(x, HumanMessage)), "")
        prompt = next((message_text(x.content) for x in messages if isinstance(x, SystemMessage) and CONTEXT_HEADER in message_text(x.content)), "")
        block = prompt.split(CONTEXT_HEADER, 1)[-1].split(CONTEXT_FOOTER, 1)[0]
        matches = list(re.finditer(r"(?m)^\[(\d+)\]\s*(.+)$", block))
        docs = [(f"[{m.group(1)}] {m.group(2)}", block[m.end():(matches[i + 1].start() if i + 1 < len(matches) else len(block))].strip()) for i, m in enumerate(matches)]
        return (
            f"【演示模式】检索到 {len(docs)} 段资料：\n\n" + "\n\n".join(f"{h}\n{b[:160]}" for h, b in docs)
            if docs else f"【演示模式】问题：{question or '（空）'}"
        )

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._compose(messages)))])

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        answer = self._compose(messages)
        for i in range(0, len(answer), 8):
            yield ChatGenerationChunk(message=AIMessageChunk(content=answer[i:i + 8]))


def create_llm() -> BaseChatModel:
    provider = settings.llm_provider
    if provider == "mock":
        return FakeChatModel()
    models = {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini"}
    if provider not in models:
        raise ValueError(f"未知的 LLM_PROVIDER: {provider!r}")
    if not settings.llm_api_key:
        raise RuntimeError(f"LLM_PROVIDER={provider} 需要配置 LLM_API_KEY")
    from langchain_openai import ChatOpenAI
    kwargs = {
        "model": settings.llm_model or models[provider], "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature, "timeout": settings.llm_timeout, "streaming": True,
    }
    if url := settings.llm_base_url or ("https://api.deepseek.com/v1" if provider == "deepseek" else ""):
        kwargs["base_url"] = url
    return ChatOpenAI(**kwargs)


def create_checkpointer():
    if settings.checkpointer == "memory":
        from langgraph.checkpoint.memory import InMemorySaver
        return InMemorySaver()
    if settings.checkpointer == "postgres":
        raise NotImplementedError("CHECKPOINTER=postgres 尚未接入")
    raise ValueError(f"未知的 CHECKPOINTER: {settings.checkpointer!r}")


def create_retriever() -> InMemoryRetriever | None:
    if settings.retriever == "memory":
        retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
        return retriever if retriever.chunk_count() else None
    if settings.retriever == "pgvector":
        raise NotImplementedError("RETRIEVER=pgvector 尚未接入")
    raise ValueError(f"未知的 RETRIEVER: {settings.retriever!r}")


def estimate_tokens(text: str) -> int:
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return max(1, cjk + max(len(text) - cjk, 0) // 4) if text else 0


class MetricsCollector:
    def __init__(self, max_records: int = 5000) -> None:
        self._lock, self._turns = threading.Lock(), deque(maxlen=max_records)

    def record_turn(self, *, intent: str, tokens: int, first_token_ms: int | None, total_ms: int, ok: bool) -> None:
        with self._lock:
            self._turns.append((time.time(), intent or "unknown", max(tokens, 0), first_token_ms, max(total_ms, 0), ok))

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()

    def summary(self, days: int = 7) -> dict:
        days = max(1, min(days, 30))
        cutoff = time.time() - days * 86400
        with self._lock:
            turns = [x for x in self._turns if x[0] >= cutoff]
        firsts = [x[3] for x in turns if x[3] is not None]
        avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else 0.0
        intents: dict[str, list[int]] = {}
        for _, intent, tokens, _, latency, ok in turns:
            row = intents.setdefault(intent, [0, 0, 0, 0])
            row[0] += 1; row[1] += tokens; row[2] += latency; row[3] += not ok
        total, errors = len(turns), sum(not x[5] for x in turns)
        return {
            "days": days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kpis": {
                "requests": total, "tokens": sum(x[2] for x in turns),
                "avg_first_token_ms": avg(firsts), "avg_latency_ms": avg([x[4] for x in turns]),
                "error_rate": round(errors / total * 100, 2) if total else 0.0,
            },
            "by_intent": sorted(({
                "intent": name, "calls": row[0], "tokens": row[1],
                "avg_latency_ms": round(row[2] / row[0], 1),
                "success_rate": round((1 - row[3] / row[0]) * 100, 2),
            } for name, row in intents.items()), key=lambda row: (-row["calls"], -row["tokens"])),
        }


@dataclass
class LangfuseTracing:
    handler: Any | None = None
    client: Any | None = None
    status: str = "disabled"
    reason: str = ""

    @property
    def enabled(self) -> bool:
        return self.handler is not None

    def shutdown(self) -> None:
        if self.client is not None:
            try:
                self.client.shutdown()
            except Exception:
                logging.getLogger("qa_ticket.langfuse").exception("Langfuse 关闭时刷新失败")


def create_langfuse_tracing(config: Settings | None = None) -> LangfuseTracing:
    cfg = config or settings
    if not cfg.langfuse_enabled:
        return LangfuseTracing(reason="LANGFUSE_ENABLED=false")
    if not cfg.langfuse_configured:
        return LangfuseTracing(status="misconfigured", reason="missing keys")
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler
        return LangfuseTracing(handler=CallbackHandler(), client=get_client(), status="enabled")
    except Exception as exc:
        logging.getLogger("qa_ticket.langfuse").exception("Langfuse 初始化失败，已降级为关闭")
        return LangfuseTracing(status="error", reason=f"{exc.__class__.__name__}: {exc}")
