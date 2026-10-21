"""应用层共享契约：跨 Agent、Chat 与接口适配器的事件名称。"""

from backend.application.contracts.chat_events import (
    EVENT_CITATION,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_INTENT,
    EVENT_ORDER,
    EVENT_SERVICE_DRAFT,
    EVENT_START,
    EVENT_TICKET,
    EVENT_TOKEN,
    EVENT_TOOL,
)

__all__ = [
    "EVENT_CITATION",
    "EVENT_DONE",
    "EVENT_ERROR",
    "EVENT_INTENT",
    "EVENT_ORDER",
    "EVENT_SERVICE_DRAFT",
    "EVENT_START",
    "EVENT_TICKET",
    "EVENT_TOKEN",
    "EVENT_TOOL",
]
