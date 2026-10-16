"""LangGraph 编排：POC 只实现 Agent + Tool 两个分支。

    START -> agent -> (有 tool_calls) -> tools -> agent -> ...
                   -> (无 tool_calls) -> END

设计上预留了 Planner / Executor / Validator / Summarizer 四节点扩展：
节点拆成一个函数、条件边集中在一处判断，加节点时不用改现有节点。
RAG 的注入点也留在这里（_inject_retrieved_context），阶段四填内容。
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

DEFAULT_SYSTEM_PROMPT = """你是企业 IT 服务台的智能助理，面向公司内部员工。

行为准则：
1. 优先基于知识库回答，不要编造公司内部流程、系统地址、审批权限。
2. 信息不足时先追问关键细节（例如报错原文、影响范围、设备型号），不要瞎猜。
3. 无法用知识库解决、或用户明确要求时，再帮他建工单，并把问题描述整理清楚。
4. 回答用中文，简洁、分点、可执行。

工具使用：
- create_ticket：建单。标题、描述、分类、优先级、联系人五个字段都要来自用户的原话或已有历史，
  联系人不明确就先问，不要用「未知」凑数；用户只是在咨询时不要建单。
- query_ticket：查进度、催单。有单号按单号查，只说「我的工单」就按联系人查。
- escalate_to_human：用户要求转人工，或问题确实超出你的能力范围时使用。
- 不要把工具返回的 JSON 原样念给用户，也不要自己编造单号或状态。"""


def route_after_agent(state: MessagesState) -> str:
    """条件边：Agent 产出了 tool_calls 就去工具节点，否则本轮结束。"""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def _prepare_messages(
    messages: Sequence[BaseMessage],
    retriever: Any | None,
    system_prompt: str,
) -> list[BaseMessage]:
    prepared = list(messages)
    if system_prompt and not isinstance(prepared[0], SystemMessage):
        prepared.insert(0, SystemMessage(content=system_prompt))
    if retriever is not None:
        prepared = _inject_retrieved_context(prepared, retriever)
    return prepared


def _inject_retrieved_context(
    messages: list[BaseMessage],
    retriever: Any,
) -> list[BaseMessage]:
    """RAG 注入点：阶段四实现。

    命中片段会以「参考资料」形式插到当前用户消息之前，同时把出处
    （文件名 / 标题 / 片段）通过 citation 事件回传前端展示引用。
    阶段一、二 retriever 为 None，这里返回原消息。
    """
    return messages


def build_agent_node(
    llm_with_tools: BaseChatModel,
    retriever: Any | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> Callable[[MessagesState], dict[str, list[BaseMessage]]]:
    def agent_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        messages = _prepare_messages(state["messages"], retriever, system_prompt)
        return {"messages": [llm_with_tools.invoke(messages)]}

    return agent_node


def build_graph(
    *,
    llm: BaseChatModel,
    tools: Sequence[BaseTool] = (),
    retriever: Any | None = None,
    checkpointer: Any | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
):
    """把模型、工具、检索器、记忆拼成一张可执行的图。"""
    tool_list = list(tools)
    llm_with_tools = llm.bind_tools(tool_list) if tool_list else llm

    builder = StateGraph(MessagesState)
    builder.add_node("agent", build_agent_node(llm_with_tools, retriever, system_prompt))
    builder.add_edge(START, "agent")

    if tool_list:
        builder.add_node("tools", ToolNode(tool_list))
        builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
        builder.add_edge("tools", "agent")
    else:
        # 还没有工具时图退化成 Agent -> END；阶段二注册工具后条件边自动生效。
        builder.add_edge("agent", END)

    return builder.compile(checkpointer=checkpointer)
