/** 右侧工单面板：列表 + 详情抽屉（含时间线）。数据来自后端的 JSON 工单存储。 */

import { useEffect, useState } from "react";
import { Badge, Button, Card, Descriptions, Drawer, Empty, List, Space, Tag, Timeline, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";

import { getTicket } from "./api/agent";
import type { Ticket } from "./types";

const { Text, Paragraph } = Typography;

const STATUS_COLOR: Record<string, string> = {
  待受理: "orange",
  处理中: "blue",
  待用户确认: "purple",
  已关闭: "default",
};

const PRIORITY_COLOR: Record<string, string> = {
  紧急: "red",
  高: "volcano",
  中: "gold",
  低: "green",
};

export interface TicketPanelProps {
  tickets: Ticket[];
  loading: boolean;
  /** 当前打开详情的工单 ID（由对话区的工单标签或列表点击触发） */
  selectedId?: string | null;
  onRefresh: () => void;
  onSelect: (ticketId: string | null) => void;
}

export default function TicketPanel({ tickets, loading, selectedId, onRefresh, onSelect }: TicketPanelProps) {
  const [detail, setDetail] = useState<Ticket | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 打开抽屉时重新拉一次详情，拿到最新的时间线
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    // 先用列表里那份兜底显示，再换成最新详情
    setDetail((current) => current ?? tickets.find((ticket) => ticket.id === selectedId) ?? null);
    setDetailLoading(true);
    getTicket(selectedId)
      .then((fresh) => {
        if (!cancelled) setDetail(fresh);
      })
      .catch(() => {
        /* 详情拉不到就继续展示列表里的那份 */
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId, tickets]);

  return (
    <Card
      className="ticket-panel"
      title={
        <Space>
          工单
          <Badge count={tickets.length} showZero color="#1677ff" />
        </Space>
      }
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>刷新</Button>}
      styles={{ body: { padding: 12 } }}
    >
      {tickets.length === 0 ? (
        <Empty description="还没有工单，试试让助理建一张" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <List
          dataSource={tickets}
          renderItem={(ticket) => (
            <List.Item key={ticket.id} onClick={() => onSelect(ticket.id)} style={{ cursor: "pointer" }}>
              <List.Item.Meta
                title={
                  <Space size={6} wrap>
                    <Text strong>{ticket.title}</Text>
                  </Space>
                }
                description={
                  <Space direction="vertical" size={4}>
                    <Space size={4} wrap>
                      <Tag color={PRIORITY_COLOR[ticket.priority] ?? "default"}>{ticket.priority}</Tag>
                      <Tag color={STATUS_COLOR[ticket.status] ?? "default"}>{ticket.status}</Tag>
                      <Tag>{ticket.category}</Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {ticket.id} · {ticket.contact}
                    </Text>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}

      <Drawer
        width={420}
        open={Boolean(detail)}
        onClose={() => onSelect(null)}
        title={detail ? `${detail.id}　${detail.title}` : ""}
      >
        {detail && (
          <>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[detail.status] ?? "default"}>{detail.status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="分类 / 优先级">
                <Tag>{detail.category}</Tag>
                <Tag color={PRIORITY_COLOR[detail.priority] ?? "default"}>{detail.priority}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="联系人">{detail.contact}</Descriptions.Item>
              <Descriptions.Item label="来源">{detail.source}</Descriptions.Item>
              <Descriptions.Item label="创建 / 更新">
                {detail.created_at}
                <br />
                {detail.updated_at}
              </Descriptions.Item>
            </Descriptions>
            <Paragraph style={{ marginTop: 16 }}>
              <Text strong>问题描述</Text>
              <br />
              <Text type="secondary">{detail.description}</Text>
            </Paragraph>
            <Text strong>处理时间线</Text>
            <Timeline
              style={{ marginTop: 12 }}
              items={detail.events.map((event) => ({
                children: (
                  <>
                    <Text>{event.action}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {event.at} · {event.actor}
                    </Text>
                    {event.note && (
                      <>
                        <br />
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {event.note}
                        </Text>
                      </>
                    )}
                  </>
                ),
              }))}
            />
            {detailLoading && <Text type="secondary">正在刷新详情…</Text>}
          </>
        )}
      </Drawer>
    </Card>
  );
}
