"""编排用例：条件边、工具节点、RAG 注入与降级。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from backend.application.agent import build_graph, create_tools
from backend.application.agent.graph import AgentState, route_after_agent
from backend.application.orders import OrderService
from backend.application.tickets import TicketService
from backend.infrastructure.llm.mock import FakeChatModel
from backend.infrastructure.persistence.json_store import JsonTicketStore
from backend.infrastructure.persistence.factory import create_order_store
from backend.infrastructure.retrieval.in_memory import CONTEXT_HEADER, InMemoryRetriever


def _build(store: JsonTicketStore, retriever=None):
    llm = FakeChatModel()
    tools = create_tools(TicketService(store), OrderService(create_order_store()))
    graph = build_graph(llm=llm, tools=tools, retriever=retriever, checkpointer=InMemorySaver())
    return graph, tools


def test_route_goes_to_tools_only_with_tool_calls() -> None:
    with_tool_call: AgentState = {
        "messages": [AIMessage(content="", tool_calls=[{"name": "create_ticket", "args": {}, "id": "c1", "type": "tool_call"}])]
    }
    without: AgentState = {"messages": [AIMessage(content="直接回答")]}
    assert route_after_agent(with_tool_call) == "tools"
    assert route_after_agent(without) == "__end__"


def test_plain_question_returns_answer_without_tools(store: JsonTicketStore) -> None:
    graph, _ = _build(store)
    state = graph.invoke({"messages": [HumanMessage(content="你好，工单系统怎么用？")]}, {"configurable": {"thread_id": "t1"}})
    assert isinstance(state["messages"][-1], AIMessage)
    assert not any(isinstance(message, ToolMessage) for message in state["messages"])
    assert store.count() == 0


def test_tool_branch_creates_ticket(store: JsonTicketStore) -> None:
    """说「帮我建个工单」→ 走 tools 节点 → 回到 agent 总结。"""
    graph, _ = _build(store)
    state = graph.invoke(
        {"messages": [HumanMessage(content="帮我建个售后工单，商品有质量问题，联系我 zhang.san@corp.com")]},
        {"configurable": {"thread_id": "t2"}},
    )
    assert any(isinstance(message, ToolMessage) for message in state["messages"])
    assert store.count() == 1


def test_retrieved_fragments_recorded_in_state(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph, _ = _build(store, retriever)
    state = graph.invoke({"messages": [HumanMessage(content="退款多久到账？")]}, {"configurable": {"thread_id": "t3"}})
    citations = state["retrieved"]
    assert citations
    assert citations[0]["source"] == "KB-EC-0020.html"
    assert citations[0]["index"] == 1
    assert 0 < len(citations[0]["snippet"]) <= 160


def test_context_injected_into_system_prompt(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    """系统提示里必须带参考资料块，否则模型无从引用。"""
    from backend.application.agent.graph import _prepare_messages

    messages, citations = _prepare_messages([HumanMessage(content="退款多久到账")], retriever, "系统提示")
    assert isinstance(messages[0], SystemMessage)
    assert CONTEXT_HEADER in messages[0].content
    assert "系统提示" in messages[0].content
    assert citations


def test_no_citation_for_unrelated_question(store: JsonTicketStore, retriever: InMemoryRetriever) -> None:
    graph, _ = _build(store, retriever)
    state = graph.invoke({"messages": [HumanMessage(content="今天午饭吃什么")]}, {"configurable": {"thread_id": "t4"}})
    assert state["retrieved"] == []


def test_retriever_failure_degrades_gracefully(store: JsonTicketStore) -> None:
    """检索抛异常不能拖垮整轮对话。"""

    class BoomRetriever:
        def invoke(self, _query):
            raise RuntimeError("向量库连接超时")

    graph, _ = _build(store, BoomRetriever())
    state = graph.invoke({"messages": [HumanMessage(content="VPN 报 691")]}, {"configurable": {"thread_id": "t5"}})
    assert isinstance(state["messages"][-1], AIMessage)
    assert state["retrieved"] == []


def test_multi_turn_memory_is_isolated_by_thread(store: JsonTicketStore) -> None:
    graph, _ = _build(store)
    config_a = {"configurable": {"thread_id": "thread-a"}}
    config_b = {"configurable": {"thread_id": "thread-b"}}
    graph.invoke({"messages": [HumanMessage(content="第一轮提问")]}, config_a)
    graph.invoke({"messages": [HumanMessage(content="第二轮提问")]}, config_a)

    state_a = graph.get_state(config_a).values
    state_b = graph.get_state(config_b).values
    assert len(state_a["messages"]) >= 4
    assert state_b.get("messages", []) == []
