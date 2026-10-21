"""HTTP request schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from backend.domain.core import ServiceType, TicketCategory, TicketPriority


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str = "default"


class ServiceConfirmRequest(BaseModel):
    order_no: str = Field(pattern=r"^SO\d{12}$")
    contact: str = Field(min_length=2, max_length=120)
    service_type: ServiceType
    category: TicketCategory
    priority: TicketPriority = "中"
    description: str = Field(min_length=10, max_length=2000)


class LlmConfigRequest(BaseModel):
    provider: Literal["mock", "deepseek", "openai"]
    api_key: SecretStr | None = None
    model: str = Field(default="", max_length=120)
    base_url: str = Field(default="", max_length=300)
