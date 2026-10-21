"""LangGraph 检查点工厂。"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver

from backend.infrastructure.config import settings


def create_checkpointer() -> BaseCheckpointSaver:
    if settings.checkpointer == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()
    if settings.checkpointer == "postgres":
        raise NotImplementedError("CHECKPOINTER=postgres 尚未接入")
    raise ValueError(f"未知的 CHECKPOINTER: {settings.checkpointer!r}")

__all__ = ["create_checkpointer"]
