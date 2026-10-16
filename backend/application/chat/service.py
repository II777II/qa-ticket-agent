"""对话用例：驱动图执行，并把图内动作翻译成对外的领域事件。

一次问答的完整用例都在这里：调用图、把模型增量 / 工具调用 / 建单 / 引用
翻译成 token、tool、ticket、citation 事件。HTTP 的 SSE 与命令行验收脚本消费同一套事件，
所以「页面上看到的」和「命令行看到的」行为一致。

事件常量定义在 backend/schemas.py（接口层契约），这一层只负责产生事件，
不负责编码成 SSE——那属于接口层。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from backend.infrastructure.config import settings
from backend.schemas import (
    EVENT_CITATION,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_START,
    EVENT_TICKET,
    EVENT_TOKEN,
    EVENT_TOOL,
)

if TYPE_CHECKING:  # 只用于类型标注，运行时不导入，避免与 runtime 形成循环
    from backend.application.runtime import AgentRuntime

logger = logging.getLogger("qa_ticket.chat")


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


def _citation_events(update: Any, announced: set[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """把 agent 节点写回的检索结果转成 citation 事件。

    一轮里 agent 可能被调用两次（先决定调工具、再总结），检索结果会重复出现，
    所以用「来源 + 小节标题」去重，避免前端把同一段引用显示两遍。
    """
    if not isinstance(update, dict):
        return
    for node_output in update.values():
        if not isinstance(node_output, dict):
            continue
        for citation in node_output.get("retrieved") or []:
            if not isinstance(citation, dict):
                continue
            key = f"{citation.get('source')}::{citation.get('title')}"
            if key in announced:
                continue
            announced.add(key)
            yield EVENT_CITATION, citation


class ChatService:
    """一轮对话的用例入口。"""

    def __init__(self, runtime: "AgentRuntime") -> None:
        self._runtime = runtime

    async def stream(self, message: str, thread_id: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """产出 (事件名, 载荷) 序列，供接口层编码成 SSE 或命令行直接打印。

        同时订阅两种流：messages 拿模型增量（吐 token、播报正在调用哪个工具），
        updates 拿节点产出（工具返回结果、建单结果、检索引用）。
        """
        config = {"configurable": {"thread_id": thread_id}}
        yield EVENT_START, {
            "thread_id": thread_id,
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
        }

        announced: set[str] = set()
        citations_announced: set[str] = set()
        try:
            async for mode, payload in self._runtime.graph.astream(
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
                    for event, data in _citation_events(payload, citations_announced):
                        yield event, data

            yield EVENT_DONE, {"thread_id": thread_id}
        except Exception as exc:  # 单轮失败不该拖垮服务，转成 error 事件交给前端
            logger.exception("对话失败")
            yield EVENT_ERROR, {"type": exc.__class__.__name__, "message": str(exc)}
