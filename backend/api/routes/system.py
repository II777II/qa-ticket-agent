"""系统类路由：健康检查、当前能力、首页。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from backend.api.deps import get_runtime
from backend.api.schemas import AgentInfoResponse, HealthResponse
from backend.application.runtime import AgentRuntime
from backend.infrastructure.config import settings
from backend.infrastructure.version import git_version

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health(runtime: AgentRuntime = Depends(get_runtime)) -> HealthResponse:
    info = runtime.describe()
    return HealthResponse(
        status="ok",
        provider=info["provider"],
        mock=info["mock"],
        checkpointer=info["checkpointer"],
        retriever=info["retriever"],
        ticket_store=info["ticket_store"],
    )


@router.get("/api/agent-info", response_model=AgentInfoResponse, summary="当前 Agent 能力")
async def agent_info(runtime: AgentRuntime = Depends(get_runtime)) -> AgentInfoResponse:
    info = runtime.describe()
    version = git_version()
    return AgentInfoResponse(
        status="ok",
        provider=info["provider"],
        mock=info["mock"],
        checkpointer=info["checkpointer"],
        retriever=info["retriever"],
        ticket_store=info["ticket_store"],
        model=info["model"],
        rag_top_k=settings.rag_top_k,
        tickets=info["tickets"],
        kb_documents=info["kb_documents"],
        kb_chunks=info["kb_chunks"],
        git_sha=version["sha"],
        git_date=version["date"],
        extensions=[
            *[f"tool:{name}" for name in info["tools"]],
            "compose:docker/docker-compose.yml",
        ],
    )


@router.get("/", summary="前端首页（已构建时）或服务说明")
async def root():
    index = settings.frontend_dist / "index.html"
    if index.is_file():
        return FileResponse(index)
    return {
        "name": "qa-ticket-agent",
        "docs": "/docs",
        "health": "/health",
        "chat": "POST /chat",
        "tickets": "GET /api/tickets",
        "frontend": "还没构建。开发用 npm run dev (5173)，演示用 npm run build 后由本服务托管",
    }
