import { DeleteOutlined, PlusOutlined, RobotOutlined } from "@ant-design/icons";

import { navigate } from "../router";
import type { Conversation } from "../types";
import VersionBadge from "./VersionBadge";

function groupConversations(items: Conversation[]) {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startYesterday = startToday - 86400000;
  const groups: { label: string; items: Conversation[] }[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "更早", items: [] },
  ];
  for (const item of items) {
    const bucket = item.updatedAt >= startToday ? groups[0] : item.updatedAt >= startYesterday ? groups[1] : groups[2];
    bucket.items.push(item);
  }
  return groups.filter((group) => group.items.length > 0);
}

function timeLabel(timestamp: number): string {
  const date = new Date(timestamp);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (conversation: Conversation) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  provider: string;
  mock: boolean;
  sha?: string;
  date?: string;
}

/** 对话页左侧栏：品牌、新建对话、按天分组的会话历史、版本徽标。 */
export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  provider,
  mock,
  sha,
  date,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
        <span className="brand-mark">
          <RobotOutlined />
        </span>
        <span className="brand-name">智能问答</span>
        <span className="brand-badge">Beta</span>
      </div>

      <button type="button" className="new-chat" onClick={onNew}>
        <PlusOutlined /> 新建对话
      </button>

      <div className="history">
        {groupConversations(conversations).map((group) => (
          <div key={group.label}>
            <div className="history-label">{group.label}</div>
            {group.items.map((conversation) => (
              <div
                key={conversation.id}
                className={conversation.id === activeId ? "history-item active" : "history-item"}
                onClick={() => onSelect(conversation)}
                role="button"
                tabIndex={0}
              >
                <span className="history-title">{conversation.title}</span>
                <span className="history-meta">
                  {timeLabel(conversation.updatedAt)} · {conversation.messages.length} 条
                  <button
                    type="button"
                    className="history-delete"
                    title="删除会话"
                    onClick={(event) => {
                      event.stopPropagation();
                      onDelete(conversation.id);
                    }}
                  >
                    <DeleteOutlined />
                  </button>
                </span>
              </div>
            ))}
          </div>
        ))}
        {conversations.length === 0 && <div className="history-empty">还没有对话记录</div>}
      </div>

      <div className="sidebar-foot">
        <button type="button" className="nav-link" onClick={() => navigate("/orders")}>
          ◈ 订单查询
        </button>
        <button type="button" className="nav-link" onClick={() => navigate("/kb")}>
          ◈ 知识库检索
        </button>
        <button type="button" className="nav-link" onClick={() => navigate("/admin")}>
          ◈ 运营概览
        </button>
        <div className="user">
          <span className="user-avatar">企</span>
          <span className="user-meta">
            <span className="user-name">演示用户</span>
            <span className="user-sub">
              {provider}
              {mock ? " · 演示模式" : ""}
            </span>
          </span>
        </div>
        <VersionBadge sha={sha} date={date} />
      </div>
    </aside>
  );
}
