"""整链用例：按演示脚本走一遍问答 → 建单 → 催单 → 转人工 → 多轮追问。"""

from __future__ import annotations

import asyncio
import json

from backend.application.chat import ChatService
from backend.application.runtime import AgentRuntime


async def _collect(runtime: AgentRuntime, message: str, thread: str) -> dict:
    collected = {"text": "", "tools": [], "tickets": [], "citations": [], "errors": []}
    async for event, payload in ChatService(runtime).stream(message, thread):
        if event == "token":
            collected["text"] += payload["text"]
        elif event == "tool":
            collected["tools"].append(payload)
        elif event == "ticket":
            collected["tickets"].extend(payload["tickets"])
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
    assert not consulted["tickets"]

    # 2. 明确要求建单：走 create_ticket
    created = _turn(runtime, "帮我建个工单，会议室打印机装不上驱动，联系我 zhang.san@corp.com", thread)
    tool_names = [tool["name"] for tool in created["tools"]]
    assert "create_ticket" in tool_names
    assert len(created["tickets"]) == 1
    ticket = created["tickets"][0]
    assert ticket["category"] == "办公设备"
    assert ticket["status"] == "待受理"
    assert ticket["contact"] == "zhang.san@corp.com"

    # 3. 催单：时间线追加记录
    urged = _turn(runtime, f"{ticket['id']} 处理到哪了？催一下", thread)
    assert any(tool["name"] == "query_ticket" for tool in urged["tools"])
    assert any("催单" in event["action"] for event in urged["tickets"][0]["events"])

    # 4. 转人工：状态变更
    escalated = _turn(runtime, f"{ticket['id']} 帮我转人工", thread)
    assert any(tool["name"] == "escalate_to_human" for tool in escalated["tools"])
    assert escalated["tickets"][0]["status"] == "处理中"

    # 5. 多轮追问：上下文累积且仍能检索
    followup = _turn(runtime, "那退款失败会怎么处理？", thread)
    assert followup["citations"], "追问同样应命中知识库"
    state = asyncio.run(runtime.graph.aget_state({"configurable": {"thread_id": thread}})).values
    assert len(state["messages"]) >= 8


def test_ticket_is_persisted_to_json(isolated_runtime: AgentRuntime) -> None:
    """对话建的工单必须落到工单文件里——重启进程不丢。"""
    created = _turn(isolated_runtime, "帮我建个工单，邮箱收不到外部邮件，联系我 li.si@corp.com", "flow-2")
    ticket_id = created["tickets"][0]["id"]

    payload = json.loads(isolated_runtime.store.path.read_text(encoding="utf-8"))
    stored = {item["id"]: item for item in payload["tickets"]}
    assert ticket_id in stored
    assert stored[ticket_id]["category"] == "邮件与协作"


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
