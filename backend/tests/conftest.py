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

from backend.application.runtime import AgentRuntime, create_runtime  # noqa: E402
from backend.domain import TicketCreate  # noqa: E402
from backend.infrastructure.persistence.json_store import JsonTicketStore  # noqa: E402
from backend.infrastructure.retrieval.in_memory import InMemoryRetriever  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> JsonTicketStore:
    """每个用例一个独立的工单文件，互不干扰。"""
    return JsonTicketStore(tmp_path / "tickets.json")


@pytest.fixture()
def retriever() -> InMemoryRetriever:
    from backend.infrastructure.config import settings

    return InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)


@pytest.fixture()
def runtime() -> AgentRuntime:
    return create_runtime()


def build_isolated_runtime(store_path: Path) -> AgentRuntime:
    """测试用运行时：工单写到指定文件，其余组件与生产完全一致。"""
    from langgraph.checkpoint.memory import InMemorySaver

    from backend.application.agent import build_graph, create_tools
    from backend.application.knowledge import KnowledgeService
    from backend.application.orders import OrderService
    from backend.application.tickets import TicketService
    from backend.infrastructure.config import settings
    from backend.infrastructure.llm.mock import FakeChatModel
    from backend.infrastructure.observability import MetricsCollector
    from backend.infrastructure.persistence.factory import create_knowledge_catalog, create_order_store

    llm = FakeChatModel()
    store = JsonTicketStore(store_path)
    tickets = TicketService(store)
    tools = create_tools(tickets)
    retriever = InMemoryRetriever(docs_dir=settings.kb_dir, top_k=settings.rag_top_k)
    checkpointer = InMemorySaver()
    graph = build_graph(llm=llm, tools=tools, retriever=retriever, checkpointer=checkpointer)
    return AgentRuntime(
        graph=graph,
        llm=llm,
        tickets=tickets,
        metrics=MetricsCollector(),
        orders=OrderService(create_order_store()),
        knowledge=KnowledgeService(create_knowledge_catalog()),
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
        title="商品有质量问题，想申请售后",
        description="收到的商品外壳有裂痕，已拍照，希望换货或退款。",
        category="商品与质量",
        priority="中",
        contact="zhang.san@corp.com",
    )
