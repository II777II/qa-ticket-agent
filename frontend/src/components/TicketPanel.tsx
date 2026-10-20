import { useEffect, useMemo, useState } from "react";
import { Badge, Button, Drawer, Empty, Input, Select, Timeline, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { getTicket } from "../api/agent";
import type { Ticket } from "../types";

const { Text, Paragraph } = Typography;

const PRIORITY_CLASS: Record<string, string> = {
  紧急: "tag-red",
  高: "tag-amber",
  中: "tag-blue",
  低: "tag-green",
};

export interface TicketPanelProps {
  /** 数据来源：turn=本轮问答产生/查询到的工单；all=显式查询全部 */
  mode: "turn" | "all";
  tickets: Ticket[];
  question: string;
  loading: boolean;
  selectedId: string | null;
  onSelect: (ticketId: string | null) => void;
  onLoadAll: () => void;
  onReloadAll: () => void;
  onExitAll: () => void;
}

/** 第 4 屏右侧：工单查询（关键字 + 状态过滤）+ 详情抽屉（时间线）。 */
export default function TicketPanel({
  mode,
  tickets,
  question,
  loading,
  selectedId,
  onSelect,
  onLoadAll,
  onReloadAll,
  onExitAll,
}: TicketPanelProps) {
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string>("全部");
  const [detail, setDetail] = useState<Ticket | null>(null);

  const filtered = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    return tickets.filter((ticket) => {
      const statusOk = status === "全部" || ticket.status === status;
      const keyOk =
        !key ||
        ticket.id.toLowerCase().includes(key) ||
        ticket.title.toLowerCase().includes(key) ||
        ticket.contact.toLowerCase().includes(key);
      return statusOk && keyOk;
    });
  }, [tickets, keyword, status]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setDetail(tickets.find((ticket) => ticket.id === selectedId) ?? null);
    let cancelled = false;
    getTicket(selectedId)
      .then((fresh) => {
        if (!cancelled) setDetail(fresh);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [selectedId, tickets]);

  return (
    <aside className="side-panel">
      <div className="panel-head">
        <span className="panel-title">工单查询</span>
        <Badge count={tickets.length} showZero color="#0d8f6f" />
        {mode === "turn" ? (
          <Button size="small" type="text" onClick={onLoadAll}>
            查询全部
          </Button>
        ) : (
          <>
            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={onReloadAll} loading={loading}>
              刷新
            </Button>
            <Button size="small" type="text" onClick={onExitAll}>
              返回本轮
            </Button>
          </>
        )}
      </div>

      {mode === "turn" && (
        <div className="panel-query">
          <Text type="secondary">本轮问题</Text>
          <div className="query-text">{question || "（这一轮还没有提问）"}</div>
        </div>
      )}

      <div className="ticket-filters">
        <Input
          size="small"
          allowClear
          placeholder="单号 / 标题 / 联系人"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
        <Select
          size="small"
          value={status}
          onChange={setStatus}
          options={["全部", "待受理", "处理中", "待用户确认", "已关闭"].map((value) => ({ value, label: value }))}
        />
      </div>

      {filtered.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={mode === "turn" ? "本轮没有产生或查询到工单" : "没有匹配的工单"}
        />
      ) : (
        <div className="ticket-list">
          {filtered.map((ticket) => (
            <button type="button" key={ticket.id} className="ticket-card" onClick={() => onSelect(ticket.id)}>
              <div className="ticket-card-head">
                <span className="ticket-id">{ticket.id}</span>
                <span className={`tag ${PRIORITY_CLASS[ticket.priority] ?? "tag-blue"}`}>{ticket.priority}</span>
                <span className={`tag tag-status-${ticket.status}`}>{ticket.status}</span>
              </div>
              <div className="ticket-title">{ticket.title}</div>
              <div className="ticket-meta">
                <span>{ticket.category}</span>
                <span>{ticket.contact}</span>
                <span>{ticket.created_at}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <Drawer width={420} open={Boolean(detail)} onClose={() => onSelect(null)} title={detail ? `${detail.id}　${detail.title}` : ""}>
        {detail && (
          <>
            <div className="detail-row">
              <span className={`tag tag-status-${detail.status}`}>{detail.status}</span>
              <span className={`tag ${PRIORITY_CLASS[detail.priority] ?? "tag-blue"}`}>{detail.priority}</span>
              <span className="tag">{detail.category}</span>
            </div>
            <Paragraph className="detail-desc">
              <Text strong>问题描述</Text>
              <br />
              <Text type="secondary">{detail.description}</Text>
            </Paragraph>
            <div className="detail-row detail-meta">
              <span>联系人 {detail.contact}</span>
              <span>创建 {detail.created_at}</span>
              <span>更新 {detail.updated_at}</span>
            </div>
            <Text strong>处理时间线</Text>
            <Timeline
              style={{ marginTop: 12 }}
              items={detail.events.map((event) => ({
                children: (
                  <div>
                    <Text>{event.action}</Text>
                    <div className="timeline-meta">
                      {event.at} · {event.actor}
                    </div>
                    {event.note && <div className="timeline-note">{event.note}</div>}
                  </div>
                ),
              }))}
            />
          </>
        )}
      </Drawer>
    </aside>
  );
}
