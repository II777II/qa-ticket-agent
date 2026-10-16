"""FastAPI 胶水层。

只做三件事：装配运行时、把 Agent 的流式输出转成 SSE、暴露健康检查。
编排逻辑在 graph.py，模型接入在 factories/llm.py，这一层刻意保持薄。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.config import settings
from backend.runtime import AgentRuntime, create_runtime
from backend.schemas import AgentInfoResponse, ChatRequest, HealthResponse, sse

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


@app.get("/", summary="服务说明")
async def root() -> dict[str, str]:
    return {
        "name": "qa-ticket-agent",
        "docs": "/docs",
        "health": "/health",
        "chat": "POST /chat",
        "frontend": "阶段三：frontend/ (React + Ant Design X)",
    }
