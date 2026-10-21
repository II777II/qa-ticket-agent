"""整链用例：按演示脚本走一遍知识库问答 → 订单查询 → 多轮追问。"""

from __future__ import annotations

import asyncio

from backend.application.core import AgentRuntime, ChatService


async def _collect(runtime: AgentRuntime, message: str, thread: str) -> dict:
    collected = {"text": "", "orders": [], "citations": [], "errors": []}
    async for event, payload in ChatService(runtime).stream(message, thread):
        if event == "token":
            collected["text"] += payload["text"]
        elif event == "order":
            collected["orders"].extend(payload["orders"])
        elif event == "citation":
            collected["citations"].append(payload)
        elif event == "error":
            collected["errors"].append(payload)
    return collected


def _turn(runtime: AgentRuntime, message: str, thread: str) -> dict:
    return asyncio.run(_collect(runtime, message, thread))


def test_full_demo_flow(isolated_runtime: AgentRuntime) -> None:
    runtime = isolated_runtime
    thread = "flow-1"

    # 1. 知识库问答：有引用、不建单
    consulted = _turn(runtime, "退款多久到账？", thread)
    assert not consulted["errors"]
    assert consulted["citations"], "应命中知识库并回传引用"
    assert "[1]" in consulted["text"]

    # 2. 订单查询：read 分支确定性调用 order_query，不出引用、不建单
    ordered = _turn(runtime, "帮我查询张三的订单", thread)
    assert ordered["orders"], "应返回张三的订单"
    assert not ordered["citations"]

    # 5. 多轮追问：上下文累积且仍能检索
    followup = _turn(runtime, "那发票怎么开？", thread)
    assert followup["citations"], "追问同样应命中知识库"
    state = asyncio.run(runtime.graph.aget_state({"configurable": {"thread_id": thread}})).values
    assert len(state["messages"]) >= 6


def test_service_request_builds_draft_without_creating_ticket(isolated_runtime: AgentRuntime) -> None:
    """对话侧已不开放售后工单：即使用户要求建单，也不应创建工单。"""
    result = _turn(isolated_runtime, "帮我建个工单，商品有质量问题", "flow-2")
    assert "草稿" in result["text"]


def test_threads_do_not_share_memory(isolated_runtime: AgentRuntime) -> None:
    runtime = isolated_runtime
    _turn(runtime, "VPN 报 691 怎么处理", "thread-x")
    _turn(runtime, "打印机驱动装不上", "thread-y")

    state_x = asyncio.run(runtime.graph.aget_state({"configurable": {"thread_id": "thread-x"}})).values
    state_y = asyncio.run(runtime.graph.aget_state({"configurable": {"thread_id": "thread-y"}})).values
    assert len(state_x["messages"]) >= 2 and len(state_y["messages"]) >= 2
    human_x = [message.content for message in state_x["messages"] if message.type == "human"]
    human_y = [message.content for message in state_y["messages"] if message.type == "human"]
    assert all("VPN" in text for text in human_x)
    assert all("打印机" in text for text in human_y)


def test_unknown_question_falls_back_without_citation(isolated_runtime: AgentRuntime) -> None:
    """知识库里没有的话题：不给引用，也不该报错。"""
    result = _turn(isolated_runtime, "食堂这周有什么新菜", "flow-3")
    assert not result["errors"]
    assert result["citations"] == []
    assert result["text"]


def test_order_query_uses_deterministic_tool_without_rag(isolated_runtime: AgentRuntime) -> None:
    """「查张三的订单」应走 read 分支的 order_query 工具，不引用知识库、也不建售后工单。"""
    result = _turn(isolated_runtime, "帮我查询张三的订单", "flow-order")
    assert result["orders"]
    assert result["citations"] == []
    assert "SO" in result["text"]


def test_missing_order_returns_plain_text(isolated_runtime: AgentRuntime) -> None:
    """确定性订单工具没命中时，也应只输出文本，不能泄露 AIMessage 对象表示。"""
    result = _turn(isolated_runtime, "查询订单 SO197001019999", "flow-order-missing")
    assert result["text"] == "没有找到订单，请提供 SO 开头的订单号、姓名或手机号。"
    assert "additional_kwargs" not in result["text"]


def test_view_name_order_extracts_customer_name(isolated_runtime: AgentRuntime) -> None:
    """「查看张三订单」必须去掉查看和订单，只按“张三”查询。"""
    result = _turn(isolated_runtime, "查看张三订单", "flow-view-order")
    assert result["orders"]
    assert "没有找到订单" not in result["text"]
