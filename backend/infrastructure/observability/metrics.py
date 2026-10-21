"""进程内运营指标：KPI 与按意图聚合。"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return max(1, cjk + max(len(text) - cjk, 0) // 4)


class MetricsCollector:
    def __init__(self, max_records: int = 5000) -> None:
        self._lock = threading.Lock()
        self._turns: deque[tuple[float, str, int, int | None, int, bool]] = deque(
            maxlen=max_records
        )

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
                (time.time(), intent or "unknown", max(tokens, 0), first_token_ms, max(total_ms, 0), ok)
            )

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()

    def summary(self, days: int = 7) -> dict:
        days = max(1, min(days, 30))
        cutoff = time.time() - days * 86400
        with self._lock:
            turns = [turn for turn in self._turns if turn[0] >= cutoff]
        total = len(turns)
        firsts = [turn[3] for turn in turns if turn[3] is not None]
        errors = sum(not turn[5] for turn in turns)
        intents: dict[str, list[int]] = {}
        for _, intent, tokens, _, latency, ok in turns:
            row = intents.setdefault(intent, [0, 0, 0, 0])
            row[0] += 1
            row[1] += tokens
            row[2] += latency
            row[3] += 0 if ok else 1

        def avg(values: list[int]) -> float:
            return round(sum(values) / len(values), 1) if values else 0.0

        return {
            "days": days,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kpis": {
                "requests": total,
                "tokens": sum(turn[2] for turn in turns),
                "avg_first_token_ms": avg(firsts),
                "avg_latency_ms": avg([turn[4] for turn in turns]),
                "error_rate": round(errors / total * 100, 2) if total else 0.0,
            },
            "by_intent": sorted(
                (
                    {
                        "intent": intent,
                        "calls": row[0],
                        "tokens": row[1],
                        "avg_latency_ms": round(row[2] / row[0], 1),
                        "success_rate": round((1 - row[3] / row[0]) * 100, 2),
                    }
                    for intent, row in intents.items()
                ),
                key=lambda row: (-row["calls"], -row["tokens"]),
            ),
        }
