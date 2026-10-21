"""订单、知识库和运营指标数据接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import get_runtime
from backend.api.schemas import KnowledgeHit, MetricsSummary
from backend.application.runtime import AgentRuntime
from backend.domain.knowledge import KnowledgeArticle, KnowledgeCategory
from backend.domain.orders import OrderRecord

router = APIRouter()


@router.get("/api/orders", response_model=list[OrderRecord], tags=["orders"])
async def list_orders(
    q: str = "",
    status: int | None = None,
    user_id: int | None = None,
    limit: int = 20,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[OrderRecord]:
    return runtime.orders.search(q=q, status=status, user_id=user_id, limit=limit)


@router.get("/api/kb/categories", response_model=list[KnowledgeCategory], tags=["knowledge"])
async def list_categories(runtime: AgentRuntime = Depends(get_runtime)) -> list[KnowledgeCategory]:
    return runtime.knowledge.categories()


@router.get("/api/kb/articles", response_model=list[KnowledgeArticle], tags=["knowledge"])
async def list_articles(
    q: str = "",
    category: str = "",
    limit: int = 50,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[KnowledgeArticle]:
    return runtime.knowledge.search(q=q, category=category, limit=limit)


@router.get("/api/kb/search", response_model=list[KnowledgeHit], tags=["knowledge"])
async def search_knowledge(
    q: str,
    top_k: int = 5,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[KnowledgeHit]:
    retriever = runtime.retriever
    if retriever is None or not q.strip():
        return []
    search = getattr(retriever, "search", None)
    documents = search(q, top_k=top_k) if callable(search) else list(retriever.invoke(q))[:top_k]
    return [
        KnowledgeHit(
            index=int(document.metadata.get("index", position)),
            source=str(document.metadata.get("source", "")),
            title=str(document.metadata.get("title", "")),
            snippet=document.page_content.strip()[:200],
            score=document.metadata.get("score"),
        )
        for position, document in enumerate(documents, start=1)
    ]


@router.get("/api/metrics/summary", response_model=MetricsSummary, tags=["metrics"])
async def metrics_summary(days: int = 7, runtime: AgentRuntime = Depends(get_runtime)) -> MetricsSummary:
    return MetricsSummary(**runtime.metrics.summary(days=days))
