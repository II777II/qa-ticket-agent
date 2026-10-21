"""画图用例：节点标注要跟着运行时配置走，不能硬编码。"""

from __future__ import annotations

from backend.scripts.draw_graph import _annotate

RAW_MERMAID = (
    "graph TD;\n"
    "\t__start__([<p>__start__</p>]):::first\n"
    "\tagent(agent)\n"
    "\ttools(tools)\n"
    "\t__end__([<p>__end__</p>]):::last\n"
    "\t__start__ --> agent;\n"
    "\tagent -.-> __end__;\n"
    "\tagent -.-> tools;\n"
    "\ttools --> agent;\n"
)


def test_annotates_agent_with_rag_steps() -> None:
    annotated = _annotate(RAW_MERMAID, tool_names=["create_ticket"], has_retriever=True)
    assert "检索知识库 (RAG)" in annotated
    assert "命中片段拼进系统提示" in annotated
    assert "llm.bind_tools().invoke()" in annotated
    assert "agent(agent)" not in annotated  # 裸节点标签被替换掉


def test_marks_missing_retriever() -> None:
    annotated = _annotate(RAW_MERMAID, tool_names=["create_ticket"], has_retriever=False)
    assert "未接入检索" in annotated
    assert "检索知识库 (RAG)" not in annotated


def test_writes_real_tool_names() -> None:
    annotated = _annotate(
        RAW_MERMAID,
        tool_names=["create_ticket", "query_ticket", "escalate_to_human"],
        has_retriever=True,
    )
    assert "create_ticket / query_ticket / escalate_to_human" in annotated


def test_labels_conditional_edges() -> None:
    """LangGraph 不标条件边，这里把判断条件补上。"""
    annotated = _annotate(RAW_MERMAID, tool_names=["create_ticket"], has_retriever=True)
    assert "agent -.->|有 tool_calls| tools;" in annotated
    assert "agent -.->|无 tool_calls| __end__;" in annotated


def test_no_tools_node_when_empty() -> None:
    """没有工具时图里没有 tools 节点，标注逻辑不该凭空造一个。"""
    raw = (
        RAW_MERMAID.replace("\ttools(tools)\n", "")
        .replace("\tagent -.-> tools;\n", "")
        .replace("\ttools --> agent;\n", "")
    )
    annotated = _annotate(raw, tool_names=[], has_retriever=False)
    assert 'tools["' not in annotated


def test_annotates_logistics_agent_tool_loop() -> None:
    raw = (
        "graph TD;\n"
        "\tclassify(classify)\n"
        "\tlogistics(logistics)\n"
        "\tlogistics_agent(logistics_agent)\n"
        "\tlogistics_guard(logistics_guard)\n"
        "\tlogistics_tools(logistics_tools)\n"
        "\tclassify -.-> logistics;\n"
    )
    annotated = _annotate(raw, tool_names=["query_order"], has_retriever=False)
    assert "物流预处理" in annotated
    assert "bind_tools + 决策" in annotated
    assert "循环上限保护" in annotated
    assert "logistics_tools<br/>query_order" in annotated
    assert "classify -.->|logistics| logistics;" in annotated
