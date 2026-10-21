"""三路图标注测试。"""

from backend.scripts.draw_graph import _annotate


def test_annotates_three_way_branches() -> None:
    raw = (
        "graph TD;\n"
        "\tpreprocess(preprocess)\n"
        "\tclassify(classify)\n"
        "\tread(read)\n"
        "\twrite(write)\n"
        "\thuman(human)\n"
        "\tclassify -.-> read;\n"
        "\tclassify -.-> write;\n"
        "\tclassify -.-> human;\n"
    )
    annotated = _annotate(raw, has_retriever=True)
    assert "意图识别 + 规则兜底" in annotated
    assert "规则选择知识库/订单工具" in annotated
    assert "classify -.->|read| read;" in annotated
    assert "classify -.->|human| human;" in annotated
