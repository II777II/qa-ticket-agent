"""进程内运营指标：KPI 与按意图聚合。"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return max(1, cjk + max(len(text) - cjk, 0) // 4)


@dataclass(frozen=True)
class TurnRecord:
    at: float
    intent: str
    tokens: int
    first_token_ms: int | None
    total_ms: int
    ok: bool


class MetricsCollector:
    def __init__(self, max_records: int = 5000) -> None:
        self._lock = threading.Lock()
        self._turns: deque[TurnRecord] = deque(maxlen=max_records)

    def record_turn(
        self,
        *,
        intent: str,
        tokens: int,
        first_token_ms: int | None,
        total_ms: int,
        ok: bool,
    ) -> None:
        with self._lock:
            self._turns.append(
                TurnRecord(
                    at=time.time(),
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
        firsts = [turn.first_token_ms for turn in turns if turn.first_token_ms is not None]
        latencies = [turn.total_ms for turn in turns]
        errors = sum(not turn.ok for turn in turns)

        def average(values: list[int]) -> float:
            return round(sum(values) / len(values), 1) if values else 0.0

        intents: dict[str, dict[str, Any]] = {}
        for turn in turns:
            row = intents.setdefault(
                turn.intent,
                {"intent": turn.intent, "calls": 0, "tokens": 0, "latency": 0, "errors": 0},
            )
            row["calls"] += 1
            row["tokens"] += turn.tokens
            row["latency"] += turn.total_ms
            row["errors"] += 0 if turn.ok else 1

        by_intent = sorted(
            (
                {
                    "intent": row["intent"],
                    "calls": row["calls"],
                    "tokens": row["tokens"],
                    "avg_latency_ms": round(row["latency"] / row["calls"], 1),
                    "success_rate": round((1 - row["errors"] / row["calls"]) * 100, 2),
                }
                for row in intents.values()
            ),
            key=lambda row: (-row["calls"], -row["tokens"]),
        )
        return {
            "days": days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kpis": {
                "requests": total,
                "tokens": sum(turn.tokens for turn in turns),
                "avg_first_token_ms": average(firsts),
                "avg_latency_ms": average(latencies),
                "error_rate": round(errors / total * 100, 2) if total else 0.0,
            },
            "by_intent": by_intent,
        }
