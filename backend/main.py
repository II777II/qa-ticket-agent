"""FastAPI 胶水层。

只做四件事：装配运行时、把 Agent 的流式输出转成 SSE、暴露健康检查与工单接口、
以及（可选）同源托管前端构建产物——`frontend/dist` 存在时访问 `/` 就是前端首页，
现场演示只开一个地址，也顺便绕开跨域。
编排逻辑在 graph.py，模型接入在 factories/llm.py，这一层刻意保持薄。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.runtime import AgentRuntime, create_runtime
from backend.schemas import (
    AgentInfoResponse,
    ChatRequest,
    HealthResponse,
    TicketRecord,
    sse,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("qa_ticket.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = create_runtime()
    logger.info("后端就绪: http://%s:%s/docs", settings.host, settings.port)
    yield
    app.state.runtime = None


app = FastAPI(
    title="企业IT服务台 智能问答工单 Agent POC",
    description="自然语言提问 -> RAG 知识库回答 -> 无法解决时自动建单。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_runtime() -> AgentRuntime:
    return app.state.runtime


@app.get("/health", response_model=HealthResponse, summary="健康检查")
async def health() -> HealthResponse:
    info = get_runtime().describe()
    return HealthResponse(
        status="ok",
        provider=info["provider"],
        mock=info["mock"],
        checkpointer=info["checkpointer"],
        retriever=info["retriever"],
        ticket_store=info["ticket_store"],
    )


@app.get("/api/agent-info", response_model=AgentInfoResponse, summary="当前 Agent 能力")
async def agent_info() -> AgentInfoResponse:
    info = get_runtime().describe()
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
        extensions=[
            *[f"tool:{name}" for name in info["tools"]],
            "compose:docker/docker-compose.yml",
        ],
    )


@app.post("/chat", summary="流式对话（SSE）")
async def chat(req: ChatRequest) -> StreamingResponse:
    runtime = get_runtime()

    async def event_stream():
        async for event, payload in runtime.stream(req.message, req.thread_id):
            yield sse(event, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 走 Nginx 时禁用缓冲，否则 SSE 会攒一批才下发
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/", summary="前端首页（已构建时）或服务说明")
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


@app.get("/api/tickets", response_model=list[TicketRecord], summary="工单列表（阶段三看板用）")
async def list_tickets(
    status: str | None = None,
    contact: str | None = None,
    limit: int = 20,
) -> list[TicketRecord]:
    store = get_runtime().store
    if store is None:
        return []
    return store.list(status=status, contact=contact, limit=limit)


@app.get("/api/tickets/{ticket_id}", response_model=TicketRecord, summary="工单详情")
async def get_ticket(ticket_id: str) -> TicketRecord:
    store = get_runtime().store
    record = store.get(ticket_id) if store else None
    if record is None:
        raise HTTPException(status_code=404, detail=f"工单不存在: {ticket_id}")
    return record


# 前端构建产物存在时挂上静态资源；API 路由在上面，不受影响（/docs 也照常可用）
_assets_dir = settings.frontend_dist / "assets"
if _assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")
