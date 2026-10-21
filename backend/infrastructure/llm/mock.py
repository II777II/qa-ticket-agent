"""离线演示模型：模拟文本回答与 query_order 工具调用。"""

from __future__ import annotations

import json
import time
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

from backend.domain.intent import ORDER_NO_RE, detect_intent, extract_order_keyword
from backend.infrastructure.retrieval.in_memory import CONTEXT_FOOTER, CONTEXT_HEADER

TEMPLATE = """【演示模式】当前没有模型 API Key，这是一段链路占位回答。

问题：{question}

把 .env 的 LLM_PROVIDER 改成 deepseek 或 openai 并配置 Key 后，会换成真实模型输出。"""


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block
            if isinstance(block, str)
            else str(block.get("text", ""))
            for block in content
            if isinstance(block, (str, dict))
        )
    return str(content)


def _last_human(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _text(message.content)
    return ""


def _called_tool(messages: Sequence[BaseMessage]) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return False
        if isinstance(message, ToolMessage):
            return True
    return False


def _documents(messages: Sequence[BaseMessage]) -> list[tuple[str, str]]:
    for message in messages:
        if not isinstance(message, SystemMessage):
            continue
        prompt = _text(message.content)
        if CONTEXT_HEADER not in prompt:
            continue
        block = prompt.split(CONTEXT_HEADER, 1)[1].split(CONTEXT_FOOTER, 1)[0]
        documents: list[tuple[str, str]] = []
        head, lines = "", []
        for line in block.splitlines():
            if line.startswith("[") and "]" in line:
                if head:
                    documents.append((head, " ".join(lines).strip()))
                head, lines = line.strip(), []
            elif line.strip():
                lines.append(line.strip())
        if head:
            documents.append((head, " ".join(lines).strip()))
        return documents
    return []


def _tool_call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": args,
                "id": f"call_mock_{name}",
                "type": "tool_call",
            }
        ],
    )


class FakeChatModel(BaseChatModel):
    """零依赖假模型，只模拟演示主链路需要的两种行为。"""

    delay: float = Field(default=0.01)
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
        message = self._plan(messages)
        if message is None:
            message = AIMessage(content=self._compose(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        planned = self._plan(messages)
        if planned is not None:
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
            if self.delay:
                time.sleep(self.delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=answer[index : index + 8]))

    def _plan(self, messages: list[BaseMessage]) -> AIMessage | None:
        names = {getattr(tool, "name", "") for tool in self.bound_tools}
        question = _last_human(messages)
        if "query_order" not in names or not question or _called_tool(messages):
            return None
        if detect_intent(question) not in {"order_lookup", "logistics"}:
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
            parts = []
            for head, body in documents:
                label = head.split("]", 1)[0].lstrip("[")
                title = head.split("]", 1)[-1].strip()
                parts.append(f"[{label}] {title}\n{body[:160]}")
            return (
                f"【演示模式】检索到 {len(documents)} 段资料：\n\n"
                + "\n\n".join(parts)
                + "\n\n以上内容来自知识库文档。"
            )
        return TEMPLATE.format(question=question or "（空）")

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
            f"- {order['order_no']} ｜ {order['status']} ｜ ¥{order['payable_amount']:.2f} ｜ "
            + " / ".join(item["name"] for item in order["items"])
            for order in orders
        ]
        return "【演示模式】查到这些订单：\n" + "\n".join(lines)
