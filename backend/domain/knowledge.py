"""电商知识库领域模型（对应 kb_article / kb_category）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KnowledgeArticle(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    article_no: str
    title: str
    summary: str = ""
    category_id: int
    category_code: str
    category_name: str
    article_type: int = 1
    tags: list[str] = []
    is_top: int = 0
    sort_weight: int = 0
    status: int = 2
    visibility: int = 0
    version_no: int = 1
    publish_time: str | None = None
    updated_at: str | None = None
    path: str
    url: str
    view_count: int = 0
    helpful_count: int = 0
    unhelpful_count: int = 0


class KnowledgeCategory(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    parent_id: int = 0
    name: str
    code: str
    level: int = 1
    path: str = ""
    sort_no: int = 0
    status: int = 1
