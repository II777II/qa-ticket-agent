"""集中配置。

所有「可替换的实现」都在这里通过环境变量切换，业务代码不直接读 env：
    模型        LLM_PROVIDER   mock | deepseek | openai
    短期记忆    CHECKPOINTER   memory | postgres
    检索        RETRIEVER      memory | pgvector
    工单存储    TICKET_STORE   json | postgres

POC 阶段只用最左边那档实现，右边几档是给 compose 升级预留的开关。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# 本文件位于 backend/infrastructure/，包根要上跳一层，否则数据目录会指到 infrastructure/ 里
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DEMO_DIR = BACKEND_DIR / "data" / "demo" / "ecommerce"

# .env 放在项目根目录，进程启动时加载一次
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """运行时配置（不可变，避免各层偷偷改全局状态）。"""

    # ---------- 服务 ----------
    host: str = _env("HOST", "127.0.0.1")
    port: int = _env_int("PORT", 5179)
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            origin.strip()
            for origin in _env(
                "CORS_ORIGINS",
                "http://127.0.0.1:5173,http://localhost:5173",
            ).split(",")
            if origin.strip()
        )
    )

    # ---------- 模型 ----------
    llm_provider: str = _env("LLM_PROVIDER", "mock").lower()
    llm_model: str = _env("LLM_MODEL")
    llm_api_key: str = _env("LLM_API_KEY")
    llm_base_url: str = _env("LLM_BASE_URL")
    llm_temperature: float = _env_float("LLM_TEMPERATURE", 0.2)
    llm_timeout: float = _env_float("LLM_TIMEOUT", 120.0)

    # ---------- 四个扩展点 ----------
    checkpointer: str = _env("CHECKPOINTER", "memory").lower()
    retriever: str = _env("RETRIEVER", "memory").lower()
    ticket_store: str = _env("TICKET_STORE", "json").lower()
    order_store: str = _env("ORDER_STORE", "json").lower()

    # ---------- 数据落点 ----------
    data_dir: Path = field(
        default_factory=lambda: Path(_env("DATA_DIR", str(BACKEND_DIR / "data")))
    )
    # 电商演示数据：订单 JSON + HTML 知识库（后续换 Postgres 时这里只是导入源）
    demo_data_dir: Path = field(
        default_factory=lambda: Path(_env("DEMO_DATA_DIR", str(DEFAULT_DEMO_DIR)))
    )
    orders_file: Path = field(
        default_factory=lambda: Path(_env("ORDERS_FILE", str(DEFAULT_DEMO_DIR / "orders.json")))
    )
    kb_root: Path = field(
        default_factory=lambda: Path(_env("KB_ROOT", str(DEFAULT_DEMO_DIR / "kb")))
    )
    kb_dir: Path = field(
        default_factory=lambda: Path(_env("KB_DIR", str(DEFAULT_DEMO_DIR / "kb" / "pages")))
    )
    kb_articles_file: Path = field(
        default_factory=lambda: Path(_env("KB_ARTICLES_FILE", str(DEFAULT_DEMO_DIR / "kb" / "articles.json")))
    )
    # 前端构建产物：存在时后端直接同源托管，现场演示只开一个地址（默认 5179）
    frontend_dist: Path = field(
        default_factory=lambda: Path(_env("FRONTEND_DIST", str(PROJECT_ROOT / "frontend" / "dist")))
    )

    # ---------- RAG ----------
    rag_top_k: int = _env_int("RAG_TOP_K", 3)

    # ---------- 生产化预留（POC 不连接，compose 升级时才用）----------
    database_url: str = _env("DATABASE_URL")
    redis_url: str = _env("REDIS_URL")
    vector_db_url: str = _env("VECTOR_DB_URL")
    embed_model: str = _env("EMBED_MODEL")

    # ---------- Langfuse 可观测性（默认关闭，失败时不影响主链路）----------
    langfuse_enabled: bool = _env_bool("LANGFUSE_ENABLED", False)
    langfuse_public_key: str = _env("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = _env("LANGFUSE_SECRET_KEY")
    langfuse_base_url: str = _env("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    @property
    def mock_mode(self) -> bool:
        """演示模式：没有 API Key 也能跑通全链路。"""
        return self.llm_provider == "mock"

    @property
    def ticket_store_file(self) -> Path:
        return self.data_dir / "tickets.json"

    @property
    def langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


settings = Settings()
