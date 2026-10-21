import { Bubble } from "@ant-design/x";
import { RobotOutlined, UserOutlined } from "@ant-design/icons";

import type { ChatMessage } from "../types";

function body(message: ChatMessage) {
  if (message.error) return <div className="bubble-text bubble-error">{message.error}</div>;
  if (!message.content && message.loading) return <div className="bubble-text bubble-muted">正在思考…</div>;
  return <div className="bubble-text">{message.content}</div>;
}

export interface MessageListProps {
  messages: ChatMessage[];
  /** 把右侧面板切到「这一轮」的知识库/订单/业务办理结果 */
  onFocusTurn?: (messageKey: string, panel: "knowledge" | "orders" | "service") => void;
}

export default function MessageList({ messages, onFocusTurn }: MessageListProps) {
  const items = messages.map((message) => ({
    key: message.key,
    role: message.role,
    content: message.role === "ai" ? body(message) : message.content,
    loading: message.loading,
    footer: (
      <div className="bubble-footer">
        {message.citations.length > 0 && (
          <div className="cite-row">
            {message.citations.map((citation) => (
              <button
                type="button"
                className="cite"
                key={`${citation.source}-${citation.title}`}
                title={citation.snippet}
                onClick={() => onFocusTurn?.(message.key, "knowledge")}
              >
                [{citation.index}] {citation.source} · {citation.title}
              </button>
            ))}
          </div>
        )}
        {(message.orders ?? []).length > 0 && (
          <div className="cite-row">
            {message.orders.map((order) => (
              <button
                key={order.order_no}
                type="button"
                className="cite cite-order"
                onClick={() => onFocusTurn?.(message.key, "orders")}
              >
                {order.order_no} · {order.status}
              </button>
            ))}
          </div>
        )}
        {message.serviceDraft && (
          <div className="cite-row">
            <button
              type="button"
              className="cite cite-service"
              onClick={() => onFocusTurn?.(message.key, "service")}
            >
              {message.serviceDraft.service_type || "业务办理"} ·{" "}
              {message.serviceDraft.ready ? "待确认" : `缺少 ${message.serviceDraft.missing.length} 项`}
            </button>
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
