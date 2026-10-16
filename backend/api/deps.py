"""依赖取用点：路由从这里拿运行时与用例对象，不直接 import app 对象（避免循环导入）。"""

from __future__ import annotations

from fastapi import Request

from backend.application.chat import ChatService
from backend.application.runtime import AgentRuntime


def get_runtime(request: Request) -> AgentRuntime:
    return request.app.state.runtime


def get_chat(request: Request) -> ChatService:
    """一次请求一个用例对象：它只持有运行时引用，没有自己的状态。"""
    return ChatService(get_runtime(request))
