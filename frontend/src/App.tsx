/** 整体布局：上方状态条 + 左侧对话 + 右侧工单面板。 */

import { useCallback, useEffect, useState } from "react";
import { Layout, Space, Tag, Typography } from "antd";

import ChatPage from "./ChatPage";
import TicketPanel from "./TicketPanel";
import { getAgentInfo, listTickets } from "./api/agent";
import type { AgentInfo, Ticket } from "./types";

const { Header, Content } = Layout;
const { Text } = Typography;

export default function App() {
  const [info, setInfo] = useState<AgentInfo | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const refreshTickets = useCallback(async () => {
    setLoading(true);
    try {
      setTickets(await listTickets());
      setBackendError(null);
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    getAgentInfo()
      .then((data) => {
        setInfo(data);
        setBackendError(null);
      })
      .catch((error: unknown) => setBackendError(error instanceof Error ? error.message : String(error)));
    void refreshTickets();
  }, [refreshTickets]);

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <Space size={12} wrap>
          <Text strong style={{ fontSize: 16 }}>
            企业IT服务台 · 智能问答工单 Agent
          </Text>
          {info && (
            <>
              <Tag color={info.mock ? "orange" : "green"}>
                模型：{info.mock ? "演示模式" : info.provider}
              </Tag>
              <Tag>记忆：{info.checkpointer ?? "未接入"}</Tag>
              <Tag>工单：{info.ticket_store ?? "未接入"}</Tag>
              <Tag>检索：{info.retriever ?? "阶段四"}</Tag>
            </>
          )}
        </Space>
      </Header>
      <Content className="app-content">
        {backendError && (
          <div className="app-error">
            <Text type="danger">
              连不上后端：{backendError}。请确认后端已在 127.0.0.1:5179 启动
              （<Text code>python -m uvicorn backend.main:app --port 5179</Text>）。
            </Text>
          </div>
        )}
        <div className="app-body">
          <ChatPage
            mock={info?.mock ?? false}
            onTicketEvent={() => void refreshTickets()}
            onOpenTicket={(ticketId) => setSelectedTicketId(ticketId)}
          />
          <TicketPanel
            tickets={tickets}
            loading={loading}
            selectedId={selectedTicketId}
            onRefresh={() => void refreshTickets()}
            onSelect={setSelectedTicketId}
          />
        </div>
      </Content>
    </Layout>
  );
}
