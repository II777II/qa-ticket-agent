"""Langfuse 可选追踪的配置与注入测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.callbacks import UsageMetadataCallbackHandler

from backend.application.chat import ChatService
from backend.infrastructure.observability import LangfuseTracing, create_langfuse_tracing


def _config(**overrides):
    values = {
        "langfuse_enabled": False,
        "langfuse_public_key": "",
        "langfuse_secret_key": "",
        "langfuse_base_url": "https://cloud.langfuse.com",
    }
    values.update(overrides)
    values["langfuse_configured"] = bool(
        values["langfuse_public_key"] and values["langfuse_secret_key"]
    )
    return SimpleNamespace(**values)


def test_langfuse_disabled_by_default() -> None:
    tracing = create_langfuse_tracing(_config())
    assert tracing.enabled is False
    assert tracing.status == "disabled"


def test_langfuse_missing_keys_fails_open() -> None:
    tracing = create_langfuse_tracing(_config(langfuse_enabled=True))
    assert tracing.enabled is False
    assert tracing.status == "misconfigured"


def test_chat_service_injects_langfuse_callback_and_session() -> None:
    class Graph:
        config = None

        async def astream(self, _inputs, config, stream_mode):
            self.config = config
            if False:
                yield None

    class Metrics:
        def record_turn(self, **_kwargs) -> None:
            pass

    graph = Graph()
    handler = object()
    runtime = SimpleNamespace(
        graph=graph,
        metrics=Metrics(),
        tracing=LangfuseTracing(handler=handler, status="enabled"),
    )

    async def consume() -> None:
        async for _event, _payload in ChatService(runtime).stream("你好", "trace-thread"):
            pass

    asyncio.run(consume())
    assert handler in graph.config["callbacks"]
    assert any(isinstance(callback, UsageMetadataCallbackHandler) for callback in graph.config["callbacks"])
    assert graph.config["metadata"]["langfuse_session_id"] == "trace-thread"
    assert "qa-ticket" in graph.config["metadata"]["langfuse_tags"]
