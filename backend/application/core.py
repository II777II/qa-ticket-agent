"""LangGraph orchestration, chat use case and runtime assembly."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, NotRequired, Sequence

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import StreamWriter

from backend.domain.core import (
    HUMAN_HINTS, ORDER_NO_RE, IntentName, IntentResult, extract_order_keyword,
    extract_service_slots, guess_category, is_order_query, rule_classify,
)
from backend.infrastructure.core import (
    LangfuseTracing, MetricsCollector, create_checkpointer, create_knowledge_catalog,
    create_langfuse_tracing, create_llm, create_order_store, create_retriever,
    create_ticket_store, estimate_tokens, format_context, message_text, settings,
)

EVENT_START, EVENT_INTENT, EVENT_TOKEN = "start", "intent", "token"
EVENT_ORDER, EVENT_SERVICE_DRAFT, EVENT_CITATION = "order", "service_draft", "citation"
EVENT_DONE, EVENT_ERROR = "done", "error"
INTENTS = ("read", "write", "human")
CLASSIFIER_PROMPT = "把用户消息分类为 read（只读查询）、write（业务办理）、human（投诉/转人工/闲聊）之一。只输出 IntentResult JSON，不要 Markdown。"
SYSTEM_PROMPT = "你是电商智能客服。基于【参考资料】回答并标引用编号；不要编造订单或规则。信息不足先追问。售后不会直接建单，只有用户在右侧确认后才提交。"
logger = logging.getLogger("qa_ticket")


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
    if settings.mock_mode:
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
        result = (
            IntentResult(intent=requested, confidence=1.0, reason="由显式 HTTP 分支路由指定")
            if requested in INTENTS else _intent(state["question"], llm)
        )
        _emit(writer, EVENT_INTENT, {
            "intent": result.intent, "confidence": result.confidence,
            "reason": result.reason, "slots": result.slots,
        })
        return {"intent": result.intent, "slots": result.slots}
    return node


def _knowledge_tool(llm: BaseChatModel, retriever: Any | None, prompt: str) -> Callable[[AgentState, StreamWriter], dict[str, Any]]:
    def node(state: AgentState, writer: StreamWriter) -> dict[str, Any]:
        docs: list[Document] = []
        if retriever is not None:
            try:
                docs = list(retriever.invoke(state["question"]))
            except Exception:
                pass
        citations = [{
            "index": i, "source": d.metadata.get("source", ""), "title": d.metadata.get("title", ""),
            "snippet": d.page_content.strip()[:160], "score": d.metadata.get("score"),
        } for i, d in enumerate(docs, 1)]
        for citation in citations:
            _emit(writer, EVENT_CITATION, citation)
        system = f"{prompt}\n\n{format_context(docs)}" if docs else prompt
        history = [x for x in state["messages"] if not isinstance(x, SystemMessage)]
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
        else:
            results = orders.search(q=extract_order_keyword(question), limit=5)
        if not results:
            return {"messages": [AIMessage(content="没有找到订单，请提供 SO 开头的订单号、姓名或手机号。")], "orders": []}
        summaries = [x.summary() for x in results]
        _emit(writer, EVENT_ORDER, {"orders": summaries})
        lines = [
            f"- {x['order_no']}｜{x['status']}｜¥{x['payable_amount']:.2f}｜" +
            " / ".join(item["name"] for item in x["items"]) for x in summaries
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
            ("service_type", service_type), ("order_no", order_no), ("contact", contact),
            ("description", question if len(question) >= 10 else ""),
        ) if not value
    ]
    draft = {
        "status": "ready" if not missing else "draft",
        "title": f"{service_type or '售后'}办理 · {order_no or '待补充订单号'}"[:60],
        "description": question, "category": slots.get("category") or guess_category(question),
        "priority": "中", "order_no": order_no, "contact": contact, "service_type": service_type,
        "slots": {k: v for k, v in slots.items() if v}, "missing": missing,
        "ready": not missing, "requires_confirmation": True,
    }
    _emit(writer, EVENT_SERVICE_DRAFT, draft)
    labels = {"service_type": "业务类型", "order_no": "订单号", "contact": "联系人", "description": "问题描述"}
    suffix = f"还缺少：{'、'.join(labels[x] for x in missing)}，请补齐后确认。" if missing else "槽位已齐全，请核对并确认提交。"
    text = f"已整理业务办理草稿：\n- 类型：{service_type or '待补充'}\n- 订单：{order_no or '待补充'}\n{suffix}"
    return {"messages": [AIMessage(content=text)], "draft": draft}


def _human(state: AgentState) -> dict[str, Any]:
    text = "已收到转人工/投诉请求。当前演示版未接入人工坐席，请先查看帮助中心规则。" if any(x in state["question"] for x in HUMAN_HINTS) else "你好，我可以查询订单、解释帮助中心规则，或整理售后业务草稿。"
    return {"messages": [AIMessage(content=text)]}


def route_by_intent(state: AgentState) -> str:
    return state.get("intent", "human") if state.get("intent") in INTENTS else "human"


def build_graph(*, llm: BaseChatModel, retriever: Any | None = None, checkpointer: Any | None = None,
                order_service: Any | None = None, system_prompt: str = SYSTEM_PROMPT):
    graph = StateGraph(AgentState)
    nodes = {
        "preprocess": _preprocess, "classify": _classify(llm),
        "read": _read(llm, retriever, order_service, system_prompt),
        "write": _write, "human": _human,
    }
    for name, node in nodes.items():
        graph.add_node(name, node)
    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "classify")
    graph.add_conditional_edges("classify", route_by_intent, {x: x for x in INTENTS})
    for name in INTENTS:
        graph.add_edge(name, END)
    return graph.compile(checkpointer=checkpointer)


class ChatService:
    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def stream(self, message: str, thread_id: str, *, requested_intent: IntentName | None = None) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id},
            "metadata": {"langfuse_session_id": thread_id, "langfuse_tags": ["qa-ticket", f"branch:{requested_intent or 'auto'}"]},
        }
        if self._runtime.tracing and self._runtime.tracing.handler:
            config["callbacks"] = [self._runtime.tracing.handler]
        yield EVENT_START, {"thread_id": thread_id, "provider": settings.llm_provider, "mock": settings.mock_mode}
        started, first_at, answer, final_text, tokens = time.perf_counter(), None, [], "", 0
        ok, intent = True, requested_intent or "unknown"
        try:
            async for mode, payload in self._runtime.graph.astream(
                {"messages": [HumanMessage(content=message)], "requested_intent": requested_intent},
                config=config, stream_mode=["messages", "custom", "updates"],
            ):
                if mode == "messages":
                    chunk, _ = payload
                    if isinstance(chunk, AIMessageChunk):
                        usage = getattr(chunk, "usage_metadata", None)
                        if isinstance(usage, dict):
                            tokens = max(tokens, int(usage.get("total_tokens") or 0))
                        if text := message_text(chunk):
                            first_at = first_at or time.perf_counter()
                            answer.append(text)
                            yield EVENT_TOKEN, {"text": text}
                elif mode == "custom" and isinstance(payload, dict):
                    event, data = payload.get("event"), payload.get("data")
                    if isinstance(event, str) and isinstance(data, dict):
                        if event == EVENT_INTENT and isinstance(data.get("intent"), str):
                            intent = data["intent"]
                        yield event, data
                elif mode == "updates" and isinstance(payload, dict):
                    for output in payload.values():
                        for item in output.get("messages") or [] if isinstance(output, dict) else []:
                            if isinstance(item, AIMessage) and not isinstance(item, AIMessageChunk):
                                final_text = message_text(item) or final_text
            if not answer and final_text:
                first_at, answer = time.perf_counter(), [final_text]
                yield EVENT_TOKEN, {"text": final_text}
            yield EVENT_DONE, {"thread_id": thread_id}
        except Exception as exc:
            ok = False
            logger.exception("对话失败")
            yield EVENT_ERROR, {"type": exc.__class__.__name__, "message": str(exc)}
        finally:
            total_ms = int((time.perf_counter() - started) * 1000)
            first_ms = int((first_at - started) * 1000) if first_at else None
            self._runtime.metrics.record_turn(
                tokens=tokens or estimate_tokens(message + "".join(answer)),
                first_token_ms=first_ms, total_ms=total_ms, ok=ok, intent=intent,
            )


@dataclass
class AgentRuntime:
    graph: Any
    llm: Any
    tickets: Any
    metrics: MetricsCollector
    orders: Any
    knowledge: Any
    retriever: Any | None = None
    checkpointer: Any | None = None
    store: Any | None = None
    tracing: LangfuseTracing | None = None

    def describe(self) -> dict[str, Any]:
        return {
            "provider": settings.llm_provider, "mock": settings.mock_mode, "model": settings.llm_model,
            "tickets": self.tickets.count(), "orders": self.orders.count(), "kb_articles": self.knowledge.count(),
            "kb_documents": getattr(self.retriever, "document_count", lambda: 0)(),
            "kb_chunks": getattr(self.retriever, "chunk_count", lambda: 0)(),
            "checkpointer": settings.checkpointer if self.checkpointer else None,
            "retriever": settings.retriever if self.retriever else None,
            "ticket_store": settings.ticket_store if self.store else None,
            "langfuse": self.tracing.status if self.tracing else "disabled",
        }

    def shutdown(self) -> None:
        self.tracing and self.tracing.shutdown()


def create_runtime() -> AgentRuntime:
    llm, checkpointer = create_llm(), create_checkpointer()
    store, orders, knowledge, retriever = create_ticket_store(), create_order_store(), create_knowledge_catalog(), create_retriever()
    tracing = create_langfuse_tracing()
    graph = build_graph(llm=llm, retriever=retriever, checkpointer=checkpointer, order_service=orders)
    return AgentRuntime(
        graph=graph, llm=llm, tickets=store, metrics=MetricsCollector(), orders=orders,
        knowledge=knowledge, retriever=retriever, checkpointer=checkpointer, store=store, tracing=tracing,
    )
