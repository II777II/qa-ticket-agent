"""对话事件契约：跨 Agent、Chat、API 与 CLI 的稳定事件名。"""

EVENT_START = "start"
EVENT_INTENT = "intent"
EVENT_TOKEN = "token"
EVENT_ORDER = "order"
EVENT_SERVICE_DRAFT = "service_draft"
EVENT_CITATION = "citation"
EVENT_DONE = "done"
EVENT_ERROR = "error"

__all__ = [
    "EVENT_CITATION",
    "EVENT_DONE",
    "EVENT_ERROR",
    "EVENT_INTENT",
    "EVENT_ORDER",
    "EVENT_SERVICE_DRAFT",
    "EVENT_START",
    "EVENT_TOKEN",
]
