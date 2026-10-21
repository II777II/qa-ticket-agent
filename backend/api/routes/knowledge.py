"""知识库路由：供「对话 + 知识库检索」页面右侧面板使用。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import get_runtime
from backend.api.schemas import KnowledgeHit
from backend.application.runtime import AgentRuntime
from backend.domain.knowledge import KnowledgeArticle, KnowledgeCategory

router = APIRouter(tags=["knowledge"])


@router.get("/api/kb/categories", response_model=list[KnowledgeCategory], summary="知识库分类")
async def list_categories(runtime: AgentRuntime = Depends(get_runtime)) -> list[KnowledgeCategory]:
    return runtime.knowledge.categories()


@router.get("/api/kb/articles", response_model=list[KnowledgeArticle], summary="知识库文章列表")
async def list_articles(
    q: str = "",
    category: str = "",
    limit: int = 50,
    runtime: AgentRuntime = Depends(get_runtime),
) -> list[KnowledgeArticle]:
    return runtime.knowledge.search(q=q, category=category, limit=limit)


@router.get("/api/kb/articles/{article_no}", response_model=KnowledgeArticle, summary="知识库文章详情")
async def get_article(article_no: str, runtime: AgentRuntime = Depends(get_runtime)) -> KnowledgeArticle:
    article = runtime.knowledge.get(article_no)
    if article is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"文章不存在: {article_no}")
    return article


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
        )
        for position, document in enumerate(documents, start=1)
    ]
