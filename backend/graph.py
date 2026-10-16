"""LangGraph 编排：POC 只实现 Agent + Tool 两个分支。

    START -> agent -> (有 tool_calls) -> tools -> agent -> ...
                   -> (无 tool_calls) -> END

设计上预留了 Planner / Executor / Validator / Summarizer 四节点扩展：
节点拆成一个函数、条件边集中在一处判断，加节点时不用改现有节点。
RAG 在 agent 节点内做：检索 → 拼进系统提示 → 把引用写回 state 的 retrieved 字段。
检索到的片段不进消息历史，所以多轮对话不会被历史资料撑爆。
"""

from __future__ import annotations

from typing import Any, Callable, NotRequired, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from backend.retrievers.memory import format_context

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
- 不要把工具返回的 JSON 原样念给用户，也不要自己编造单号或状态。

引用规范：
- 系统消息里带【参考资料】时，回答要基于它，并在相应位置标出来源编号，例如「…（[1]）」。
- 资料里没有的内容不要脑补；可以说明「知识库里没有这个流程」，再建议建工单。"""


class AgentState(MessagesState):
    """消息历史之外多存一个字段：本轮检索命中的片段（供 SSE 的 citation 事件使用）。"""

    retrieved: NotRequired[list[dict[str, Any]]]


def route_after_agent(state: AgentState) -> str:
    """条件边：Agent 产出了 tool_calls 就去工具节点，否则本轮结束。"""
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # 有些模型返回内容块列表
        return "".join(
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in content
            if isinstance(block, (str, dict))
        )
    return str(content)


def _prepare_messages(
    messages: Sequence[BaseMessage],
    retriever: Any | None,
    system_prompt: str,
) -> tuple[list[BaseMessage], list[dict[str, Any]]]:
    """重建系统提示（有检索器时带上参考资料），返回 (消息列表, 本轮引用)。"""
    history = [message for message in messages if not isinstance(message, SystemMessage)]
    prompt = system_prompt
    citations: list[dict[str, Any]] = []

    if retriever is not None:
        question = next(
            (_text_of(message.content) for message in reversed(history) if isinstance(message, HumanMessage)),
            "",
        )
        if question:
            documents = _retrieve(retriever, question)
            if documents:
                citations = _to_citations(documents)
                prompt = f"{system_prompt}\n\n{format_context(documents)}"

    return [SystemMessage(content=prompt), *history], citations


def _retrieve(retriever: Any, question: str) -> list[Document]:
    """检索失败不该拖垮整轮对话，降级成「不带资料回答」。"""
    try:
        return list(retriever.invoke(question))
    except Exception:  # pragma: no cover - 检索异常兜底
        return []


def _to_citations(documents: Sequence[Document]) -> list[dict[str, Any]]:
    return [
        {
            "index": position,
            "source": document.metadata.get("source", ""),
            "title": document.metadata.get("title", ""),
            "snippet": document.page_content.strip()[:160],
            "score": document.metadata.get("score"),
        }
        for position, document in enumerate(documents, start=1)
    ]


def build_agent_node(
    llm_with_tools: BaseChatModel,
    retriever: Any | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
) -> Callable[[AgentState], dict[str, Any]]:
    def agent_node(state: AgentState) -> dict[str, Any]:
        messages, citations = _prepare_messages(state["messages"], retriever, system_prompt)
        return {"messages": [llm_with_tools.invoke(messages)], "retrieved": citations}

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

    builder = StateGraph(AgentState)
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
