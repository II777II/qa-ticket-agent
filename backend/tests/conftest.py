"""pytest 全局准备。

关键点：环境变量必须在 import backend.* 之前设置——`config.settings` 是模块级单例，
import 时就把值定下来了。pytest 会先导入 conftest，所以这里设置最合适。

另外把 DATA_DIR 指到临时目录，测试跑完不会在项目里留下工单数据。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 固定成演示模式与进程内实现，保证用例确定、不联网、不依赖外部服务
os.environ["LLM_PROVIDER"] = "mock"
os.environ["CHECKPOINTER"] = "memory"
os.environ["RETRIEVER"] = "memory"
os.environ["TICKET_STORE"] = "json"
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="qa-ticket-test-")

from backend.retrievers.memory import InMemoryRetriever  # noqa: E402
from backend.runtime import AgentRuntime, create_runtime  # noqa: E402
from backend.domain import TicketCreate  # noqa: E402
from backend.stores.json_store import JsonTicketStore  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> JsonTicketStore:
    """每个用例一个独立的工单文件，互不干扰。"""
    return JsonTicketStore(tmp_path / "tickets.json")


@pytest.fixture()
def retriever() -> InMemoryRetriever:
    from backend.config import settings

    return InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)


@pytest.fixture()
def runtime() -> AgentRuntime:
    return create_runtime()


def build_isolated_runtime(store_path: Path) -> AgentRuntime:
    """测试用运行时：工单写到指定文件，其余组件与生产完全一致。"""
    from langgraph.checkpoint.memory import InMemorySaver

    from backend.config import settings
    from backend.graph import build_graph
    from backend.mock_llm import FakeChatModel
    from backend.tools import create_tools

    llm = FakeChatModel()
    store = JsonTicketStore(store_path)
    tools = create_tools(store)
    retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
    checkpointer = InMemorySaver()
    graph = build_graph(llm=llm, tools=tools, retriever=retriever, checkpointer=checkpointer)
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tools=tools,
        retriever=retriever,
        checkpointer=checkpointer,
        store=store,
    )


@pytest.fixture()
def isolated_runtime(tmp_path: Path) -> AgentRuntime:
    return build_isolated_runtime(tmp_path / "tickets.json")


@pytest.fixture()
def sample_ticket() -> TicketCreate:
    return TicketCreate(
        title="会议室打印机装不上驱动",
        description="Win11 装企业驱动包时报签名校验失败，已卸载旧驱动。",
        category="办公设备",
        priority="中",
        contact="zhang.san@corp.com",
    )
