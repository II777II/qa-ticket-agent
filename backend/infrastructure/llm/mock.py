"""离线演示模型：生成占位文本和基于检索资料的演示回答。"""

from __future__ import annotations

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
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

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


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(content=self._compose(messages))
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        answer = self._compose(messages)
        for index in range(0, len(answer), 8):
            yield ChatGenerationChunk(message=AIMessageChunk(content=answer[index : index + 8]))

    def _compose(self, messages: list[BaseMessage]) -> str:
        question = _last_human(messages)
        documents = _documents(messages)
        if documents:
            parts = [f"{head}\n{body[:160]}" for head, body in documents]
            return f"【演示模式】检索到 {len(documents)} 段资料：\n\n" + "\n\n".join(parts)
        return f"【演示模式】问题：{question or '（空）'}"
