"""可观测性：给后台管理页与排查用的埋点实现。

POC 用进程内统计（重启清零、单实例有效）；生产换成 Prometheus/OpenTelemetry + 日志聚合。
"""

from backend.infrastructure.observability.metrics import MetricsCollector, estimate_tokens

__all__ = ["MetricsCollector", "estimate_tokens"]
