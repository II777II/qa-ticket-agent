"""LangGraph 主干：预处理 → LLM 意图识别 → 四路路由。

    START → preprocess → classify ─┬→ knowledge → END
                                   ├→ query     → END
                                   ├→ service   → END
                                   └→ fallback  → END

四路依据：知识咨询 / 订单查询 / 售后业务办理 / 投诉·闲聊·转人工。
POC 的 service 分支只生成「工单草稿」并追问缺失槽位，不直接建单。
"""

from __future__ import annotations

from typing import Any, Callable, NotRequired, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import StreamWriter

from backend.application.agent.classifier import classify_intent
from backend.application.agent.prompts import SYSTEM_PROMPT
from backend.application.contracts import (
    EVENT_CITATION,
    EVENT_INTENT,
    EVENT_ORDER,
    EVENT_SERVICE_DRAFT,
)
from backend.application.orders import OrderService
from backend.application.orders.service import order_summary
from backend.domain.intent import (
    IntentName,
    ORDER_NO_RE,
    extract_order_keyword,
    extract_service_slots,
    guess_category,
)
from backend.infrastructure.retrieval.in_memory import format_context

INTENTS = {"knowledge", "query", "service", "fallback"}
TRANSFER_HINTS = ("转人工", "人工客服", "找人工", "客服电话", "投诉", "差评")


class AgentState(MessagesState):
    question: NotRequired[str]
    requested_intent: NotRequired[IntentName | None]
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


def _emit(writer: StreamWriter, event: str, data: dict[str, Any]) -> None:
    """按 LangGraph custom 流的约定发送一个业务事件。"""
    writer({"event": event, "data": data})


def _preprocess_node(state: AgentState) -> dict[str, Any]:
    text = _last_human_text(state["messages"]).strip()
    return {"question": text[:2000] or "（空消息）"}


def _classify_node(llm: BaseChatModel) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        question = state.get("question") or _last_human_text(state["messages"])
        requested_intent = state.get("requested_intent")
        if requested_intent in INTENTS:
            output = {
                "intent": requested_intent,
                "confidence": 1.0,
                "intent_reason": "由显式 HTTP 分支路由指定",
                "slots": {},
            }
        else:
            result = classify_intent(question, llm)
            output = {
                "intent": result.intent,
                "confidence": result.confidence,
                "intent_reason": result.reason,
                "slots": result.slots,
            }
        _emit(
            writer,
            EVENT_INTENT,
            {
                "intent": output["intent"],
                "confidence": output["confidence"],
                "reason": output["intent_reason"],
                "slots": output["slots"],
            },
        )
        return output

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
) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        history = [message for message in state["messages"] if not isinstance(message, SystemMessage)]
        question = state.get("question") or _last_human_text(history)
        prompt = system_prompt
        citations: list[dict[str, Any]] = []
        if retriever is not None and question:
            documents = _retrieve(retriever, question)
            if documents:
                citations = _to_citations(documents)
                prompt = f"{system_prompt}\n\n{format_context(documents)}"
        for citation in citations:
            _emit(writer, EVENT_CITATION, citation)
        answer = llm.invoke([SystemMessage(content=prompt), *history])
        return {"messages": [answer], "retrieved": citations}

    return node


def _query_node(orders: OrderService | None) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
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
        _emit(writer, EVENT_ORDER, {"orders": summaries})
        lines = [f"查到 {len(summaries)} 笔订单："]
        for order in summaries:
            items = " / ".join(item["name"] for item in order["items"])
            lines.append(
                f"- {order['order_no']} ｜ {order['status']} ｜ 应付 ¥{order['payable_amount']:.2f} ｜ {items}"
            )
        lines.append("如果这不是你要找的订单，请把订单号发我。")
        return {"messages": [AIMessage(content="\n".join(lines))], "orders": summaries}

    return node


def _service_node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
    question = state.get("question") or _last_human_text(state["messages"])
    recognized = extract_service_slots(question)
    intent_slots = state.get("slots", {})
    order_no = recognized.get("order_no") or intent_slots.get("order_no", "")
    contact = recognized.get("contact") or intent_slots.get("contact", "")
    service_type = recognized.get("service_type") or intent_slots.get("service_type", "")
    category = recognized.get("category") or intent_slots.get("category") or guess_category(question)
    title = f"{service_type or '售后'}办理 · {order_no or '待补充订单号'}"
    description = question
    draft = {
        "status": "ready" if order_no and contact and service_type and len(description) >= 10 else "draft",
        "title": title[:60],
        "description": description,
        "category": category,
        "priority": "中",
        "order_no": order_no,
        "contact": contact,
        "service_type": service_type,
        "slots": {
            key: value
            for key, value in {
                "order_no": order_no,
                "contact": contact,
                "service_type": service_type,
                "category": category,
            }.items()
            if value
        },
        "requires_confirmation": True,
    }
    missing = []
    if not service_type:
        missing.append("service_type")
    if not order_no:
        missing.append("order_no")
    if not contact:
        missing.append("contact")
    if len(description) < 10:
        missing.append("description")
    draft["missing"] = missing
    draft["ready"] = not missing
    draft["status"] = "ready" if draft["ready"] else "draft"
    _emit(writer, EVENT_SERVICE_DRAFT, draft)

    labels = {
        "service_type": "业务类型",
        "order_no": "订单号",
        "contact": "联系人",
        "description": "问题描述",
    }
    lines = [
        "已整理业务办理草稿：",
        f"- 业务类型：{service_type or '待补充'}",
        f"- 订单号：{order_no or '待补充'}",
        f"- 联系人：{contact or '待补充'}",
        f"- 分类：{category}",
        f"- 标题：{draft['title']}",
        f"- 优先级：{draft['priority']}",
    ]
    if missing:
        lines.append(f"还缺少：{'、'.join(labels[item] for item in missing)}，请在右侧补齐后确认。")
    else:
        lines.append("槽位已齐全，请在右侧核对并点击“确认提交”。")
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
