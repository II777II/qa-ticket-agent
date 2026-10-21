"""LangGraph state, intent classification, route nodes and deterministic tools."""

from __future__ import annotations

from typing import Any, Callable, NotRequired, Sequence

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import StreamWriter

from backend.domain.core import (
    HUMAN_HINTS,
    ORDER_NO_RE,
    IntentName,
    IntentResult,
    extract_service_slots,
    extract_user_id,
    guess_category,
    is_order_query,
    rule_classify,
)
from backend.infrastructure.llm import message_text
from backend.infrastructure.retrieval import format_context

EVENT_START, EVENT_INTENT, EVENT_TOKEN = "start", "intent", "token"
EVENT_ORDER, EVENT_SERVICE_DRAFT, EVENT_CITATION = "order", "service_draft", "citation"
EVENT_DONE, EVENT_ERROR = "done", "error"
INTENTS = ("read", "write", "human")
CLASSIFIER_PROMPT = "把用户消息分类为 read（只读查询）、write（业务办理）、human（投诉/转人工/闲聊）之一。只输出 IntentResult JSON，不要 Markdown。"
SYSTEM_PROMPT = "你是电商智能客服。基于【参考资料】回答并标引用编号；不要编造订单或规则。信息不足先追问。售后不会直接建单，只有用户在右侧确认后才提交。"


class AgentState(MessagesState):
    question: NotRequired[str]
    requested_intent: NotRequired[IntentName | None]
    intent: NotRequired[str]
    slots: NotRequired[dict[str, str]]
    retrieved: NotRequired[list[dict[str, Any]]]
    orders: NotRequired[list[dict[str, Any]]]
    draft: NotRequired[dict[str, Any]]


def _last_human(messages: Sequence[BaseMessage]) -> str:
    return next((message_text(x.content) for x in reversed(messages) if isinstance(x, HumanMessage)), "")


def _emit(writer: StreamWriter, event: str, data: dict[str, Any]) -> None:
    writer({"event": event, "data": data})


def _intent(question: str, llm: BaseChatModel) -> IntentResult:
    if getattr(llm, "_llm_type", "") == "fake-chat-model":
        return rule_classify(question)
    try:
        result = llm.with_structured_output(IntentResult).invoke(
            [SystemMessage(content=CLASSIFIER_PROMPT), HumanMessage(content=question)]
        )
        return result if isinstance(result, IntentResult) else IntentResult(**result)
    except Exception:
        return rule_classify(question)


def _preprocess(state: AgentState) -> dict[str, Any]:
    return {"question": _last_human(state["messages"]).strip()[:2000] or "（空消息）"}


def _classify(llm: BaseChatModel) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        requested = state.get("requested_intent")
        if requested in INTENTS:
            result = IntentResult(intent=requested, confidence=1.0, reason="由显式 HTTP 分支路由指定")
        elif is_order_query(state["question"]):
            result = rule_classify(state["question"])
        else:
            result = _intent(state["question"], llm)
        _emit(writer, EVENT_INTENT, {
            "intent": result.intent,
            "confidence": result.confidence,
            "reason": result.reason,
            "slots": result.slots,
        })
        return {"intent": result.intent, "slots": result.slots}

    return node


def _knowledge_tool(
    llm: BaseChatModel,
    retriever: Any | None,
    prompt: str,
) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        docs: list[Document] = []
        if retriever is not None:
            try:
                docs = list(retriever.invoke(state["question"]))
            except Exception:
                pass
        citations = [{
            "index": index,
            "source": doc.metadata.get("source", ""),
            "title": doc.metadata.get("title", ""),
            "snippet": doc.page_content.strip()[:160],
            "score": doc.metadata.get("score"),
        } for index, doc in enumerate(docs, 1)]
        for citation in citations:
            _emit(writer, EVENT_CITATION, citation)
        system = f"{prompt}\n\n{format_context(docs)}" if docs else prompt
        history = [item for item in state["messages"] if not isinstance(item, SystemMessage)]
        return {
            "messages": [llm.invoke([SystemMessage(content=system), *history])],
            "retrieved": citations,
        }

    return node


def _order_tool(orders: Any | None) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        question = state["question"]
        if orders is None:
            results = []
        elif match := ORDER_NO_RE.search(question):
            record = orders.get(match.group(0))
            results = [record] if record else []
        elif user_id := extract_user_id(question):
            results = orders.search(user_id=user_id, limit=20)
        else:
            results = []
        if not results:
            return {
                "messages": [AIMessage(content="没有找到订单，请提供 SO 开头的订单号或 user_id。")],
                "orders": [],
            }
        summaries = [order.summary() for order in results]
        _emit(writer, EVENT_ORDER, {"orders": summaries})
        lines = [
            f"- {item['order_no']}｜{item['status']}｜¥{item['payable_amount']:.2f}｜"
            + " / ".join(product["name"] for product in item["items"])
            for item in summaries
        ]
        return {
            "messages": [AIMessage(content=f"查到 {len(summaries)} 笔订单：\n" + "\n".join(lines))],
            "orders": summaries,
        }

    return node


def _read(llm: BaseChatModel, retriever: Any | None, orders: Any | None, prompt: str):
    knowledge = _knowledge_tool(llm, retriever, prompt)
    order = _order_tool(orders)

    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        return order(state, writer) if is_order_query(state["question"]) else knowledge(state, writer)

    return node


def _write(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
    question = state["question"]
    slots = {**state.get("slots", {}), **extract_service_slots(question)}
    order_no, contact = slots.get("order_no", ""), slots.get("contact", "")
    service_type = slots.get("service_type", "")
    missing = [
        key for key, value in (
            ("service_type", service_type),
            ("order_no", order_no),
            ("contact", contact),
            ("description", question if len(question) >= 10 else ""),
        ) if not value
    ]
    draft = {
        "status": "ready" if not missing else "draft",
        "title": f"{service_type or '售后'}办理 · {order_no or '待补充订单号'}"[:60],
        "description": question,
        "category": slots.get("category") or guess_category(question),
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
        if missing else "槽位已齐全，请核对并确认提交。"
    )
    text = f"已整理业务办理草稿：\n- 类型：{service_type or '待补充'}\n- 订单：{order_no or '待补充'}\n{suffix}"
    return {"messages": [AIMessage(content=text)], "draft": draft}


def _human(state: AgentState) -> dict[str, Any]:
    text = (
        "已收到转人工/投诉请求。当前演示版未接入人工坐席，请先查看帮助中心规则。"
        if any(item in state["question"] for item in HUMAN_HINTS)
        else "你好，我可以查询订单、解释帮助中心规则，或整理售后业务草稿。"
    )
    return {"messages": [AIMessage(content=text)]}


def route_by_intent(state: AgentState) -> str:
    return state.get("intent", "human") if state.get("intent") in INTENTS else "human"


def build_graph(
    *,
    llm: BaseChatModel,
    retriever: Any | None = None,
    checkpointer: Any | None = None,
    order_service: Any | None = None,
    system_prompt: str = SYSTEM_PROMPT,
):
    graph = StateGraph(AgentState)
    nodes = {
        "preprocess": _preprocess,
        "classify": _classify(llm),
        "read": _read(llm, retriever, order_service, system_prompt),
        "write": _write,
        "human": _human,
    }
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "classify")
    graph.add_conditional_edges("classify", route_by_intent, {name: name for name in INTENTS})
    for name in INTENTS:
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)
