"""编排用例：预处理 → 意图识别 → 四路路由。"""

from __future__ import annotations

import pytest

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.application.agent import build_graph
from backend.application.agent.graph import route_by_intent
from backend.application.orders import OrderService
from backend.infrastructure.llm.mock import FakeChatModel
from backend.infrastructure.persistence.factory import create_order_store
from backend.infrastructure.persistence.json_store import JsonTicketStore
from backend.infrastructure.retrieval.in_memory import InMemoryRetriever


def _build(store: JsonTicketStore, retriever=None):
    return build_graph(
        llm=FakeChatModel(),
        retriever=retriever,
        checkpointer=InMemorySaver(),
        order_service=OrderService(create_order_store()),
    )


def test_route_by_intent_maps_four_ways() -> None:
    assert route_by_intent({"messages": [], "intent": "knowledge"}) == "knowledge"
    assert route_by_intent({"messages": [], "intent": "query"}) == "query"
    assert route_by_intent({"messages": [], "intent": "service"}) == "service"
    assert route_by_intent({"messages": [], "intent": "fallback"}) == "fallback"
    assert route_by_intent({"messages": [], "intent": "unknown"}) == "fallback"


@pytest.mark.parametrize("intent", ["knowledge", "query", "service", "fallback"])
def test_requested_intent_forces_graph_branch(
    store: JsonTicketStore,
    retriever: InMemoryRetriever,
    intent: str,
) -> None:
    graph = _build(store, retriever)
    state = graph.invoke(
        {
            "messages": [HumanMessage(content="退款多久到账？")],
            "requested_intent": intent,
        },
        {"configurable": {"thread_id": f"forced-{intent}"}},
    )
    assert state["intent"] == intent
    assert state["intent_reason"] == "由显式 HTTP 分支路由指定"


def test_next_turn_clears_requested_intent(
    store: JsonTicketStore,
    retriever: InMemoryRetriever,
) -> None:
    graph = _build(store, retriever)
    config = {"configurable": {"thread_id": "forced-reset"}}
    graph.invoke(
        {
            "messages": [HumanMessage(content="退款多久到账？")],
            "requested_intent": "fallback",
        },
        config,
    )
    state = graph.invoke(
        {
            "messages": [HumanMessage(content="退款多久到账？")],
            "requested_intent": None,
        },
        config,
    )
    assert state["intent"] == "knowledge"
    assert state["intent_reason"] != "由显式 HTTP 分支路由指定"


def test_knowledge_branch_retrieves(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph = _build(store, retriever)
    state = graph.invoke({"messages": [HumanMessage(content="退款多久到账？")]}, {"configurable": {"thread_id": "t1"}})
    assert state["intent"] == "knowledge"
    assert state["retrieved"]
    assert state["retrieved"][0]["source"] == "KB-EC-0020.html"
    assert isinstance(state["messages"][-1], AIMessage)
    assert "[1]" in state["messages"][-1].content


def test_query_branch_returns_orders_without_rag(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph = _build(store, retriever)
    state = graph.invoke(
        {"messages": [HumanMessage(content="帮我查询张三的订单")]}, {"configurable": {"thread_id": "t2"}}
    )
    assert state["intent"] == "query"
    assert state["orders"]
    assert state.get("retrieved", []) == []
    assert "SO" in state["messages"][-1].content


def test_service_branch_builds_draft_only(store: JsonTicketStore) -> None:
    graph = _build(store)
    state = graph.invoke(
        {"messages": [HumanMessage(content="商品损坏了，帮我建个工单，联系我 a@corp.com")]},
        {"configurable": {"thread_id": "t3"}},
    )
    assert state["intent"] == "service"
    assert state["draft"]["status"] == "draft"
    assert "草稿" in state["messages"][-1].content
    assert store.count() == 0  # 只生成草稿，不直接建单


def test_fallback_branch_for_complaint(store: JsonTicketStore) -> None:
    graph = _build(store)
    state = graph.invoke({"messages": [HumanMessage(content="我要投诉")]}, {"configurable": {"thread_id": "t4"}})
    assert state["intent"] == "fallback"
    assert "投诉" in state["messages"][-1].content or "转人工" in state["messages"][-1].content


def test_retriever_failure_degrades_gracefully(store: JsonTicketStore) -> None:
    class BoomRetriever:
        def invoke(self, _query):
            raise RuntimeError("向量库连接超时")

    graph = _build(store, BoomRetriever())
    state = graph.invoke({"messages": [HumanMessage(content="退款多久到账")]}, {"configurable": {"thread_id": "t5"}})
    assert isinstance(state["messages"][-1], AIMessage)
    assert state["retrieved"] == []


def test_multi_turn_memory_is_isolated_by_thread(store: JsonTicketStore) -> None:
    graph = _build(store)
    config_a = {"configurable": {"thread_id": "thread-a"}}
    config_b = {"configurable": {"thread_id": "thread-b"}}
    graph.invoke({"messages": [HumanMessage(content="退款多久到账")]}, config_a)
    graph.invoke({"messages": [HumanMessage(content="那发票怎么开")]}, config_a)

    state_a = graph.get_state(config_a).values
    state_b = graph.get_state(config_b).values
    assert len(state_a["messages"]) >= 4
    assert state_b.get("messages", []) == []
