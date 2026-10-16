"""接口层数据结构：HTTP 请求体 + SSE 事件。

SSE 事件名固定成下面这几类，前端 streamChat 按事件名分发；
阶段二、四新增「工具」「引用」「建单」事件时，前端只需要多写一个 case。
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

EVENT_START = "start"          # 一轮开始（带头像信息：用的哪个模型、是否演示模式）
EVENT_TOKEN = "token"          # 自然语言增量
EVENT_TOOL = "tool"            # 阶段二：工具调用与返回
EVENT_CITATION = "citation"    # 阶段四：RAG 引用出处
EVENT_TICKET = "ticket"        # 阶段二：建单结果
EVENT_DONE = "done"            # 一轮结束
EVENT_ERROR = "error"          # 出错（前端据此展示兜底提示）


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="用户这一轮说的话")
    thread_id: str = Field(default="default", description="会话 ID，短期记忆按它隔离")
    user_id: str | None = Field(default=None, description="工单联系人标识，阶段二使用")


class HealthResponse(BaseModel):
    status: str
    provider: str
    mock: bool
    checkpointer: str | None = None
    retriever: str | None = None
    ticket_store: str | None = None


class AgentInfoResponse(HealthResponse):
    """给前端「Agent 配置」面板用：展示当前 POC 开了哪些能力。"""

    model: str = ""
    rag_top_k: int = 0
    tickets: int = 0
    kb_documents: int = 0
    kb_chunks: int = 0
    extensions: list[str] = Field(default_factory=list)


def sse(event: str, data: dict[str, Any]) -> str:
    """把一次事件编码成 SSE 报文。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class CitationPayload(BaseModel):
    """citation 事件的载荷：模型这句回答的依据来自哪篇文档的哪一小节。"""

    index: int = Field(description="回答里的标注编号，如 [1]")
    source: str = Field(description="文件名，如 vpn-691.md")
    title: str = Field(description="小节标题")
    snippet: str = Field(default="", description="命中片段前 160 字，供前端悬浮展示")
    score: float | None = Field(default=None, description="检索打分，调参时看它")


# 工单实体与业务规则已下沉到领域层（backend/domain/）：
#   实体  -> backend.domain.models
#   规则  -> backend.domain.rules
# 本模块只保留接口层 DTO 与 SSE 事件定义。
