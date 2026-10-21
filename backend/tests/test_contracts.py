"""应用层公开门面与共享事件契约的边界测试。"""

from __future__ import annotations

import backend.application.chat as chat_package
import backend.application.contracts as contracts
from backend.application.chat import ChatService
from backend.application.contracts import EVENT_ERROR, EVENT_SERVICE_DRAFT, EVENT_START


def test_chat_package_exposes_only_chat_service() -> None:
    assert chat_package.__all__ == ["ChatService"]
    assert chat_package.ChatService is ChatService
    assert not hasattr(chat_package, "EVENT_START")


def test_chat_events_live_in_shared_contract_package() -> None:
    assert EVENT_START == "start"
    assert EVENT_SERVICE_DRAFT == "service_draft"
    assert EVENT_ERROR == "error"
    assert {
        "EVENT_START",
        "EVENT_SERVICE_DRAFT",
        "EVENT_ERROR",
    }.issubset(set(contracts.__all__))
