"""运营指标路由：后台管理页的 KPI、趋势与模型明细。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import get_runtime
from backend.api.schemas import MetricsSummary
from backend.application.runtime import AgentRuntime

router = APIRouter(tags=["metrics"])


@router.get("/api/metrics/summary", response_model=MetricsSummary, summary="运营指标汇总")
async def metrics_summary(days: int = 7, runtime: AgentRuntime = Depends(get_runtime)) -> MetricsSummary:
    return MetricsSummary(**runtime.metrics.summary(days=days))
