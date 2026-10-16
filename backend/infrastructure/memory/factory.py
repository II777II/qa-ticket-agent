"""记忆工厂：按 CHECKPOINTER 创建 LangGraph 的检查点保存器。

POC 只做短期记忆（进程内存，thread_id 隔离）；生产换成 PostgresSaver 就是长期记忆，
业务代码不用改——LangGraph 只认 BaseCheckpointSaver 这个接口。
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver

from backend.infrastructure.config import settings


def create_checkpointer() -> BaseCheckpointSaver:
    kind = settings.checkpointer

    if kind == "memory":
        # langgraph 1.x 的正式名字是 InMemorySaver，MemorySaver 是旧别名
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    if kind == "postgres":
        raise NotImplementedError(
            "CHECKPOINTER=postgres 尚未接入：需要先 pip install langgraph-checkpoint-postgres，"
            "并在 docker/docker-compose.yml 里打开 postgres 服务、填好 DATABASE_URL。"
        )

    raise ValueError(f"未知的 CHECKPOINTER: {kind!r}，可选 memory / postgres")
