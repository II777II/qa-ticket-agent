"""运营指标：KPI、按意图聚合和重置。"""

from __future__ import annotations

from backend.infrastructure.observability import MetricsCollector, estimate_tokens


def test_estimate_tokens_counts_cjk_and_latin() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("你好") == 2
    assert estimate_tokens("abcd") == 1


def test_empty_summary_is_zeroed() -> None:
    summary = MetricsCollector().summary(days=7)
    assert summary["kpis"]["requests"] == 0
    assert summary["kpis"]["error_rate"] == 0.0
    assert summary["by_intent"] == []


def test_summary_aggregates_turns() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(intent="read", tokens=100, first_token_ms=100, total_ms=800, ok=True)
    metrics.record_turn(intent="write", tokens=200, first_token_ms=300, total_ms=1200, ok=True)
    metrics.record_turn(intent="human", tokens=300, first_token_ms=None, total_ms=500, ok=False)

    kpis = metrics.summary(days=1)["kpis"]
    assert kpis == {
        "requests": 3,
        "tokens": 600,
        "avg_first_token_ms": 200.0,
        "avg_latency_ms": 833.3,
        "error_rate": 33.33,
    }


def test_by_intent_aggregates_and_sorts_by_calls() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(intent="read", tokens=100, first_token_ms=100, total_ms=800, ok=True)
    metrics.record_turn(intent="write", tokens=50, first_token_ms=50, total_ms=200, ok=True)
    metrics.record_turn(intent="read", tokens=200, first_token_ms=300, total_ms=1200, ok=False)

    rows = metrics.summary(days=1)["by_intent"]
    assert [row["intent"] for row in rows] == ["read", "write"]
    assert rows[0] == {
        "intent": "read",
        "calls": 2,
        "tokens": 300,
        "avg_latency_ms": 1000.0,
        "success_rate": 50.0,
    }


def test_reset_clears_records() -> None:
    metrics = MetricsCollector()
    metrics.record_turn(intent="read", tokens=1, first_token_ms=1, total_ms=1, ok=True)
    metrics.reset()
    assert metrics.summary(days=1)["kpis"]["requests"] == 0
