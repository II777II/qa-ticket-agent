"""物流试点分支：确定性预处理 + Agent/Tool 循环。"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from backend.application.agent.prompts import LOGISTICS_SYSTEM_PROMPT
from backend.domain.intent import ORDER_NO_RE

MAX_LOGISTICS_STEPS = 4


def _last_human_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def logistics_prepare_node(state: dict[str, Any]) -> dict[str, Any]:
    """提取物流查询条件；复杂决策交给后面的 Agent。"""
    text = state.get("question") or _last_human_text(state.get("messages", []))
    slots = dict(state.get("slots") or {})
    order_no = ORDER_NO_RE.search(text)
    if order_no:
        slots["order_no"] = order_no.group(0).upper()
    return {"slots": slots, "logistics_steps": 0}


def logistics_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    model = llm.bind_tools(list(tools)) if tools else llm

    def node(state: dict[str, Any]) -> dict[str, Any]:
        history = [message for message in state.get("messages", []) if not isinstance(message, SystemMessage)]
        answer = model.invoke([SystemMessage(content=LOGISTICS_SYSTEM_PROMPT), *history])
        return {
            "messages": [answer],
            "logistics_steps": int(state.get("logistics_steps", 0)) + 1,
        }

    return node


def create_logistics_tools_node(tools: Sequence[BaseTool]) -> ToolNode:
    return ToolNode(list(tools))


def route_logistics(state: dict[str, Any]) -> str:
    """有工具调用且未超预算时进入 tools，否则结束。"""
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return "end"
    if int(state.get("logistics_steps", 0)) >= MAX_LOGISTICS_STEPS:
        return "guard"
    return "tools"


def logistics_guard_node(_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            AIMessage(content="物流查询步骤过多，已停止自动调用工具。请补充订单号后重试。")
        ]
    }
