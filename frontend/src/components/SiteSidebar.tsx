import { RobotOutlined } from "@ant-design/icons";

import { navigate } from "../router";
import type { AgentInfo } from "../types";
import VersionBadge from "./VersionBadge";

export interface SiteSidebarProps {
  active: "chat" | "orders" | "kb" | "admin";
  info: AgentInfo | null;
}

const NAV = [
  { key: "chat", label: "智能问答", path: "/chat" },
  { key: "orders", label: "订单查询", path: "/orders" },
  { key: "kb", label: "知识库检索", path: "/kb" },
  { key: "admin", label: "运营概览", path: "/admin" },
] as const;

/** 订单/知识库/后台共用的左侧导航。 */
export default function SiteSidebar({ active, info }: SiteSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
        <span className="brand-mark">
          <RobotOutlined />
        </span>
        <span className="brand-name">电商智能助手</span>
      </div>
      <div className="admin-nav">
        {NAV.map((item) => (
          <button
            key={item.key}
            type="button"
            className={item.key === active ? "nav-item active" : "nav-item"}
            onClick={() => navigate(item.path)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="sidebar-foot">
        <span className="user-name">
          {info?.mock ? "演示模式" : info?.provider ?? "Agent"}
        </span>
        <VersionBadge sha={info?.git_sha} date={info?.git_date} />
      </div>
    </aside>
  );
}
