"""应用装配层 + 统一流式出口。

两件事：
1. create_runtime()：调用各工厂，把 LLM、工具、检索器、记忆、工单存储拼成一个运行时。
2. AgentRuntime.stream()：唯一的流式出口。HTTP 的 SSE 和命令行验收脚本都走这里，
   保证「页面上看到的」和「命令行看到的」是同一套行为。

阶段二接上 checkpointer、tools 与工单存储，阶段四接上 retriever——都只改这个文件。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from backend.config import settings
from backend.factories.llm import create_llm
from backend.factories.memory import create_checkpointer
from backend.factories.store import create_ticket_store
from backend.graph import build_graph
from backend.schemas import (
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_START,
    EVENT_TICKET,
    EVENT_TOKEN,
    EVENT_TOOL,
)
from backend.tools import create_tools

logger = logging.getLogger("qa_ticket.runtime")


def _text_of(chunk: Any) -> str:
    """把模型增量里的文本抽出来（兼容 str 与内容块列表两种返回）。"""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _json_payload(content: Any) -> dict[str, Any] | None:
    """工具约定返回 JSON 字符串；解析不出来就当成普通文本。"""
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _tool_events(update: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """从「节点产出」里抽出工具结果事件与工单事件。"""
    if not isinstance(update, dict):
        return
    for node_output in update.values():
        if not isinstance(node_output, dict):
            continue
        for item in node_output.get("messages") or []:
            if not isinstance(item, ToolMessage):
                continue
            payload = _json_payload(item.content)
            ok = getattr(item, "status", "success") != "error" and (payload is None or payload.get("ok", True))
            yield EVENT_TOOL, {
                "phase": "result",
                "name": item.name or "",
                "ok": ok,
                "message": (payload or {}).get("message") or ("" if ok else str(item.content)[:200]),
            }
            data = payload or {}
            # 建单返回单数 ticket，查询返回 tickets 列表，这里统一成列表发给前端
            tickets = data.get("tickets") or ([data["ticket"]] if data.get("ticket") else None)
            if tickets:
                yield EVENT_TICKET, {"tickets": tickets}


@dataclass
class AgentRuntime:
    """一次进程启动内共享的 Agent 运行时。"""

    graph: Any
    llm: Any
    tools: list[Any] = field(default_factory=list)
    retriever: Any | None = None
    checkpointer: Any | None = None
    store: Any | None = None

    async def stream(self, message: str, thread_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """产出 (事件名, 载荷) 序列。

        事件名与 schemas.py 里的常量一一对应，调用方只负责编码成 SSE 或打印。

        同时订阅两种流：messages 拿模型增量（吐 token、播报正在调用哪个工具），
        updates 拿节点产出（工具返回结果、建单结果）。
        """
        config = {"configurable": {"thread_id": thread_id}}
        yield EVENT_START, {
            "thread_id": thread_id,
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
        }

        announced: set[str] = set()
        try:
            async for mode, payload in self.graph.astream(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    chunk, meta = payload
                    if not isinstance(chunk, AIMessageChunk) or meta.get("langgraph_node") != "agent":
                        continue
                    for call in chunk.tool_calls or []:
                        # 流式下参数是分片到达的，这里只播报「要调用谁」，参数以工具返回为准
                        key = call.get("id") or str(call.get("name"))
                        if key in announced:
                            continue
                        announced.add(key)
                        yield EVENT_TOOL, {"phase": "call", "name": call.get("name")}
                    text = _text_of(chunk)
                    if text:
                        yield EVENT_TOKEN, {"text": text}
                elif mode == "updates":
                    for event, data in _tool_events(payload):
                        yield event, data

            yield EVENT_DONE, {"thread_id": thread_id}
        except Exception as exc:  # 单轮失败不该拖垮服务，转成 error 事件交给前端
            logger.exception("对话失败")
            yield EVENT_ERROR, {"type": exc.__class__.__name__, "message": str(exc)}

    def describe(self) -> dict[str, Any]:
        return {
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
            "model": settings.llm_model or "",
            "tools": [getattr(tool, "name", str(tool)) for tool in self.tools],
            "tickets": self.store.count() if self.store else 0,
            "checkpointer": settings.checkpointer if self.checkpointer else None,
            "retriever": settings.retriever if self.retriever else None,
            "ticket_store": settings.ticket_store if self.store else None,
        }


def create_runtime() -> AgentRuntime:
    """按当前配置装配运行时。

    阶段二：LLM + 三个工单工具 + 短期记忆 checkpointer + JSON 工单存储。
    阶段四：再接上 create_retriever()，RAG 与引用生效。
    """
    llm = create_llm()
    checkpointer = create_checkpointer()
    store = create_ticket_store()
    tools = create_tools(store)
    retriever = None  # 阶段四：create_retriever()

    graph = build_graph(
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
    )
    logger.info(
        "Agent 运行时装配完成: %s",
        {
            "provider": settings.llm_provider,
            "tools": [getattr(tool, "name", str(tool)) for tool in tools],
            "checkpointer": settings.checkpointer,
            "ticket_store": settings.ticket_store,
            "tickets": store.count(),
        },
    )
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
    )
