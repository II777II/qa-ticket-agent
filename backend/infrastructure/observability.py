"""In-process metrics and optional Langfuse tracing."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from backend.infrastructure.config import Settings, settings


def estimate_tokens(text: str) -> int:
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    return max(1, cjk + max(len(text) - cjk, 0) // 4) if text else 0


class MetricsCollector:
    def __init__(self, max_records: int = 5000) -> None:
        self._lock, self._turns = threading.Lock(), deque(maxlen=max_records)

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
            self._turns.append((
                time.time(), intent or "unknown", max(tokens, 0),
                first_token_ms, max(total_ms, 0), ok,
            ))

    def reset(self) -> None:
        with self._lock:
            self._turns.clear()

    def summary(self, days: int = 7) -> dict:
        days = max(1, min(days, 30))
        cutoff = time.time() - days * 86400
        with self._lock:
            turns = [turn for turn in self._turns if turn[0] >= cutoff]
        firsts = [turn[3] for turn in turns if turn[3] is not None]
        avg = lambda values: round(sum(values) / len(values), 1) if values else 0.0
        intents: dict[str, list[int]] = {}
        for _, intent, tokens, _, latency, ok in turns:
            row = intents.setdefault(intent, [0, 0, 0, 0])
            row[0] += 1
            row[1] += tokens
            row[2] += latency
            row[3] += not ok
        total, errors = len(turns), sum(not turn[5] for turn in turns)
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
                ({
                    "intent": intent,
                    "calls": row[0],
                    "tokens": row[1],
                    "avg_latency_ms": round(row[2] / row[0], 1),
                    "success_rate": round((1 - row[3] / row[0]) * 100, 2),
                } for intent, row in intents.items()),
                key=lambda row: (-row["calls"], -row["tokens"]),
            ),
        }


@dataclass
class LangfuseTracing:
    handler: Any | None = None
    client: Any | None = None
    status: str = "disabled"
    reason: str = ""

    @property
    def enabled(self) -> bool:
        return self.handler is not None

    def shutdown(self) -> None:
        if self.client is None:
            return
        try:
            self.client.shutdown()
        except Exception:
            logging.getLogger("qa_ticket.langfuse").exception("Langfuse 关闭时刷新失败")


def create_langfuse_tracing(config: Settings | None = None) -> LangfuseTracing:
    cfg = config or settings
    if not cfg.langfuse_enabled:
        return LangfuseTracing(reason="LANGFUSE_ENABLED=false")
    if not cfg.langfuse_configured:
        return LangfuseTracing(status="misconfigured", reason="missing keys")
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler
        return LangfuseTracing(handler=CallbackHandler(), client=get_client(), status="enabled")
    except Exception as exc:
        logging.getLogger("qa_ticket.langfuse").exception("Langfuse 初始化失败，已降级为关闭")
        return LangfuseTracing(status="error", reason=f"{exc.__class__.__name__}: {exc}")
