"""四路图标注测试。"""

from backend.scripts.draw_graph import _annotate


def test_annotates_four_way_branches() -> None:
    raw = (
        "graph TD;\n"
        "\tpreprocess(preprocess)\n"
        "\tclassify(classify)\n"
        "\tknowledge(knowledge)\n"
        "\tquery(query)\n"
        "\tservice(service)\n"
        "\tfallback(fallback)\n"
        "\tclassify -.-> knowledge;\n"
        "\tclassify -.-> query;\n"
        "\tclassify -.-> service;\n"
        "\tclassify -.-> fallback;\n"
    )
    annotated = _annotate(raw, has_retriever=True)
    assert "意图识别 + 规则兜底" in annotated
    assert "RAG 问答" in annotated
    assert "classify -.->|knowledge| knowledge;" in annotated
    assert "classify -.->|fallback| fallback;" in annotated
