"""知识库浏览/搜索用例（RAG 召回仍走 BaseRetriever，这里负责目录与详情）。"""

from __future__ import annotations

from typing import Protocol

from backend.domain.knowledge import KnowledgeArticle, KnowledgeCategory


class KnowledgeCatalog(Protocol):
    def categories(self) -> list[KnowledgeCategory]: ...

    def get(self, article_no: str) -> KnowledgeArticle | None: ...

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]: ...

    def count(self) -> int: ...


class KnowledgeService:
    def __init__(self, catalog: KnowledgeCatalog) -> None:
        self._catalog = catalog

    def categories(self) -> list[KnowledgeCategory]:
        return self._catalog.categories()

    def get(self, article_no: str) -> KnowledgeArticle | None:
        return self._catalog.get(article_no)

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]:
        return self._catalog.search(q=q, category=category, limit=limit)

    def count(self) -> int:
        return self._catalog.count()
