"""One-turn chat use case that executes LangGraph and emits application events."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from backend.application.agent import (
    EVENT_DONE, EVENT_ERROR, EVENT_INTENT, EVENT_START, EVENT_TOKEN,
)
from backend.domain.core import IntentName
from backend.infrastructure.config import settings
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
        *,
        requested_intent: IntentName | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id},
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_tags": ["qa-ticket", f"branch:{requested_intent or 'auto'}"],
            },
        }
        if self._runtime.tracing and self._runtime.tracing.handler:
            config["callbacks"] = [self._runtime.tracing.handler]
        provider = getattr(self._runtime, "provider", "") or settings.llm_provider
        yield EVENT_START, {"thread_id": thread_id, "provider": provider, "mock": provider == "mock"}
        started, first_at, answer, final_text, tokens = time.perf_counter(), None, [], "", 0
        ok, intent = True, requested_intent or "unknown"
        try:
            async for mode, payload in self._runtime.graph.astream(
                {"messages": [HumanMessage(content=message)], "requested_intent": requested_intent},
                config=config,
                stream_mode=["messages", "custom", "updates"],
            ):
                if mode == "messages":
                    chunk, _ = payload
                    if isinstance(chunk, AIMessageChunk):
                        usage = getattr(chunk, "usage_metadata", None)
                        if isinstance(usage, dict):
                            tokens = max(tokens, int(usage.get("total_tokens") or 0))
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
            self._runtime.metrics.record_turn(
                tokens=tokens or estimate_tokens(message + "".join(answer)),
                first_token_ms=first_ms,
                total_ms=total_ms,
                ok=ok,
                intent=intent,
            )
