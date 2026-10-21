"""Environment configuration, logging and version helpers."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEMO_DIR = BACKEND_DIR / "data" / "demo" / "ecommerce"
EVAL_CASES_FILE = DEMO_DIR / "eval_cases.json"
LLM_MODELS = {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini"}
load_dotenv(PROJECT_ROOT / ".env")


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
    database_url: str = _env("DATABASE_URL")
    pgvector_collection: str = _env("PGVECTOR_COLLECTION", "kb_chunk")
    embedding_provider: str = _env("EMBEDDING_PROVIDER", "mock").lower()
    embedding_model: str = _env("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_api_key: str = _env("EMBEDDING_API_KEY") or _env("OPENAI_API_KEY")
    embedding_base_url: str = _env("EMBEDDING_BASE_URL")
    embedding_dimensions: int = _number("EMBEDDING_DIMENSIONS", 1536, int)
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
