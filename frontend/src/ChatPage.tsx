/** 对话页：Bubble.List 渲染消息，Sender 负责输入，工具调用用 ThoughtChain 展示。 */

import { useMemo, useState } from "react";
import { Bubble, Prompts, Sender, ThoughtChain, Welcome } from "@ant-design/x";
import type { ThoughtChainItemType } from "@ant-design/x";
import { ReloadOutlined, RobotOutlined, SendOutlined, ToolOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Space, Tag, Typography } from "antd";

import { useChat } from "./hooks/useChat";
import type { ChatMessage, Ticket } from "./types";

const { Paragraph, Text } = Typography;

const EXAMPLES = [
  "VPN 连不上，提示 691 错误怎么办？",
  "域账号被锁了，怎么解锁？",
  "帮我建个工单，会议室的网络打印机装不上驱动，联系我 zhang.san@corp.com",
  "帮我查一下进程",
];

function toolChainItems(message: ChatMessage): ThoughtChainItemType[] {
  return message.tools.map((tool) => ({
    key: tool.key,
    title: tool.phase === "call" ? `调用工具 ${tool.name}` : `工具返回 ${tool.name}`,
    description: tool.message || undefined,
    status: tool.phase === "call" ? "loading" : tool.ok === false ? "error" : "success",
    collapsible: Boolean(tool.message),
  }));
}

function bubbleContent(message: ChatMessage) {
  if (message.error) {
    return <Text type="danger">{message.error}</Text>;
  }
  if (!message.content && message.loading) {
    return <Text type="secondary">正在思考…</Text>;
  }
  return <div className="bubble-text">{message.content}</div>;
}

export interface ChatPageProps {
  onTicketEvent?: (tickets: Ticket[]) => void;
  onOpenTicket?: (ticketId: string) => void;
  mock: boolean;
}

export default function ChatPage({ onTicketEvent, onOpenTicket, mock }: ChatPageProps) {
  const { messages, busy, send, stop, reset, threadId } = useChat();
  const [input, setInput] = useState("");

  const items = useMemo(
    () =>
      messages.map((message) => ({
        key: message.key,
        role: message.role,
        content: message.role === "ai" ? bubbleContent(message) : message.content,
        loading: message.loading,
        footer: (
          <Space direction="vertical" size={4} style={{ width: "100%" }}>
            {message.tools.length > 0 && (
              <ThoughtChain items={toolChainItems(message)} defaultExpandedKeys={[]} />
            )}
            {message.tickets.map((ticket) => (
              <Space key={ticket.id} size={6} wrap>
                <Tag color="blue" style={{ cursor: "pointer" }} onClick={() => onOpenTicket?.(ticket.id)}>
                  {ticket.id}
                </Tag>
                <Text type="secondary">
                  {ticket.category} / {ticket.priority} / {ticket.status}
                </Text>
              </Space>
            ))}
            {message.citations.map((citation) => (
              <Text key={`${citation.title}-${citation.source}`} type="secondary">
                引用：{citation.title}（{citation.source}）
              </Text>
            ))}
          </Space>
        ),
      })),
    [messages, onOpenTicket],
  );

  const handleSubmit = (text: string) => {
    setInput("");
    void send(text, onTicketEvent);
  };

  return (
    <div className="chat-page">
      <div className="chat-scroll">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <Welcome
              icon={<RobotOutlined />}
              variant="borderless"
              title="企业IT服务台智能助理"
              description={
                mock
                  ? "当前是演示模式：回答是内置占位内容，但「提问 → 建单 → 查进度 → 转人工」的链路是真的。"
                  : "用日常语言描述问题即可。知识库解决不了、或你明确要求时，我会帮你建工单。"
              }
            />
            <Prompts
              title="试试这些"
              items={EXAMPLES.map((example, index) => ({ key: String(index), label: example, description: example }))}
              onItemClick={(info) => setInput(String(info.data.label ?? ""))}
              wrap
            />
          </div>
        ) : (
          <Bubble.List
            items={items}
            autoScroll
            role={{
              ai: {
                placement: "start",
                avatar: <RobotOutlined />,
                variant: "outlined",
              },
              user: {
                placement: "end",
                avatar: <UserOutlined />,
                variant: "filled",
              },
            }}
          />
        )}
      </div>

      <div className="chat-footer">
        {mock && (
          <Alert
            type="warning"
            showIcon
            banner
            message="演示模式：模型是内置占位实现，建单/查单/转人工工具与记忆是真实执行的。"
          />
        )}
        <Paragraph type="secondary" style={{ margin: "8px 0 0", fontSize: 12 }}>
          会话 ID：{threadId}　
          <ToolOutlined /> 可用工具：建单 / 查进度 / 转人工
        </Paragraph>
        <Space.Compact style={{ width: "100%", marginTop: 8 }}>
          <Sender
            value={input}
            onChange={setInput}
            onSubmit={handleSubmit}
            loading={busy}
            onCancel={stop}
            placeholder="描述你遇到的问题，Enter 发送"
            autoSize={{ minRows: 1, maxRows: 5 }}
            style={{ flex: 1 }}
          />
          <Button type="primary" icon={<SendOutlined />} disabled={busy || !input.trim()} onClick={() => handleSubmit(input)}>
            发送
          </Button>
          <Button icon={<ReloadOutlined />} onClick={reset} disabled={messages.length === 0}>
            新会话
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
