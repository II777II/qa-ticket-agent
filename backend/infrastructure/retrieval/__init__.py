"""检索：实现 + 工厂。

换向量库时新增一个实现文件、在工厂里加一个分支即可，应用层不用动。
"""

from backend.infrastructure.retrieval.factory import create_retriever
from backend.infrastructure.retrieval.in_memory import (
    CONTEXT_FOOTER,
    CONTEXT_HEADER,
    InMemoryRetriever,
    format_context,
)

__all__ = [
    "create_retriever",
    "InMemoryRetriever",
    "format_context",
    "CONTEXT_HEADER",
    "CONTEXT_FOOTER",
]
