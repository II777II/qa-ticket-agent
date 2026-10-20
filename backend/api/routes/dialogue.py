"""对话能力聚合路由：平级挂载统一入口与显式分支入口。"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.routes import agent as agent_routes
from backend.api.routes import chat as chat_routes

router = APIRouter()
router.include_router(chat_routes.router)
router.include_router(agent_routes.router)
