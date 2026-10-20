"""知识库路由：供「对话 + 知识库检索」页面右侧面板使用。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import get_runtime
from backend.api.schemas import KnowledgeHit
from backend.application.runtime import AgentRuntime

router = APIRouter(tags=["knowledge"])


@router.get("/api/kb/search", response_model=list[KnowledgeHit], summary="知识库检索")
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
            coverage=document.metadata.get("coverage"),
        )
        for position, document in enumerate(documents, start=1)
    ]
