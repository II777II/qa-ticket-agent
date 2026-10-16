"""模型工厂：按 LLM_PROVIDER 创建 BaseChatModel。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from backend.infrastructure.config import settings

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
PROVIDER_DEFAULT_MODEL = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
}
PROVIDER_DEFAULT_BASE_URL = {
    "deepseek": DEEPSEEK_BASE_URL,
    "openai": "",
}


def create_llm() -> BaseChatModel:
    """返回一个统一的对话模型接口。

    mock      -> 本地假模型（无 Key 演示）
    deepseek  -> DeepSeek，走 OpenAI 兼容协议
    openai    -> OpenAI 或任意 OpenAI 兼容端点

    生产可换成 ChatLiteLLM 之类的多provider网关，调用方无感知。
    """
    provider = settings.llm_provider

    if provider == "mock":
        from backend.infrastructure.llm.mock import FakeChatModel

        return FakeChatModel()

    if provider not in PROVIDER_DEFAULT_MODEL:
        raise ValueError(
            f"未知的 LLM_PROVIDER: {provider!r}，可选 mock / deepseek / openai"
        )

    from langchain_openai import ChatOpenAI

    if not settings.llm_api_key:
        raise RuntimeError(
            f"LLM_PROVIDER={provider} 需要配置 LLM_API_KEY（可先用 LLM_PROVIDER=mock 演示）"
        )

    model = settings.llm_model or PROVIDER_DEFAULT_MODEL[provider]
    base_url = settings.llm_base_url or PROVIDER_DEFAULT_BASE_URL[provider]

    kwargs = {
        "model": model,
        "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature,
        "timeout": settings.llm_timeout,
        "streaming": True,
    }
    if base_url:
        kwargs["base_url"] = base_url

    return ChatOpenAI(**kwargs)
