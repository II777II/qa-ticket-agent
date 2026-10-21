"""Langfuse 可选追踪：初始化失败时保持 fail-open，不影响对话主链路。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backend.infrastructure.config import Settings, settings

logger = logging.getLogger("qa_ticket.langfuse")


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
        if self.client is None:
            return
        try:
            self.client.shutdown()
        except Exception:
            logger.exception("Langfuse 关闭时刷新失败")


def create_langfuse_tracing(config: Settings | None = None) -> LangfuseTracing:
    """按配置创建 Langfuse CallbackHandler；任何初始化异常都降级为关闭。"""
    cfg = config or settings
    if not cfg.langfuse_enabled:
        return LangfuseTracing(status="disabled", reason="LANGFUSE_ENABLED=false")
    if not cfg.langfuse_configured:
        logger.warning("Langfuse 已启用但缺少 PUBLIC/SECRET Key，已自动关闭")
        return LangfuseTracing(status="misconfigured", reason="missing keys")

    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        client = get_client()
        handler = CallbackHandler()
        logger.info("Langfuse tracing 已启用: %s", cfg.langfuse_base_url)
        return LangfuseTracing(handler=handler, client=client, status="enabled")
    except Exception as exc:
        logger.exception("Langfuse 初始化失败，已降级为关闭")
        return LangfuseTracing(
            status="error",
            reason=f"{exc.__class__.__name__}: {exc}",
        )
