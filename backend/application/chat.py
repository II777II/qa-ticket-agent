"""One-turn chat use case that executes LangGraph and emits application events."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from backend.application.graph import (
    EVENT_DONE, EVENT_ERROR, EVENT_INTENT, EVENT_START, EVENT_TOKEN,
)
from backend.infrastructure.llm import message_text
from backend.infrastructure.observability import estimate_tokens

if TYPE_CHECKING:
    from backend.application.runtime import AgentRuntime

logger = logging.getLogger("qa_ticket")


class ChatService:
    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def stream(
        self,
        message: str,
        thread_id: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_tags": ["qa-ticket", "auto"],
            },
        }
        usage_handler = UsageMetadataCallbackHandler()
        callbacks: list[Any] = [usage_handler]
        if self._runtime.tracing and self._runtime.tracing.handler:
            callbacks.append(self._runtime.tracing.handler)
        config["callbacks"] = callbacks
        graph, provider, _ = self._runtime.snapshot()
        yield EVENT_START, {"thread_id": thread_id, "provider": provider, "mock": provider == "mock"}
        started, first_at, answer, final_text = time.perf_counter(), None, [], ""
        ok, intent = True, "unknown"
        try:
            async for mode, payload in graph.astream(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                stream_mode=["messages", "custom", "updates"],
            ):
                if mode == "messages":
                    chunk, _ = payload
                    if isinstance(chunk, AIMessageChunk):
                        if text := message_text(chunk):
                            first_at = first_at or time.perf_counter()
                            answer.append(text)
                            yield EVENT_TOKEN, {"text": text}
                elif mode == "custom" and isinstance(payload, dict):
                    event, data = payload.get("event"), payload.get("data")
                    if isinstance(event, str) and isinstance(data, dict):
                        if event == EVENT_INTENT and isinstance(data.get("intent"), str):
                            intent = data["intent"]
                        yield event, data
                elif mode == "updates" and isinstance(payload, dict):
                    for output in payload.values():
                        for item in output.get("messages") or [] if isinstance(output, dict) else []:
                            if isinstance(item, AIMessage) and not isinstance(item, AIMessageChunk):
                                final_text = message_text(item) or final_text
            if not answer and final_text:
                first_at, answer = time.perf_counter(), [final_text]
                yield EVENT_TOKEN, {"text": final_text}
            yield EVENT_DONE, {"thread_id": thread_id}
        except Exception as exc:
            ok = False
            logger.exception("对话失败")
            yield EVENT_ERROR, {"type": exc.__class__.__name__, "message": str(exc)}
        finally:
            total_ms = int((time.perf_counter() - started) * 1000)
            first_ms = int((first_at - started) * 1000) if first_at else None
            usage_tokens = sum(
                int(usage.get("total_tokens") or 0)
                for usage in usage_handler.usage_metadata.values()
            )
            self._runtime.metrics.record_turn(
                tokens=usage_tokens or estimate_tokens(message + "".join(answer)),
                first_token_ms=first_ms,
                total_ms=total_ms,
                ok=ok,
                intent=intent,
            )
