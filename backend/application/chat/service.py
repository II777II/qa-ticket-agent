"""一轮对话用例：执行 LangGraph，并把结果翻译为业务事件。"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from backend.application.contracts import (
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_INTENT,
    EVENT_ORDER,
    EVENT_START,
    EVENT_TOKEN,
)
from backend.domain.intent import IntentName
from backend.infrastructure.config import settings
from backend.infrastructure.observability import estimate_tokens

if TYPE_CHECKING:
    from backend.application.runtime import AgentRuntime

logger = logging.getLogger("qa_ticket.chat")


def _text(value: Any) -> str:
    content = getattr(value, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block
            if isinstance(block, str)
            else str(block.get("text", ""))
            for block in content
            if isinstance(block, (str, dict))
        )
    return ""


class ChatService:
    def __init__(self, runtime: "AgentRuntime") -> None:
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
            "run_name": "qa-ticket.chat",
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_tags": ["qa-ticket", f"branch:{requested_intent or 'auto'}"],
            },
        }
        if self._runtime.tracing and self._runtime.tracing.handler:
            config["callbacks"] = [self._runtime.tracing.handler]

        yield EVENT_START, {
            "thread_id": thread_id,
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
        }
        started = time.perf_counter()
        first_at: float | None = None
        answer: list[str] = []
        final_text = ""
        usage_tokens = 0
        emitted = False
        ok = True
        intent = requested_intent or "unknown"

        try:
            async for mode, payload in self._runtime.graph.astream(
                {
                    "messages": [HumanMessage(content=message)],
                    "requested_intent": requested_intent,
                },
                config=config,
                stream_mode=["messages", "custom", "updates"],
            ):
                if mode == "messages":
                    chunk, _ = payload
                    if not isinstance(chunk, AIMessageChunk):
                        continue
                    usage = getattr(chunk, "usage_metadata", None)
                    if isinstance(usage, dict):
                        usage_tokens = max(usage_tokens, int(usage.get("total_tokens") or 0))
                    text = _text(chunk)
                    if text:
                        emitted = True
                        first_at = first_at or time.perf_counter()
                        answer.append(text)
                        yield EVENT_TOKEN, {"text": text}
                elif mode == "custom" and isinstance(payload, dict):
                    event, data = payload.get("event"), payload.get("data")
                    if isinstance(event, str) and isinstance(data, dict):
                        if event == EVENT_INTENT and isinstance(data.get("intent"), str):
                            intent = data["intent"]
                        yield event, data
                elif mode == "updates":
                    for output in payload.values() if isinstance(payload, dict) else []:
                        for item in output.get("messages") or [] if isinstance(output, dict) else []:
                            if isinstance(item, AIMessage) and not isinstance(item, AIMessageChunk):
                                final_text = _text(item) or final_text

            if not emitted and final_text:
                first_at = time.perf_counter()
                answer.append(final_text)
                yield EVENT_TOKEN, {"text": final_text}
            yield EVENT_DONE, {"thread_id": thread_id}
        except Exception as exc:
            ok = False
            logger.exception("对话失败")
            yield EVENT_ERROR, {"type": exc.__class__.__name__, "message": str(exc)}
        finally:
            total_ms = int((time.perf_counter() - started) * 1000)
            first_ms = int((first_at - started) * 1000) if first_at else None
            tokens = usage_tokens or estimate_tokens(message + "".join(answer))
            self._runtime.metrics.record_turn(
                tokens=tokens,
                first_token_ms=first_ms,
                total_ms=total_ms,
                ok=ok,
                intent=intent,
            )
