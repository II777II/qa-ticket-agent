"""LangGraph 主干：预处理 → LLM 意图识别 → 五路路由。

    START → preprocess → classify ─┬→ knowledge → END
                                   ├→ query     → END
                                   ├→ service   → END
                                   ├→ logistics → agent ⇄ tools → END
                                   └→ fallback  → END

五路依据：知识咨询 / 订单查询 / 售后业务办理 / 物流查询 / 投诉·闲聊·转人工。
POC 的 service 分支只生成「工单草稿」并追问缺失槽位，不直接建单。
"""

from __future__ import annotations

from typing import Any, Callable, NotRequired, Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import StreamWriter

from backend.application.contracts import (
    EVENT_CITATION,
    EVENT_INTENT,
    EVENT_ORDER,
    EVENT_SERVICE_DRAFT,
)
from backend.application.orders import OrderService
from backend.application.orders.service import order_summary
from backend.domain.intent import (
    IntentResult,
    IntentName,
    ORDER_NO_RE,
    extract_order_keyword,
    extract_service_slots,
    guess_category,
    rule_classify,
)
from backend.infrastructure.config import settings
from backend.infrastructure.retrieval.in_memory import format_context

INTENTS = {"knowledge", "query", "service", "logistics", "fallback"}
TRANSFER_HINTS = ("转人工", "人工客服", "找人工", "客服电话", "投诉", "差评")
MAX_LOGISTICS_STEPS = 4

CLASSIFIER_PROMPT = """你是电商客服意图分类器。只分到以下五类之一：
knowledge（规则/流程咨询）、query（查询具体订单）、service（售后业务办理）、
logistics（物流/快递/配送查询）、fallback（闲聊、投诉或转人工）。
只输出 IntentResult JSON，不要 Markdown。"""

SYSTEM_PROMPT = """你是电商平台智能客服。优先根据帮助中心资料回答并标引用编号；
不要编造订单、物流或规则。信息不足时先追问。当前售后不会直接建单，只有用户在右侧确认后才提交。"""

LOGISTICS_SYSTEM_PROMPT = """你是电商物流查询助手。用户提供订单号、姓名或手机号时调用
query_order 查询真实状态；有工具结果后简洁总结，不输出原始 JSON，不编造物流单号。
信息不足时先追问，一次回答最多调用 2 次工具。"""


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
    logistics_steps: NotRequired[int]


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


def _classify_intent(question: str, llm: BaseChatModel) -> IntentResult:
    if settings.mock_mode:
        return rule_classify(question)
    try:
        result = llm.with_structured_output(IntentResult).invoke(
            [SystemMessage(content=CLASSIFIER_PROMPT), HumanMessage(content=question)]
        )
        if isinstance(result, IntentResult):
            return result
        if isinstance(result, dict):
            return IntentResult(**result)
    except Exception:
        pass
    return rule_classify(question)


def _logistics_prepare(state: AgentState) -> dict[str, Any]:
    slots = dict(state.get("slots") or {})
    match = ORDER_NO_RE.search(state.get("question") or "")
    if match:
        slots["order_no"] = match.group(0).upper()
    return {"slots": slots, "logistics_steps": 0}


def _logistics_agent_node(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
) -> Callable[[AgentState], dict[str, Any]]:
    model = llm.bind_tools(list(tools)) if tools else llm

    def node(state: AgentState) -> dict[str, Any]:
        history = [message for message in state["messages"] if not isinstance(message, SystemMessage)]
        answer = model.invoke([SystemMessage(content=LOGISTICS_SYSTEM_PROMPT), *history])
        return {
            "messages": [answer],
            "logistics_steps": int(state.get("logistics_steps", 0)) + 1,
        }

    return node


def _route_logistics(state: AgentState) -> str:
    last = state["messages"][-1] if state.get("messages") else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return "end"
    return "guard" if int(state.get("logistics_steps", 0)) >= MAX_LOGISTICS_STEPS else "tools"


def _logistics_guard_node(_state: AgentState) -> dict[str, Any]:
    return {"messages": [AIMessage(content="物流查询步骤过多，请补充订单号后重试。")]}


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
            result = _classify_intent(question, llm)
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
    tools: Sequence[BaseTool] = (),  # logistics 分支使用；其它分支直接调用确定性用例
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
    builder.add_node("logistics", _logistics_prepare)
    builder.add_node("logistics_agent", _logistics_agent_node(llm, tools))
    builder.add_node("logistics_guard", _logistics_guard_node)
    builder.add_node("fallback", _fallback_node)

    logistics_routes: dict[str, Any] = {"end": END, "guard": "logistics_guard"}
    if tools:
        builder.add_node("logistics_tools", ToolNode(list(tools)))
        builder.add_edge("logistics_tools", "logistics_agent")
        logistics_routes["tools"] = "logistics_tools"
    else:
        logistics_routes["tools"] = END

    builder.add_edge(START, "preprocess")
    builder.add_edge("preprocess", "classify")
    builder.add_conditional_edges(
        "classify",
        route_by_intent,
        {
            "knowledge": "knowledge",
            "query": "query",
            "service": "service",
            "logistics": "logistics",
            "fallback": "fallback",
        },
    )
    builder.add_edge("logistics", "logistics_agent")
    builder.add_conditional_edges("logistics_agent", _route_logistics, logistics_routes)
    builder.add_edge("logistics_guard", END)
    for branch in ("knowledge", "query", "service", "fallback"):
        builder.add_edge(branch, END)

    return builder.compile(checkpointer=checkpointer)
