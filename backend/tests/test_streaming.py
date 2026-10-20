"""SSE 生成器的异常兜底测试。"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from backend.api.schemas import ChatRequest
from backend.api.streaming import stream_events


class BrokenChatService:
    async def stream(
        self,
        _message: str,
        _thread_id: str,
        *,
        requested_intent: str | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        yield "start", {"thread_id": "stream-error", "provider": "test", "mock": True}
        raise RuntimeError("upstream disconnected")


class UnserializableChatService:
    async def stream(
        self,
        _message: str,
        _thread_id: str,
        *,
        requested_intent: str | None = None,
    ) -> AsyncIterator[tuple[str, dict]]:
        yield "start", {"bad": object()}


def _collect(chat_service) -> list:
    async def run():
        return [
            event
            async for event in stream_events(
                chat_service,
                ChatRequest(message="测试", thread_id="stream-error"),
            )
        ]

    return asyncio.run(run())


def test_stream_events_converts_exception_to_error_event() -> None:
    events = _collect(BrokenChatService())
    assert [event.event for event in events] == ["start", "error"]
    payload = json.loads(events[-1].raw_data)
    assert payload == {
        "type": "RuntimeError",
        "message": "upstream disconnected",
    }


def test_stream_events_catches_payload_serialization_error() -> None:
    events = _collect(UnserializableChatService())
    assert [event.event for event in events] == ["error"]
    payload = json.loads(events[-1].raw_data)
    assert payload["type"] == "TypeError"
    assert payload["message"]
