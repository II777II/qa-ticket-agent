"""知识库目录（articles.json + categories.json），供知识库页面浏览与搜索。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.domain.knowledge import KnowledgeArticle, KnowledgeCategory

logger = logging.getLogger("qa_ticket.kb_catalog")


class JsonKnowledgeCatalog:
    def __init__(self, articles_file: Path, categories_file: Path) -> None:
        self.articles_file = Path(articles_file)
        self.categories_file = Path(categories_file)
        self._articles: list[KnowledgeArticle] = []
        self._categories: list[KnowledgeCategory] = []
        self._load()

    def _load(self) -> None:
        if self.articles_file.is_file():
            self._articles = [KnowledgeArticle(**item) for item in json.loads(self.articles_file.read_text(encoding="utf-8"))]
        if self.categories_file.is_file():
            self._categories = [
                KnowledgeCategory(**item) for item in json.loads(self.categories_file.read_text(encoding="utf-8"))
            ]
        logger.info("知识库目录已加载: %d 篇文章 / %d 个分类", len(self._articles), len(self._categories))

    def categories(self) -> list[KnowledgeCategory]:
        return sorted(self._categories, key=lambda item: item.sort_no)

    def get(self, article_no: str) -> KnowledgeArticle | None:
        wanted = article_no.strip().upper()
        return next((article for article in self._articles if article.article_no.upper() == wanted), None)

    def search(self, *, q: str = "", category: str = "", limit: int = 50) -> list[KnowledgeArticle]:
        key = q.strip().lower()
        category_key = category.strip().lower()
        results = []
        for article in self._articles:
            if category_key and category_key not in {
                article.category_code.lower(),
                article.category_name.lower(),
                str(article.category_id),
            }:
                continue
            if key:
                haystack = [article.title.lower(), article.summary.lower(), article.article_no.lower()]
                haystack.extend(tag.lower() for tag in article.tags)
                if not any(key in text for text in haystack):
                    continue
            results.append(article)
        results.sort(key=lambda item: (item.is_top, item.sort_weight), reverse=True)
        return results[: max(limit, 0)]

    def count(self) -> int:
        return len(self._articles)
