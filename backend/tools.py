"""工具注册表。

阶段一：空表（图里没有工具节点，Agent 直接回答问题）。
阶段二在这里补三个 @tool：
    create_ticket       建单：标题/描述/分类/优先级/联系人（参数走 Pydantic 校验，防幻觉乱建单）
    query_ticket        查进度、催单
    escalate_to_human   转人工
新增工具不需要改 graph.py：build_graph 会按 tools 是否为空自动挂上 Tool 节点。
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

TOOLS: list[BaseTool] = []


def get_tools() -> list[BaseTool]:
    return list(TOOLS)
