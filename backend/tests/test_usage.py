"""Usage callback aggregation tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from backend.application.chat import ChatService


class _UsageGraph:
    async def astream(self, _inputs, config, stream_mode):
        for total in (12, 8):
            result = LLMResult(generations=[[ChatGeneration(message=AIMessage(
                content="ignored",
                usage_metadata={"input_tokens": total - 2, "output_tokens": 2, "total_tokens": total},
                response_metadata={"model_name": "test-model"},
            ))]])
            for callback in config["callbacks"]:
                callback.on_llm_end(result)
        yield "updates", {"node": {"messages": [AIMessage(content="聚合完成")]}}


class _Metrics:
    def __init__(self) -> None:
        self.tokens = None

    def record_turn(self, **kwargs) -> None:
        self.tokens = kwargs["tokens"]


def test_chat_service_sums_usage_across_llm_calls() -> None:
    metrics = _Metrics()
    runtime = SimpleNamespace(graph=_UsageGraph(), metrics=metrics, tracing=None, provider="test")

    async def consume() -> None:
        async for _event, _payload in ChatService(runtime).stream("测试", "usage-thread"):
            pass

    asyncio.run(consume())
    assert metrics.tokens == 20
