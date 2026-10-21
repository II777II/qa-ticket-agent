"""编排用例：预处理 → 三路意图识别 → read 工具分派。"""

from __future__ import annotations

import asyncio

import pytest

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.application.graph import build_graph, route_by_intent
from backend.infrastructure.llm import FakeChatModel
from backend.infrastructure.retrieval import InMemoryRetriever
from backend.infrastructure.storage import JsonTicketStore, create_order_store


def _build(store: JsonTicketStore, retriever=None):
    return build_graph(
        llm=FakeChatModel(),
        retriever=retriever,
        checkpointer=InMemorySaver(),
        order_service=create_order_store(),
    )


def test_route_by_intent_maps_three_ways() -> None:
    assert route_by_intent({"messages": [], "intent": "read"}) == "read"
    assert route_by_intent({"messages": [], "intent": "write"}) == "write"
    assert route_by_intent({"messages": [], "intent": "human"}) == "human"
    assert route_by_intent({"messages": [], "intent": "unknown"}) == "human"


@pytest.mark.parametrize("intent", ["read", "write", "human"])
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


def test_next_turn_clears_requested_intent(
    store: JsonTicketStore,
    retriever: InMemoryRetriever,
) -> None:
    graph = _build(store, retriever)
    config = {"configurable": {"thread_id": "forced-reset"}}
    graph.invoke(
        {
            "messages": [HumanMessage(content="退款多久到账？")],
            "requested_intent": "human",
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
    assert state["intent"] == "read"


def test_read_branch_uses_knowledge_tool(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph = _build(store, retriever)
    state = graph.invoke({"messages": [HumanMessage(content="退款多久到账？")]}, {"configurable": {"thread_id": "t1"}})
    assert state["intent"] == "read"
    assert state["retrieved"]
    assert state["retrieved"][0]["source"] == "KB-EC-0020.html"
    assert isinstance(state["messages"][-1], AIMessage)
    assert "[1]" in state["messages"][-1].content


def test_read_branch_uses_order_tool_without_rag(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph = _build(store, retriever)
    state = graph.invoke(
        {"messages": [HumanMessage(content="查询用户 10018 的订单")]}, {"configurable": {"thread_id": "t2"}}
    )
    assert state["intent"] == "read"
    assert state["orders"]
    assert state.get("retrieved", []) == []
    assert "SO" in state["messages"][-1].content


def test_write_branch_builds_draft_only(store: JsonTicketStore) -> None:
    graph = _build(store)
    state = graph.invoke(
        {"messages": [HumanMessage(content="商品损坏了，帮我建个工单，联系我 a@corp.com")]},
        {"configurable": {"thread_id": "t3"}},
    )
    assert state["intent"] == "write"
    assert state["draft"]["status"] == "draft"
    assert state["draft"]["contact"] == "a@corp.com"
    assert "order_no" in state["draft"]["missing"]
    assert "service_type" in state["draft"]["missing"]
    assert state["draft"]["requires_confirmation"] is True
    assert "草稿" in state["messages"][-1].content
    assert store.count() == 0  # 只生成草稿，不直接建单


def test_service_draft_recognizes_complete_slots(store: JsonTicketStore) -> None:
    graph = _build(store)
    state = graph.invoke(
        {
            "messages": [
                HumanMessage(
                    content="订单 SO202609150020 的商品损坏，申请换货，联系电话 13800138000"
                )
            ]
        },
        {"configurable": {"thread_id": "service-ready"}},
    )
    draft = state["draft"]
    assert state["intent"] == "write"
    assert draft["ready"] is True
    assert draft["missing"] == []
    assert draft["order_no"] == "SO202609150020"
    assert draft["contact"] == "13800138000"
    assert draft["service_type"] == "换货"
    assert draft["slots"]["service_type"] == "换货"
    assert store.count() == 0


def test_service_node_emits_langgraph_custom_event(
    store: JsonTicketStore,
    retriever: InMemoryRetriever,
) -> None:
    graph = _build(store, retriever)

    async def collect() -> list[dict]:
        return [
            payload
            async for payload in graph.astream(
                {
                    "messages": [
                        HumanMessage(
                            content="订单 SO202609150020 商品损坏，申请维修，联系电话 13800138000"
                        )
                    ]
                },
                {"configurable": {"thread_id": "custom-event"}},
                stream_mode="custom",
            )
        ]

    payloads = asyncio.run(collect())
    drafts = [payload for payload in payloads if payload.get("event") == "service_draft"]
    assert len(drafts) == 1
    assert drafts[0]["data"]["service_type"] == "维修"


def test_human_branch_for_complaint(store: JsonTicketStore) -> None:
    graph = _build(store)
    state = graph.invoke({"messages": [HumanMessage(content="我要投诉")]}, {"configurable": {"thread_id": "t4"}})
    assert state["intent"] == "human"
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
