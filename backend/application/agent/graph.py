"""LangGraph 五路编排：确定性分支 + 物流 Agent/Tools 试点。"""

from __future__ import annotations

from typing import Any, Callable, NotRequired, Sequence

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
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
    IntentName,
    IntentResult,
    ORDER_NO_RE,
    extract_order_keyword,
    extract_service_slots,
    guess_category,
    rule_classify,
)
from backend.infrastructure.config import settings
from backend.infrastructure.retrieval.in_memory import format_context

INTENTS = {"knowledge", "query", "service", "logistics", "fallback"}
MAX_LOGISTICS_STEPS = 4
TRANSFER_HINTS = ("转人工", "人工客服", "找人工", "客服电话", "投诉", "差评")

CLASSIFIER_PROMPT = """把用户消息分类为 knowledge、query、service、logistics、fallback 之一。
只输出 IntentResult JSON，不要 Markdown。"""
SYSTEM_PROMPT = """你是电商智能客服。基于【参考资料】回答并标引用编号；不要编造订单或规则。
信息不足先追问。售后不会直接建单，只有用户在右侧确认后才提交。"""
LOGISTICS_SYSTEM_PROMPT = """你是物流查询助手。有订单号、姓名或手机号时调用 query_order；
根据工具结果简洁回答，不输出原始 JSON，最多调用 2 次工具。"""


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


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content
            if isinstance(item, (str, dict))
        )
    return str(content)


def _last_human(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _text(message.content)
    return ""


def _emit(writer: StreamWriter, event: str, data: dict[str, Any]) -> None:
    writer({"event": event, "data": data})


def _intent(question: str, llm: BaseChatModel) -> IntentResult:
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


def _preprocess(state: AgentState) -> dict[str, Any]:
    text = _last_human(state["messages"]).strip()
    return {"question": text[:2000] or "（空消息）"}


def _classify(llm: BaseChatModel) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        requested = state.get("requested_intent")
        result = (
            IntentResult(intent=requested, confidence=1.0, reason="由显式 HTTP 分支路由指定")
            if requested in INTENTS
            else _intent(state["question"], llm)
        )
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
                "intent": result.intent,
                "confidence": result.confidence,
                "reason": result.reason,
                "slots": result.slots,
            },
        )
        return output

    return node


def _knowledge(
    llm: BaseChatModel,
    retriever: Any | None,
    base_prompt: str,
) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        history = [item for item in state["messages"] if not isinstance(item, SystemMessage)]
        question = state["question"]
        prompt = base_prompt
        citations: list[dict[str, Any]] = []
        if retriever is not None:
            try:
                docs: list[Document] = list(retriever.invoke(question))
            except Exception:
                docs = []
            citations = [
                {
                    "index": index,
                    "source": doc.metadata.get("source", ""),
                    "title": doc.metadata.get("title", ""),
                    "snippet": doc.page_content.strip()[:160],
                    "score": doc.metadata.get("score"),
                }
                for index, doc in enumerate(docs, start=1)
            ]
            if docs:
                prompt = f"{prompt}\n\n{format_context(docs)}"
        for citation in citations:
            _emit(writer, EVENT_CITATION, citation)
        return {
            "messages": [llm.invoke([SystemMessage(content=prompt), *history])],
            "retrieved": citations,
        }

    return node


def _query(orders: OrderService | None) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        question = state["question"]
        order_no = ORDER_NO_RE.search(question)
        if orders is None:
            results = []
        elif order_no:
            record = orders.get(order_no.group(0))
            results = [record] if record else []
        else:
            results = orders.search(q=extract_order_keyword(question), limit=5)
        if not results:
            return {
                "messages": [AIMessage(content="没有找到订单，请提供 SO 开头的订单号、姓名或手机号。")],
                "orders": [],
            }
        summaries = [order_summary(order) for order in results]
        _emit(writer, EVENT_ORDER, {"orders": summaries})
        lines = [
            f"- {order['order_no']}｜{order['status']}｜¥{order['payable_amount']:.2f}｜"
            + " / ".join(item["name"] for item in order["items"])
            for order in summaries
        ]
        return {
            "messages": [AIMessage(content=f"查到 {len(summaries)} 笔订单：\n" + "\n".join(lines))],
            "orders": summaries,
        }

    return node


def _service(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
    question = state["question"]
    slots = {**state.get("slots", {}), **extract_service_slots(question)}
    order_no = slots.get("order_no", "")
    contact = slots.get("contact", "")
    service_type = slots.get("service_type", "")
    category = slots.get("category") or guess_category(question)
    missing = [
        key
        for key, value in (
            ("service_type", service_type),
            ("order_no", order_no),
            ("contact", contact),
            ("description", question if len(question) >= 10 else ""),
        )
        if not value
    ]
    draft = {
        "status": "ready" if not missing else "draft",
        "title": f"{service_type or '售后'}办理 · {order_no or '待补充订单号'}"[:60],
        "description": question,
        "category": category,
        "priority": "中",
        "order_no": order_no,
        "contact": contact,
        "service_type": service_type,
        "slots": {key: value for key, value in slots.items() if value},
        "missing": missing,
        "ready": not missing,
        "requires_confirmation": True,
    }
    _emit(writer, EVENT_SERVICE_DRAFT, draft)
    labels = {"service_type": "业务类型", "order_no": "订单号", "contact": "联系人", "description": "问题描述"}
    suffix = (
        f"还缺少：{'、'.join(labels[key] for key in missing)}，请补齐后确认。"
        if missing
        else "槽位已齐全，请核对并确认提交。"
    )
    text = f"已整理业务办理草稿：\n- 类型：{service_type or '待补充'}\n- 订单：{order_no or '待补充'}\n{suffix}"
    return {"messages": [AIMessage(content=text)], "draft": draft}


def _fallback(state: AgentState) -> dict[str, Any]:
    question = state["question"]
    text = (
        "已收到转人工/投诉请求。当前演示版未接入人工坐席，请先查看帮助中心规则。"
        if any(hint in question for hint in TRANSFER_HINTS)
        else "你好，我可以查询订单、解释帮助中心规则，或整理售后业务草稿。"
    )
    return {"messages": [AIMessage(content=text)]}


def _logistics_prepare(state: AgentState) -> dict[str, Any]:
    slots = dict(state.get("slots") or {})
    match = ORDER_NO_RE.search(state["question"])
    if match:
        slots["order_no"] = match.group(0).upper()
    return {"slots": slots, "logistics_steps": 0}


def _logistics_agent(
    llm: BaseChatModel,
    tools: Sequence[BaseTool],
) -> Callable[[AgentState], dict[str, Any]]:
    model = llm.bind_tools(list(tools)) if tools else llm

    def node(state: AgentState) -> dict[str, Any]:
        history = [item for item in state["messages"] if not isinstance(item, SystemMessage)]
        return {
            "messages": [model.invoke([SystemMessage(content=LOGISTICS_SYSTEM_PROMPT), *history])],
            "logistics_steps": int(state.get("logistics_steps", 0)) + 1,
        }

    return node


def _route_logistics(state: AgentState) -> str:
    last = state["messages"][-1] if state.get("messages") else None
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return "end"
    return "guard" if int(state.get("logistics_steps", 0)) >= MAX_LOGISTICS_STEPS else "tools"


def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "fallback")
    return intent if intent in INTENTS else "fallback"


def build_graph(
    *,
    llm: BaseChatModel,
    tools: Sequence[BaseTool] = (),
    retriever: Any | None = None,
    checkpointer: Any | None = None,
    order_service: OrderService | None = None,
    system_prompt: str = SYSTEM_PROMPT,
):
    graph = StateGraph(AgentState)
    for name, node in {
        "preprocess": _preprocess,
        "classify": _classify(llm),
        "knowledge": _knowledge(llm, retriever, system_prompt),
        "query": _query(order_service),
        "service": _service,
        "logistics": _logistics_prepare,
        "logistics_agent": _logistics_agent(llm, tools),
        "logistics_guard": lambda _state: {
            "messages": [AIMessage(content="物流查询步骤过多，请补充订单号后重试。")]
        },
        "fallback": _fallback,
    }.items():
        graph.add_node(name, node)
    routes: dict[str, Any] = {"end": END, "guard": "logistics_guard"}
    if tools:
        graph.add_node("logistics_tools", ToolNode(list(tools)))
        graph.add_edge("logistics_tools", "logistics_agent")
        routes["tools"] = "logistics_tools"
    else:
        routes["tools"] = END

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "classify")
    graph.add_conditional_edges(
        "classify",
        route_by_intent,
        {name: name for name in INTENTS},
    )
    graph.add_edge("logistics", "logistics_agent")
    graph.add_conditional_edges("logistics_agent", _route_logistics, routes)
    graph.add_edge("logistics_guard", END)
    for name in ("knowledge", "query", "service", "fallback"):
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)
