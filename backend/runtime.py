"""应用装配层 + 统一流式出口。

两件事：
1. create_runtime()：调用各工厂，把 LLM、工具、检索器、记忆、工单存储拼成一个运行时。
2. AgentRuntime.stream()：唯一的流式出口。HTTP 的 SSE 和命令行验收脚本都走这里，
   保证「页面上看到的」和「命令行看到的」是同一套行为。

阶段二接上 checkpointer 与 tools、阶段四接上 retriever 时，只改这个文件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessageChunk, HumanMessage

from backend.config import settings
from backend.factories.llm import create_llm
from backend.graph import build_graph
from backend.schemas import (
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_START,
    EVENT_TOKEN,
)
from backend.tools import get_tools

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
        """
        config = {"configurable": {"thread_id": thread_id}}
        yield EVENT_START, {
            "thread_id": thread_id,
            "provider": settings.llm_provider,
            "mock": settings.mock_mode,
        }

        try:
            async for chunk, meta in self.graph.astream(
                {"messages": [HumanMessage(content=message)]},
                config=config,
                stream_mode="messages",
            ):
                if not isinstance(chunk, AIMessageChunk):
                    continue
                if meta.get("langgraph_node") != "agent":
                    # 工具节点等内部消息不直接吐给用户，阶段二单独发 tool 事件
                    continue

                # 阶段二：这里再判断 chunk.tool_call_chunks，发出 tool 事件
                text = _text_of(chunk)
                if text:
                    yield EVENT_TOKEN, {"text": text}

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
            "checkpointer": settings.checkpointer if self.checkpointer else None,
            "retriever": settings.retriever if self.retriever else None,
            "ticket_store": settings.ticket_store if self.store else None,
        }


def create_runtime() -> AgentRuntime:
    """按当前配置装配运行时。

    阶段一：LLM + 空工具表（图退化成 Agent -> END）。
    阶段二：接上 create_checkpointer() 与工具，多轮记忆与建单生效。
    阶段四：接上 create_retriever()，RAG 与引用生效。
    """
    llm = create_llm()
    tools = get_tools()

    checkpointer = None  # 阶段二：create_checkpointer()
    retriever = None     # 阶段四：create_retriever()
    store = None         # 阶段二：create_ticket_store()

    graph = build_graph(
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
    )
    logger.info("Agent 运行时装配完成: %s", {"provider": settings.llm_provider, "tools": len(tools)})
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
    )
