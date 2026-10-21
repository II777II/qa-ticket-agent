"""Import HTML knowledge-base chunks into LangChain PGVector."""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from langchain_core.documents import Document

from backend.infrastructure.config import settings
from backend.infrastructure.retrieval import _split_sections
from backend.infrastructure.vector_store import create_pgvector_store


def main() -> int:
    parser = argparse.ArgumentParser(description="导入知识库到 PGVector")
    parser.add_argument("--kb-dir", type=Path, default=settings.kb_dir)
    parser.add_argument("--reset", action="store_true", help="先清空当前 collection")
    args = parser.parse_args()

    store, engine = create_pgvector_store(pre_delete_collection=args.reset)
    documents, ids = [], []
    for path in sorted(args.kb_dir.glob("*.html")):
        if path.name.lower() == "index.html":
            continue
        for index, (title, body) in enumerate(_split_sections(path)):
            documents.append(Document(
                page_content=body,
                metadata={"source": path.name, "title": title, "chunk": index},
            ))
            ids.append(str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path.name}:{title}:{index}")))

    try:
        if documents:
            store.add_documents(documents, ids=ids)
        print(f"已导入 {len(documents)} 个知识片段到 {settings.pgvector_collection}")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
