"""LangGraph 主干：预处理 → LLM 意图识别 → 四路路由。

    START → preprocess → classify ─┬→ knowledge → END
                                   ├→ query     → END
                                   ├→ service   → END
                                   └→ fallback  → END

四路依据：知识咨询 / 订单查询 / 售后业务办理 / 投诉·闲聊·转人工。
POC 的 service 分支只生成「工单草稿」并追问缺失槽位，不直接建单。
"""

from __future__ import annotations

import re
from typing import Any, Callable, NotRequired, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph

from backend.application.agent.classifier import classify_intent
from backend.application.agent.prompts import SYSTEM_PROMPT
from backend.application.orders import OrderService
from backend.application.orders.service import order_summary
from backend.domain.intent import ORDER_NO_RE, extract_order_keyword, guess_category
from backend.infrastructure.retrieval.in_memory import format_context

INTENTS = {"knowledge", "query", "service", "fallback"}
TRANSFER_HINTS = ("转人工", "人工客服", "找人工", "客服电话", "投诉", "差评")


class AgentState(MessagesState):
    question: NotRequired[str]
    intent: NotRequired[str]
    confidence: NotRequired[float]
    intent_reason: NotRequired[str]
    slots: NotRequired[dict[str, str]]
    retrieved: NotRequired[list[dict[str, Any]]]
    orders: NotRequired[list[dict[str, Any]]]
    draft: NotRequired[dict[str, Any]]


def _last_human_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _as_text(message.content)
    return ""


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in content
            if isinstance(block, (str, dict))
        )
    return str(content)


def route_by_intent(state: AgentState) -> str:
    """一级意图路由：只允许四个合法分支，未知意图走兜底。"""
    intent = state.get("intent", "fallback")
    return intent if intent in INTENTS else "fallback"


def _preprocess_node(state: AgentState) -> dict[str, Any]:
    text = _last_human_text(state["messages"]).strip()
    return {"question": text[:2000] or "（空消息）"}


def _classify_node(llm: BaseChatModel) -> Callable[[AgentState], dict[str, Any]]:
    def node(state: AgentState) -> dict[str, Any]:
        question = state.get("question") or _last_human_text(state["messages"])
        result = classify_intent(question, llm)
        return {
            "intent": result.intent,
            "confidence": result.confidence,
            "intent_reason": result.reason,
            "slots": result.slots,
        }

    return node


def _retrieve(retriever: Any, question: str) -> list[Document]:
    try:
        return list(retriever.invoke(question))
    except Exception:
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


def _knowledge_node(
    llm: BaseChatModel,
    retriever: Any | None,
    system_prompt: str,
) -> Callable[[AgentState], dict[str, Any]]:
    def node(state: AgentState) -> dict[str, Any]:
        history = [message for message in state["messages"] if not isinstance(message, SystemMessage)]
        question = state.get("question") or _last_human_text(history)
        prompt = system_prompt
        citations: list[dict[str, Any]] = []
        if retriever is not None and question:
            documents = _retrieve(retriever, question)
            if documents:
                citations = _to_citations(documents)
                prompt = f"{system_prompt}\n\n{format_context(documents)}"
        answer = llm.invoke([SystemMessage(content=prompt), *history])
        return {"messages": [answer], "retrieved": citations}

    return node


def _query_node(orders: OrderService | None) -> Callable[[AgentState], dict[str, Any]]:
    def node(state: AgentState) -> dict[str, Any]:
        question = state.get("question") or _last_human_text(state["messages"])
        order_no = ORDER_NO_RE.search(question)
        results = []
        if orders is not None:
            if order_no:
                record = orders.get(order_no.group(0))
                results = [record] if record is not None else []
            else:
                results = orders.search(q=extract_order_keyword(question), limit=5)

        if not results:
            text = "没有找到匹配的订单，请提供订单号（SO 开头）或收货人姓名/手机号。"
            return {"messages": [AIMessage(content=text)], "orders": []}

        summaries = [order_summary(order) for order in results]
        lines = [f"查到 {len(summaries)} 笔订单："]
        for order in summaries:
            items = " / ".join(item["name"] for item in order["items"])
            lines.append(
                f"- {order['order_no']} ｜ {order['status']} ｜ 应付 ¥{order['payable_amount']:.2f} ｜ {items}"
            )
        lines.append("如果这不是你要找的订单，请把订单号发我。")
        return {"messages": [AIMessage(content="\n".join(lines))], "orders": summaries}

    return node


def _clean_draft_title(text: str) -> str:
    title = text
    for hint in ("帮我建个工单", "帮我建个售后工单", "售后工单", "建个工单", "建单", "帮我", "麻烦"):
        title = title.replace(hint, "")
    title = re.sub(r"[，,。；;、！!？?：:\s]+", " ", title).strip()
    return (title or "售后问题")[:40]


def _service_node(state: AgentState) -> dict[str, Any]:
    question = state.get("question") or _last_human_text(state["messages"])
    order_no = ORDER_NO_RE.search(question)
    draft = {
        "status": "draft",
        "title": _clean_draft_title(question),
        "category": guess_category(question),
        "priority": "中",
        "order_no": order_no.group(0).upper() if order_no else "",
        "contact": "",
    }
    lines = [
        "已整理售后工单草稿：",
        f"- 标题：{draft['title']}",
        f"- 分类：{draft['category']}",
        f"- 优先级：{draft['priority']}",
    ]
    missing = []
    if not draft["order_no"]:
        missing.append("订单号")
    if not draft["contact"]:
        missing.append("联系人")
    if missing:
        lines.append(f"还缺少：{'、'.join(missing)}，补充后我再帮你提交。")
    else:
        lines.append("请确认后提交（演示版暂不直接创建工单）。")
    return {"messages": [AIMessage(content="\n".join(lines))], "draft": draft}


def _fallback_node(state: AgentState) -> dict[str, Any]:
    question = state.get("question") or _last_human_text(state["messages"])
    if any(hint in question for hint in TRANSFER_HINTS):
        text = (
            "已收到转人工/投诉请求。当前演示版未接入人工坐席，"
            "可以先查看帮助中心的相关规则，或在订单查询页确认订单状态。"
        )
    else:
        text = "你好，我是电商智能客服，可以帮你查询订单、解释帮助中心的规则与流程。"
    return {"messages": [AIMessage(content=text)]}


def build_graph(
    *,
    llm: BaseChatModel,
    tools: Sequence[BaseTool] = (),  # 兼容旧调用；四路路由分支自行调用用例/工具
    retriever: Any | None = None,
    checkpointer: Any | None = None,
    order_service: OrderService | None = None,
    system_prompt: str = SYSTEM_PROMPT,
):
    builder = StateGraph(AgentState)
    builder.add_node("preprocess", _preprocess_node)
    builder.add_node("classify", _classify_node(llm))
    builder.add_node("knowledge", _knowledge_node(llm, retriever, system_prompt))
    builder.add_node("query", _query_node(order_service))
    builder.add_node("service", _service_node)
    builder.add_node("fallback", _fallback_node)

    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "classify")
    builder.add_conditional_edges(
        "classify",
        route_by_intent,
        {"knowledge": "knowledge", "query": "query", "service": "service", "fallback": "fallback"},
    )
    for branch in ("knowledge", "query", "service", "fallback"):
        builder.add_edge(branch, END)

    return builder.compile(checkpointer=checkpointer)
