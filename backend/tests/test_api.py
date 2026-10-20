"""接口用例：健康检查、能力查询、四路分支与 SSE 事件契约。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.api.app import app as api_app
from backend.api.routes import agent as agent_routes
from backend.api.routes import chat as chat_routes
from backend.api.routes import dialogue as dialogue_routes
from backend.application.runtime import AgentRuntime


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app), base_url="http://testserver")


async def _get(path: str):
    async with _client() as client:
        return await client.get(path)


async def _stream_post(
    path: str,
    message: str,
    thread_id: str,
    expect_status: int = 200,
) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with _client() as client:
        async with client.stream("POST", path, json={"message": message, "thread_id": thread_id}) as response:
            assert response.status_code == expect_status
            current = ""
            async for line in response.aiter_lines():
                if line.startswith("event: "):
                    current = line[7:]
                elif line.startswith("data: ") and current:
                    events.append((current, json.loads(line[6:])))
                    current = ""
    return events


async def _stream_chat(message: str, thread_id: str, expect_status: int = 200) -> list[tuple[str, dict]]:
    return await _stream_post("/chat", message, thread_id, expect_status)


def _prepare(runtime: AgentRuntime) -> None:
    """接口层靠 app.state.runtime 取运行时，测试里直接注入隔离版本。"""
    api_app.state.runtime = runtime


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
    assert body["kb_documents"] == 50
    assert body["kb_chunks"] >= 100
    assert body["orders"] == 50
    assert body["kb_articles"] == 50
    assert "tool:query_order" in body["extensions"]
    assert "tool:create_ticket" not in body["extensions"]
    assert body["tickets"] == 0
    assert body["git_sha"]  # 界面要显示版本号


def test_root_returns_html_or_json(isolated_runtime: AgentRuntime) -> None:
    """构建过前端就返回首页，否则返回服务说明——两种都算正常。"""
    _prepare(isolated_runtime)
    response = asyncio.run(_get("/"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(("text/html", "application/json"))


def test_ticket_routes_are_not_mounted(isolated_runtime: AgentRuntime) -> None:
    """对话侧停用售后工单后，旧资源接口也不再暴露。"""
    _prepare(isolated_runtime)
    assert asyncio.run(_get("/api/tickets")).status_code == 404
    assert asyncio.run(_get("/api/tickets/TK-19700101-0001")).status_code == 404


def test_openapi_mounts_chat_and_four_branch_routes() -> None:
    paths = api_app.openapi()["paths"]
    assert "/chat" in paths
    assert paths["/branch/knowledge"]["post"]
    assert paths["/branch/query"]["post"]
    assert paths["/branch/service"]["post"]
    assert paths["/branch/fallback"]["post"]
    assert "/api/tickets" not in paths


def test_dialogue_router_owns_chat_and_four_branch_routes() -> None:
    """路由装配层级必须是 app → dialogue → chat / branch。"""
    included = [
        getattr(route, "original_router", None)
        for route in dialogue_routes.router.routes
    ]
    assert any(router is chat_routes.router for router in included)
    assert any(router is agent_routes.router for router in included)
    assert not any(
        getattr(route, "original_router", None) is agent_routes.router
        for route in chat_routes.router.routes
    )


def test_kb_search_returns_hits(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    body = asyncio.run(_get("/api/kb/search?q=%E9%80%80%E6%AC%BE%E5%88%B0%E8%B4%A6&top_k=2")).json()
    assert body
    assert body[0]["source"] == "KB-EC-0020.html"
    assert body[0]["score"] is not None
    assert len(body) <= 2


def test_metrics_summary_after_one_turn(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    asyncio.run(_stream_chat("退款多久到账？", "api-metrics"))

    summary = asyncio.run(_get("/api/metrics/summary?days=1")).json()
    kpis = summary["kpis"]
    assert kpis["requests"] == 1
    assert kpis["tokens"] > 0
    assert kpis["avg_latency_ms"] > 0
    assert kpis["avg_first_token_ms"] >= 0
    assert len(summary["by_day"]) == 1
    assert summary["by_model"][0]["calls"] == 1


def test_chat_sse_event_contract(isolated_runtime: AgentRuntime) -> None:
    """咨询类问题的事件序列：start → token… → citation… → done，且不建单。"""
    _prepare(isolated_runtime)
    events = asyncio.run(_stream_chat("退款多久到账？", "api-2"))
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


def test_chat_does_not_create_tickets(isolated_runtime: AgentRuntime) -> None:
    """对话侧不再提供售后工单工具。"""
    _prepare(isolated_runtime)
    events = asyncio.run(_stream_chat("帮我建个售后工单，商品有质量问题，联系我 wang.wu@corp.com", "api-3"))
    tools = [(payload["phase"], payload["name"]) for name, payload in events if name == "tool"]
    assert not any(name == "create_ticket" for _, name in tools)
    assert not any(name == "ticket" for name, _ in events)


def test_chat_rejects_empty_message(isolated_runtime: AgentRuntime) -> None:
    """空消息由 Pydantic 拦在接口层，不进图。"""
    _prepare(isolated_runtime)

    async def post() -> int:
        async with _client() as client:
            response = await client.post("/chat", json={"message": "", "thread_id": "api-4"})
            return response.status_code

    assert asyncio.run(post()) == 422


def test_orders_api(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    listing = asyncio.run(_get("/api/orders?limit=5")).json()
    assert len(listing) == 5
    order_no = listing[0]["order_no"]
    assert order_no.startswith("SO")
    assert listing[0]["status_label"]

    detail = asyncio.run(_get(f"/api/orders/{order_no.lower()}"))
    assert detail.status_code == 200
    assert detail.json()["order_no"] == order_no
    assert detail.json()["items"]

    missing = asyncio.run(_get("/api/orders/SO197001019999"))
    assert missing.status_code == 404


def test_kb_article_catalog(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    categories = asyncio.run(_get("/api/kb/categories")).json()
    assert len(categories) == 8

    articles = asyncio.run(_get("/api/kb/articles?category=AFTERSALE")).json()
    assert articles and all(item["category_code"] == "AFTERSALE" for item in articles)

    detail = asyncio.run(_get(f"/api/kb/articles/{articles[0]['article_no']}"))
    assert detail.status_code == 200
    assert detail.json()["url"].startswith("/kb/pages/")


def test_chat_order_query_sse(isolated_runtime: AgentRuntime) -> None:
    _prepare(isolated_runtime)
    events = asyncio.run(_stream_chat("帮我查询张三的订单", "api-order"))
    names = [name for name, _ in events]
    assert "citation" not in names
    assert "ticket" not in names
    assert "order" in names
    intents = [payload for name, payload in events if name == "intent"]
    assert intents and intents[-1]["intent"] == "query"
    text = "".join(payload["text"] for name, payload in events if name == "token")
    assert "SO" in text


@pytest.mark.parametrize(
    ("path", "expected_intent"),
    [
        ("/branch/knowledge", "knowledge"),
        ("/branch/query", "query"),
        ("/branch/service", "service"),
        ("/branch/fallback", "fallback"),
    ],
)
def test_explicit_branch_routes_force_intent(
    isolated_runtime: AgentRuntime,
    path: str,
    expected_intent: str,
) -> None:
    """同一句默认会走 knowledge 的话，显式分支入口必须进入指定分支。"""
    _prepare(isolated_runtime)
    events = asyncio.run(
        _stream_post(path, "退款多久到账？", f"branch-{expected_intent}")
    )

    names = [name for name, _ in events]
    intents = [payload for name, payload in events if name == "intent"]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert "error" not in names
    assert intents[-1]["intent"] == expected_intent
    assert intents[-1]["confidence"] == 1.0
    assert "HTTP" in intents[-1]["reason"]


def test_explicit_branch_does_not_leak_into_next_chat_request(isolated_runtime: AgentRuntime) -> None:
    """显式分支写下的强制意图，必须被同一 thread_id 的 /chat 自动分类清除。"""
    _prepare(isolated_runtime)
    thread_id = "branch-reset"
    asyncio.run(_stream_post("/branch/fallback", "退款多久到账？", thread_id))
    events = asyncio.run(_stream_chat("退款多久到账？", thread_id))

    intent = [payload for name, payload in events if name == "intent"][-1]
    assert intent["intent"] == "knowledge"
    assert intent["reason"] != "由显式 HTTP 分支路由指定"
