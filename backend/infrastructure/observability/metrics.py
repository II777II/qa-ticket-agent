"""进程内运营指标：token、延迟、错误率、按天/模型/意图聚合。

后台管理页的数据源。刻意保持零依赖、线程安全、可单测；
记录的是「一轮对话」而不是每次 LLM 调用，因为用户关心的是「问一个问题要多久」。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any


def estimate_tokens(text: str) -> int:
    """粗估 token：中文按 1 字≈1 token，其余按 4 字符≈1 token。

    真实模型返回 usage 时优先用真实值；演示模式没有 usage，只能用估算。
    """
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other = max(len(text) - cjk, 0)
    return max(1, cjk + other // 4)


@dataclass(frozen=True)
class TurnRecord:
    at: float
    model: str
    intent: str
    tokens: int
    first_token_ms: int | None
    total_ms: int
    ok: bool


class MetricsCollector:
    """线程安全的环形记录器（默认保留最近 5000 轮）。"""

    def __init__(self, max_records: int = 5000) -> None:
        self._lock = threading.Lock()
        self._turns: deque[TurnRecord] = deque(maxlen=max_records)

    def record_turn(
        self,
        *,
        model: str,
        tokens: int,
        first_token_ms: int | None,
        total_ms: int,
        ok: bool,
        intent: str = "unknown",
    ) -> None:
        with self._lock:
            self._turns.append(
                TurnRecord(
                    at=time.time(),
                    model=model or "unknown",
                    intent=intent or "unknown",
                    tokens=max(tokens, 0),
                    first_token_ms=first_token_ms,
                    total_ms=max(total_ms, 0),
                    ok=ok,
                )
            )

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()

    def summary(self, days: int = 7) -> dict[str, Any]:
        days = max(1, min(days, 30))
        cutoff = time.time() - days * 86400
        with self._lock:
            turns = [turn for turn in self._turns if turn.at >= cutoff]

        total = len(turns)
        tokens = sum(turn.tokens for turn in turns)
        firsts = sorted(turn.first_token_ms for turn in turns if turn.first_token_ms is not None)
        latencies = [turn.total_ms for turn in turns]
        errors = sum(1 for turn in turns if not turn.ok)

        def average(values: list[int]) -> float:
            return round(sum(values) / len(values), 1) if values else 0.0

        def p95(values: list[int]) -> int:
            if not values:
                return 0
            index = min(len(values) - 1, max(0, int(round(0.95 * (len(values) - 1)))))
            return values[index]

        today = date.today()
        day_buckets: dict[str, dict[str, Any]] = {}
        for offset in range(days - 1, -1, -1):
            key = (today - timedelta(days=offset)).strftime("%m-%d")
            day_buckets[key] = {"date": key, "requests": 0, "tokens": 0, "latency_total": 0, "errors": 0}

        model_buckets: dict[str, dict[str, Any]] = {}
        intent_buckets: dict[str, dict[str, Any]] = {}
        for turn in turns:
            day_key = datetime.fromtimestamp(turn.at).strftime("%m-%d")
            bucket = day_buckets.get(day_key)
            if bucket is not None:
                bucket["requests"] += 1
                bucket["tokens"] += turn.tokens
                bucket["latency_total"] += turn.total_ms
                bucket["errors"] += 0 if turn.ok else 1

            model = model_buckets.setdefault(
                turn.model, {"model": turn.model, "calls": 0, "tokens": 0, "latency_total": 0, "errors": 0}
            )
            model["calls"] += 1
            model["tokens"] += turn.tokens
            model["latency_total"] += turn.total_ms
            model["errors"] += 0 if turn.ok else 1

            intent = intent_buckets.setdefault(
                turn.intent,
                {"intent": turn.intent, "calls": 0, "tokens": 0, "latency_total": 0, "errors": 0},
            )
            intent["calls"] += 1
            intent["tokens"] += turn.tokens
            intent["latency_total"] += turn.total_ms
            intent["errors"] += 0 if turn.ok else 1

        by_day = [
            {
                "date": bucket["date"],
                "requests": bucket["requests"],
                "tokens": bucket["tokens"],
                "avg_latency_ms": round(bucket["latency_total"] / bucket["requests"], 1) if bucket["requests"] else 0.0,
            }
            for bucket in day_buckets.values()
        ]
        by_model = sorted(
            (
                {
                    "model": bucket["model"],
                    "calls": bucket["calls"],
                    "tokens": bucket["tokens"],
                    "avg_latency_ms": round(bucket["latency_total"] / bucket["calls"], 1) if bucket["calls"] else 0.0,
                    "success_rate": round((1 - bucket["errors"] / bucket["calls"]) * 100, 2) if bucket["calls"] else 100.0,
                }
                for bucket in model_buckets.values()
            ),
            key=lambda row: row["tokens"],
            reverse=True,
        )
        by_intent = sorted(
            (
                {
                    "intent": bucket["intent"],
                    "calls": bucket["calls"],
                    "tokens": bucket["tokens"],
                    "avg_latency_ms": round(bucket["latency_total"] / bucket["calls"], 1)
                    if bucket["calls"]
                    else 0.0,
                    "success_rate": round((1 - bucket["errors"] / bucket["calls"]) * 100, 2)
                    if bucket["calls"]
                    else 100.0,
                }
                for bucket in intent_buckets.values()
            ),
            key=lambda row: (-row["calls"], -row["tokens"]),
        )

        return {
            "days": days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kpis": {
                "requests": total,
                "tokens": tokens,
                "avg_first_token_ms": average(firsts),
                "p95_first_token_ms": p95(firsts),
                "avg_latency_ms": average(latencies),
                "error_rate": round(errors / total * 100, 2) if total else 0.0,
            },
            "by_day": by_day,
            "by_model": by_model,
            "by_intent": by_intent,
        }
