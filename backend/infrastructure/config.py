"""集中配置：所有可替换实现都通过环境变量切换。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEMO_DIR = BACKEND_DIR / "data" / "demo" / "ecommerce"
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    return Path(_env(name, str(default)))


@dataclass(frozen=True)
class Settings:
    host: str = _env("HOST", "127.0.0.1")
    port: int = _int("PORT", 5179)
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in _env(
                "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
            ).split(",")
            if item.strip()
        )
    )

    llm_provider: str = _env("LLM_PROVIDER", "mock").lower()
    llm_model: str = _env("LLM_MODEL")
    llm_api_key: str = _env("LLM_API_KEY")
    llm_base_url: str = _env("LLM_BASE_URL")
    llm_temperature: float = _float("LLM_TEMPERATURE", 0.2)
    llm_timeout: float = _float("LLM_TIMEOUT", 120.0)

    checkpointer: str = _env("CHECKPOINTER", "memory").lower()
    retriever: str = _env("RETRIEVER", "memory").lower()
    ticket_store: str = _env("TICKET_STORE", "json").lower()
    order_store: str = _env("ORDER_STORE", "json").lower()
    rag_top_k: int = _int("RAG_TOP_K", 3)

    data_dir: Path = field(default_factory=lambda: _path("DATA_DIR", BACKEND_DIR / "data"))
    orders_file: Path = field(default_factory=lambda: _path("ORDERS_FILE", DEMO_DIR / "orders.json"))
    kb_root: Path = field(default_factory=lambda: _path("KB_ROOT", DEMO_DIR / "kb"))
    kb_dir: Path = field(default_factory=lambda: _path("KB_DIR", DEMO_DIR / "kb" / "pages"))
    kb_articles_file: Path = field(
        default_factory=lambda: _path("KB_ARTICLES_FILE", DEMO_DIR / "kb" / "articles.json")
    )
    frontend_dist: Path = field(
        default_factory=lambda: _path("FRONTEND_DIST", PROJECT_ROOT / "frontend" / "dist")
    )

    langfuse_enabled: bool = _bool("LANGFUSE_ENABLED")
    langfuse_public_key: str = _env("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = _env("LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = _env("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    @property
    def mock_mode(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def ticket_store_file(self) -> Path:
        return self.data_dir / "tickets.json"

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()
