import { Bubble, ThoughtChain } from "@ant-design/x";
import type { ThoughtChainItemType } from "@ant-design/x";
import { RobotOutlined, UserOutlined } from "@ant-design/icons";

import type { ChatMessage } from "../types";

function toolItems(message: ChatMessage): ThoughtChainItemType[] {
  return message.tools.map((tool) => ({
    key: tool.key,
    title: tool.phase === "call" ? `调用工具 ${tool.name}` : `工具返回 ${tool.name}`,
    description: tool.message || undefined,
    status: tool.phase === "call" ? "loading" : tool.ok === false ? "error" : "success",
    collapsible: Boolean(tool.message),
  }));
}

function body(message: ChatMessage) {
  if (message.error) return <div className="bubble-text bubble-error">{message.error}</div>;
  if (!message.content && message.loading) return <div className="bubble-text bubble-muted">正在思考…</div>;
  return <div className="bubble-text">{message.content}</div>;
}

export interface MessageListProps {
  messages: ChatMessage[];
  onOpenTicket?: (ticketId: string) => void;
}

export default function MessageList({ messages, onOpenTicket }: MessageListProps) {
  const items = messages.map((message) => ({
    key: message.key,
    role: message.role,
    content: message.role === "ai" ? body(message) : message.content,
    loading: message.loading,
    footer: (
      <div className="bubble-footer">
        {message.tools.length > 0 && <ThoughtChain items={toolItems(message)} defaultExpandedKeys={[]} />}
        {message.citations.length > 0 && (
          <div className="cite-row">
            {message.citations.map((citation) => (
              <span className="cite" key={`${citation.source}-${citation.title}`} title={citation.snippet}>
                [{citation.index}] {citation.source} · {citation.title}
              </span>
            ))}
          </div>
        )}
        {message.tickets.length > 0 && (
          <div className="cite-row">
            {message.tickets.map((ticket) => (
              <button
                key={ticket.id}
                type="button"
                className="cite cite-green"
                onClick={() => onOpenTicket?.(ticket.id)}
              >
                🎫 {ticket.id} · {ticket.status}
              </button>
            ))}
          </div>
        )}
      </div>
    ),
  }));

  return (
    <Bubble.List
      className="message-list"
      items={items}
      autoScroll
      role={{
        ai: { placement: "start", avatar: <RobotOutlined />, variant: "outlined" },
        user: { placement: "end", avatar: <UserOutlined />, variant: "filled" },
      }}
    />
  );
}
