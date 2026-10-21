"""运营指标用例：聚合口径、p95、错误率、按天补齐、按模型排序。"""

from __future__ import annotations

from backend.infrastructure.observability.metrics import MetricsCollector, estimate_tokens


def test_estimate_tokens_counts_cjk_and_latin() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("abcd") == 1  # 4 个英文字符 ≈ 1 token


def test_empty_summary_is_zeroed() -> None:
    summary = MetricsCollector().summary(days=7)
    assert summary["kpis"]["requests"] == 0
    assert summary["kpis"]["error_rate"] == 0.0
    assert len(summary["by_day"]) == 7  # 没有数据也补齐 7 天
    assert summary["by_model"] == []


def test_summary_aggregates_turns() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(model="mock", tokens=100, first_token_ms=100, total_ms=800, ok=True)
    metrics.record_turn(model="mock", tokens=200, first_token_ms=300, total_ms=1200, ok=True)
    metrics.record_turn(model="deepseek", tokens=300, first_token_ms=None, total_ms=500, ok=False)

    kpis = metrics.summary(days=1)["kpis"]
    assert kpis["requests"] == 3
    assert kpis["tokens"] == 600
    assert kpis["avg_first_token_ms"] == 200.0  # 只统计有首字时间的两轮
    assert kpis["p95_first_token_ms"] == 300
    assert kpis["avg_latency_ms"] == 833.3
    assert kpis["error_rate"] == 33.33


def test_by_model_sorted_by_tokens() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(model="a", tokens=10, first_token_ms=10, total_ms=100, ok=True)
    metrics.record_turn(model="b", tokens=50, first_token_ms=20, total_ms=200, ok=True)
    rows = metrics.summary(days=1)["by_model"]
    assert [row["model"] for row in rows] == ["b", "a"]
    assert rows[0]["success_rate"] == 100.0


def test_by_intent_aggregates_calls_tokens_latency_and_success() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(
        model="mock",
        intent="knowledge",
        tokens=100,
        first_token_ms=100,
        total_ms=800,
        ok=True,
    )
    metrics.record_turn(
        model="mock",
        intent="query",
        tokens=50,
        first_token_ms=50,
        total_ms=200,
        ok=True,
    )
    metrics.record_turn(
        model="mock",
        intent="knowledge",
        tokens=200,
        first_token_ms=300,
        total_ms=1200,
        ok=False,
    )

    rows = metrics.summary(days=1)["by_intent"]
    assert [row["intent"] for row in rows] == ["knowledge", "query"]
    assert rows[0]["calls"] == 2
    assert rows[0]["tokens"] == 300
    assert rows[0]["avg_latency_ms"] == 1000.0
    assert rows[0]["success_rate"] == 50.0


def test_reset_clears_records() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(model="mock", tokens=1, first_token_ms=1, total_ms=1, ok=True)
    metrics.reset()
    assert metrics.summary(days=1)["kpis"]["requests"] == 0
