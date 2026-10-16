"""演示模式（mock）模型。

存在的意义：没有 API Key、或者现场没有外网时，整条链路（前端 -> SSE -> LangGraph
-> 模型）依然能跑通并演示。它刻意做得很"笨"：只在回答里明确标注这是占位内容，
免得演示时把假数据当成真实模型输出。

阶段二接入工具后，这里再加「识别到建单意图就返回 tool_calls」的模拟分支。
"""

from __future__ import annotations

import time
from typing import Any, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

TEMPLATE = """【演示模式】当前没有可用的模型 API Key，这是一段占位回答，用来验证链路是否通畅。

你刚才问的是：{question}

链路检查：前端 -> FastAPI /chat (SSE) -> LangGraph agent 节点 -> 模型。
把 .env 里的 LLM_PROVIDER 改成 deepseek 或 openai 并填好 Key，这里就会替换成真实模型的流式输出。"""


def _chunks(text: str, size: int = 6) -> Iterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]


class FakeChatModel(BaseChatModel):
    """零依赖假模型：只做流式文本输出，不做推理。"""

    delay: float = Field(default=0.01, description="每个 chunk 之间的间隔，让流式效果可见")
    bound_tools: list[Any] = Field(default_factory=list, description="bind_tools 传进来的工具，阶段二用它做模拟调用")

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        """让 mock 也能被 bind_tools 装饰，这样图结构和真实模型完全一致。"""
        return self.model_copy(update={"bound_tools": list(tools or [])})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self._compose(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        for piece in _chunks(self._compose(messages)):
            if self.delay:
                time.sleep(self.delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))

    def _compose(self, messages: list[BaseMessage]) -> str:
        question = ""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                question = _as_text(message.content)
                break
        if not question:
            last = messages[-1] if messages else None
            if isinstance(last, SystemMessage):
                return "【演示模式】收到系统提示，但还没有用户问题。"
        return TEMPLATE.format(question=question or "(空)")


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)
