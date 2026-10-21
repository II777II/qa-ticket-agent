"""应用层共享事件契约测试。"""

from __future__ import annotations

from backend.application.core import EVENT_ERROR, EVENT_SERVICE_DRAFT, EVENT_START


def test_chat_events_live_in_shared_contract_package() -> None:
    assert EVENT_START == "start"
    assert EVENT_SERVICE_DRAFT == "service_draft"
    assert EVENT_ERROR == "error"
