import { useCallback, useEffect, useState } from "react";
import { ReloadOutlined, RobotOutlined } from "@ant-design/icons";
import { Button, Empty, Space, Table, Typography } from "antd";

import { getMetrics } from "../api/agent";
import KpiCard from "../components/KpiCard";
import TrendChart from "../components/TrendChart";
import VersionBadge from "../components/VersionBadge";
import { navigate } from "../router";
import type { AgentInfo, MetricsSummary } from "../types";

const { Text } = Typography;

const NAV_ITEMS = ["运营概览", "模型配置", "知识库管理", "工单对接", "调用日志", "系统设置"];

function formatNumber(value: number): string {
  return value >= 10000 ? `${(value / 10000).toFixed(1)}w` : value.toLocaleString("zh-CN");
}

/** 第 5 屏：后台管理（运营概览）。 */
export default function AdminPage({ info }: { info: AgentInfo | null }) {
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setMetrics(await getMetrics(7));
    } catch {
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const kpis = metrics?.kpis;
  const byDay = metrics?.by_day ?? [];
  const rows = (metrics?.by_model ?? []).map((row) => ({ ...row, key: row.model }));

  return (
    <div className="shell">
      <aside className="sidebar admin-side">
        <div className="brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
          <span className="brand-mark">
            <RobotOutlined />
          </span>
          <span className="brand-name">智能问答</span>
        </div>
        <div className="admin-nav">
          {NAV_ITEMS.map((item, index) => (
            <button
              key={item}
              type="button"
              className={index === 0 ? "nav-item active" : "nav-item"}
              title={index === 0 ? "" : "POC 暂未实现"}
              disabled={index !== 0}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="sidebar-foot">
          <button type="button" className="nav-link" onClick={() => navigate("/chat")}>
            ← 返回对话
          </button>
          <VersionBadge sha={info?.git_sha} date={info?.git_date} />
        </div>
      </aside>

      <main className="admin-main">
        <header className="topbar">
          <span className="topbar-title">运营概览</span>
          <span className="pill">最近 7 天</span>
          <span className="spacer" />
          <Text type="secondary" style={{ fontSize: 11 }}>
            {metrics ? `数据更新于 ${metrics.generated_at}` : "暂无数据"}
          </Text>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>
            刷新
          </Button>
        </header>

        <div className="admin-body">
          <div className="kpi-row">
            <KpiCard label="Token 消耗" value={formatNumber(kpis?.tokens ?? 0)} hint="近 7 天 · 估算 + 真实 usage" />
            <KpiCard label="平均首字延迟" value={Math.round(kpis?.avg_first_token_ms ?? 0)} unit="ms" hint={`P95 ${kpis?.p95_first_token_ms ?? 0} ms`} />
            <KpiCard label="请求总量" value={formatNumber(kpis?.requests ?? 0)} unit="次" hint={`平均 ${Math.round(kpis?.avg_latency_ms ?? 0)} ms / 轮`} />
            <KpiCard label="错误率" value={(kpis?.error_rate ?? 0).toFixed(2)} unit="%" hint="单轮失败占比" />
          </div>

          <div className="chart-row">
            <div className="chart-card">
              <div className="chart-head">
                <span>系统延迟趋势</span>
                <span className="muted">单位 ms</span>
              </div>
              {byDay.length > 0 ? (
                <TrendChart data={byDay.map((day) => ({ label: day.date, value: day.avg_latency_ms }))} mode="line" />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有调用数据" />
              )}
            </div>
            <div className="chart-card">
              <div className="chart-head">
                <span>Token 消耗分布</span>
                <span className="muted">近 7 天</span>
              </div>
              {byDay.length > 0 ? (
                <TrendChart data={byDay.map((day) => ({ label: day.date, value: day.tokens }))} mode="bars" />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有调用数据" />
              )}
            </div>
          </div>

          <div className="table-card">
            <div className="chart-head">
              <span>模型调用明细</span>
              <span className="muted">按 Token 消耗排序</span>
            </div>
            <Table
              size="small"
              pagination={false}
              dataSource={rows}
              locale={{ emptyText: "跑几轮对话后这里会出现数据（进程内统计，重启清零）" }}
              columns={[
                { title: "模型", dataIndex: "model", key: "model" },
                { title: "调用次数", dataIndex: "calls", key: "calls", align: "right" as const },
                { title: "Token 消耗", dataIndex: "tokens", key: "tokens", align: "right" as const, render: (value: number) => formatNumber(value) },
                { title: "平均延迟", dataIndex: "avg_latency_ms", key: "latency", align: "right" as const, render: (value: number) => `${Math.round(value)} ms` },
                {
                  title: "成功率",
                  dataIndex: "success_rate",
                  key: "success",
                  align: "right" as const,
                  render: (value: number) => <span className={value >= 99 ? "ok-text" : ""}>{value}%</span>,
                },
              ]}
            />
          </div>

          <Space>
            <Text type="secondary" style={{ fontSize: 11 }}>
              POC 指标为进程内统计：重启清零、单实例有效；生产应接 Prometheus / 日志平台。
            </Text>
          </Space>
        </div>
      </main>
    </div>
  );
}
