"""接口用例：健康检查、能力查询、工单接口、/chat 的 SSE 事件契约。"""

from __future__ import annotations

import asyncio
import json

import httpx

from backend import main as backend_main
from backend.application.runtime import AgentRuntime


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=backend_main.app), base_url="http://testserver")


async def _get(path: str):
    async with _client() as client:
        return await client.get(path)


async def _stream_chat(message: str, thread_id: str, expect_status: int = 200) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with _client() as client:
        async with client.stream("POST", "/chat", json={"message": message, "thread_id": thread_id}) as response:
            assert response.status_code == expect_status
            current = ""
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    current = line[7:]
                elif line.startswith("data: ") and current:
                    events.append((current, json.loads(line[6:])))
                    current = ""
    return events


def _prepare(runtime: AgentRuntime) -> None:
    """接口层靠 app.state.runtime 取运行时，测试里直接注入隔离版本。"""
    backend_main.app.state.runtime = runtime


def test_health(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    response = asyncio.run(_get("/health"))
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["provider"] == "mock"
    assert body["checkpointer"] == "memory"


def test_agent_info_reports_capabilities(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    body = asyncio.run(_get("/api/agent-info")).json()
    assert body["kb_documents"] == 5
    assert body["kb_chunks"] >= 10
    assert "tool:create_ticket" in body["extensions"]
    assert body["tickets"] == 0


def test_root_returns_html_or_json(isolated_runtime: AgentRuntime) -> None:
    """构建过前端就返回首页，否则返回服务说明——两种都算正常。"""
    _prepare(isolated_runtime)
    response = asyncio.run(_get("/"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(("text/html", "application/json"))


def test_tickets_flow(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    assert asyncio.run(_get("/api/tickets")).json() == []

    events = asyncio.run(_stream_chat("帮我建个工单，会议室打印机装不上驱动，联系我 li.si@corp.com", "api-1"))
    tickets = [payload["tickets"][0] for event, payload in events if event == "ticket"]
    assert tickets, "建单后应收到 ticket 事件"
    ticket_id = tickets[0]["id"]

    listing = asyncio.run(_get("/api/tickets")).json()
    assert len(listing) == 1

    detail = asyncio.run(_get(f"/api/tickets/{ticket_id}"))
    assert detail.status_code == 200
    assert detail.json()["title"]
    assert len(detail.json()["events"]) >= 1


def test_unknown_ticket_returns_404(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    assert asyncio.run(_get("/api/tickets/TK-19700101-0001")).status_code == 404


def test_chat_sse_event_contract(isolated_runtime: AgentRuntime) -> None:
    """咨询类问题的事件序列：start → token… → citation… → done，且不建单。"""
    _prepare(isolated_runtime)
    events = asyncio.run(_stream_chat("VPN 连不上，提示 691 怎么办？", "api-2"))
    names = [name for name, _ in events]

    assert names[0] == "start"
    assert names[-1] == "done"
    assert "token" in names
    assert "citation" in names
    assert "tool" not in names and "ticket" not in names

    start = events[0][1]
    assert start["thread_id"] == "api-2"
    assert start["mock"] is True
    assert "[1]" in "".join(payload["text"] for name, payload in events if name == "token")


def test_chat_sse_tool_and_ticket_events(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    events = asyncio.run(_stream_chat("帮我建个工单，VPN 报 691，整个部门都连不上，联系我 wang.wu@corp.com", "api-3"))
    tools = [(payload["phase"], payload["name"]) for name, payload in events if name == "tool"]
    assert ("call", "create_ticket") in tools
    assert ("result", "create_ticket") in tools
    assert any(name == "ticket" for name, _ in events)


def test_chat_rejects_empty_message(isolated_runtime: AgentRuntime) -> None:
    """空消息由 Pydantic 拦在接口层，不进图。"""
    _prepare(isolated_runtime)

    async def post() -> int:
        async with _client() as client:
            response = await client.post("/chat", json={"message": "", "thread_id": "api-4"})
            return response.status_code

    assert asyncio.run(post()) == 422
