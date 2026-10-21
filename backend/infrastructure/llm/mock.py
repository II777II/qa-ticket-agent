"""离线演示模型：模拟文本回答与 query_order 工具调用。"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from backend.domain.intent import ORDER_NO_RE, extract_order_keyword, rule_classify
from backend.infrastructure.retrieval.in_memory import CONTEXT_FOOTER, CONTEXT_HEADER


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
    return next(
        (_text(item.content) for item in reversed(messages) if isinstance(item, HumanMessage)),
        "",
    )


def _documents(messages: Sequence[BaseMessage]) -> list[tuple[str, str]]:
    prompt = next(
        (
            _text(item.content)
            for item in messages
            if isinstance(item, SystemMessage) and CONTEXT_HEADER in _text(item.content)
        ),
        "",
    )
    block = prompt.split(CONTEXT_HEADER, 1)[-1].split(CONTEXT_FOOTER, 1)[0]
    matches = list(re.finditer(r"(?m)^\[(\d+)\]\s*(.+)$", block))
    return [
        (
            f"[{match.group(1)}] {match.group(2)}",
            block[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(block)].strip(),
        )
        for index, match in enumerate(matches)
    ]


def _tool_call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": f"call_mock_{name}", "type": "tool_call"}],
    )


class FakeChatModel(BaseChatModel):
    bound_tools: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self.model_copy(update={"bound_tools": list(tools or [])})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self._plan(messages) or AIMessage(content=self._compose(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        planned = self._plan(messages)
        if planned:
            call = planned.tool_calls[0]
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": call["name"],
                            "args": json.dumps(call["args"], ensure_ascii=False),
                            "id": call["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                    ],
                )
            )
            return
        answer = self._compose(messages)
        for index in range(0, len(answer), 8):
            yield ChatGenerationChunk(message=AIMessageChunk(content=answer[index : index + 8]))

    def _plan(self, messages: list[BaseMessage]) -> AIMessage | None:
        names = {getattr(tool, "name", "") for tool in self.bound_tools}
        question = _last_human(messages)
        if (
            "query_order" not in names
            or not question
            or (messages and isinstance(messages[-1], ToolMessage))
            or rule_classify(question).intent not in {"query", "logistics"}
        ):
            return None
        order_no = ORDER_NO_RE.search(question)
        args = (
            {"order_no": order_no.group(0).upper()}
            if order_no
            else {"keyword": extract_order_keyword(question)}
        )
        return _tool_call("query_order", args)

    def _compose(self, messages: list[BaseMessage]) -> str:
        if messages and isinstance(messages[-1], ToolMessage):
            return self._compose_tool(messages[-1])
        question = _last_human(messages)
        documents = _documents(messages)
        if documents:
            parts = [f"{head}\n{body[:160]}" for head, body in documents]
            return f"【演示模式】检索到 {len(documents)} 段资料：\n\n" + "\n\n".join(parts)
        return f"【演示模式】问题：{question or '（空）'}"

    @staticmethod
    def _compose_tool(message: ToolMessage) -> str:
        try:
            payload = json.loads(message.content)
        except (TypeError, json.JSONDecodeError):
            return f"【演示模式】工具返回：{message.content}"
        if not payload.get("ok", True):
            return f"【演示模式】{payload.get('message', '工具执行失败')}"
        orders = payload.get("orders") or []
        if not orders:
            return f"【演示模式】{payload.get('message', '没有查到结果')}"
        lines = [
            f"- {order['order_no']}｜{order['status']}｜¥{order['payable_amount']:.2f}｜"
            + " / ".join(item["name"] for item in order["items"])
            for order in orders
        ]
        return "【演示模式】查到这些订单：\n" + "\n".join(lines)
