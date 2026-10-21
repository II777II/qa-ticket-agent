"""模型工厂：按 LLM_PROVIDER 创建 BaseChatModel。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from backend.infrastructure.config import settings

PROVIDER_MODELS = {"deepseek": "deepseek-chat", "openai": "gpt-4o-mini"}


def create_llm() -> BaseChatModel:
    provider = settings.llm_provider
    if provider == "mock":
        from backend.infrastructure.llm.mock import FakeChatModel

        return FakeChatModel()
    if provider not in PROVIDER_MODELS:
        raise ValueError(f"未知的 LLM_PROVIDER: {provider!r}")
    if not settings.llm_api_key:
        raise RuntimeError(f"LLM_PROVIDER={provider} 需要配置 LLM_API_KEY")

    from langchain_openai import ChatOpenAI

    base_url = settings.llm_base_url or (
        "https://api.deepseek.com/v1" if provider == "deepseek" else ""
    )
    kwargs = {
        "model": settings.llm_model or PROVIDER_MODELS[provider],
        "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout,
        "streaming": True,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)

__all__ = ["create_llm"]
