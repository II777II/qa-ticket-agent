"""检索实现。

POC：进程内关键词检索（零依赖、不联网、可解释），文档放 backend/data/kb/。
生产：pgvector / Qdrant / Milvus + 重排——只要保持 LangChain 的 BaseRetriever 接口，
graph.py 与工具层都不用动。
"""

from backend.retrievers.memory import (
    CONTEXT_HEADER,
    CONTEXT_FOOTER,
    InMemoryRetriever,
    format_context,
)

__all__ = ["InMemoryRetriever", "format_context", "CONTEXT_HEADER", "CONTEXT_FOOTER"]
