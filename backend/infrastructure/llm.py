"""Chat model factories, mock model and memory checkpointer factory."""

from __future__ import annotations

import re
from typing import Any, Iterator

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from backend.infrastructure.config import LLM_MODELS, settings
from backend.infrastructure.retrieval import CONTEXT_FOOTER, CONTEXT_HEADER


def message_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item if isinstance(item, str) else str(item.get("text", ""))
            for item in content if isinstance(item, (str, dict))
        )
    return str(content)


class FakeChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def _compose(self, messages: list[BaseMessage]) -> str:
        question = next((message_text(x.content) for x in reversed(messages) if isinstance(x, HumanMessage)), "")
        prompt = next(
            (message_text(x.content) for x in messages
             if isinstance(x, SystemMessage) and CONTEXT_HEADER in message_text(x.content)),
            "",
        )
        block = prompt.split(CONTEXT_HEADER, 1)[-1].split(CONTEXT_FOOTER, 1)[0]
        matches = list(re.finditer(r"(?m)^\[(\d+)\]\s*(.+)$", block))
        docs = [
            (
                f"[{match.group(1)}] {match.group(2)}",
                block[match.end():(matches[index + 1].start() if index + 1 < len(matches) else len(block))].strip(),
            )
            for index, match in enumerate(matches)
        ]
        return (
            f"【演示模式】检索到 {len(docs)} 段资料：\n\n" + "\n\n".join(f"{head}\n{body[:160]}" for head, body in docs)
            if docs else f"【演示模式】问题：{question or '（空）'}"
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._compose(messages)))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        answer = self._compose(messages)
        for index in range(0, len(answer), 8):
            yield ChatGenerationChunk(message=AIMessageChunk(content=answer[index:index + 8]))


def create_llm(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str = "",
    base_url: str = "",
) -> BaseChatModel:
    provider = (provider or settings.llm_provider).lower()
    if provider == "mock":
        return FakeChatModel()
    if provider not in LLM_MODELS:
        raise ValueError(f"未知的 LLM_PROVIDER: {provider!r}")
    key = api_key or settings.llm_api_key
    if not key:
        raise RuntimeError(f"LLM_PROVIDER={provider} 需要配置 LLM_API_KEY")
    from langchain_openai import ChatOpenAI

    kwargs = {
        "model": model or settings.llm_model or LLM_MODELS[provider],
        "api_key": key,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout,
        "streaming": True,
    }
    if url := base_url or settings.llm_base_url or ("https://api.deepseek.com/v1" if provider == "deepseek" else ""):
        kwargs["base_url"] = url
    return ChatOpenAI(**kwargs)


def create_checkpointer():
    if settings.checkpointer == "memory":
        from langgraph.checkpoint.memory import InMemorySaver
        return InMemorySaver()
    if settings.checkpointer == "postgres":
        raise NotImplementedError("CHECKPOINTER=postgres 尚未接入")
    raise ValueError(f"未知的 CHECKPOINTER: {settings.checkpointer!r}")
