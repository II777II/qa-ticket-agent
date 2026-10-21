import { useCallback, useEffect, useState } from "react";
import { SettingOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "antd";

import { getAgentInfo } from "./api/agent";
import LlmSettingsModal from "./components/LlmSettingsModal";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import HomePage from "./pages/HomePage";
import KnowledgePage from "./pages/KnowledgePage";
import OrdersPage from "./pages/OrdersPage";
import { useRoute } from "./router";
import type { AgentInfo } from "./types";

export default function App() {
  const route = useRoute();
  const [info, setInfo] = useState<AgentInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const refreshInfo = useCallback(() => {
    getAgentInfo()
      .then((data) => {
        setInfo(data);
        setError(null);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    refreshInfo();
  }, [refreshInfo]);

  const page =
    route.page === "admin" ? (
      <AdminPage info={info} onOpenLlmSettings={() => setSettingsOpen(true)} />
    ) : route.page === "orders" ? (
      <OrdersPage info={info} />
    ) : route.page === "kb" ? (
      <KnowledgePage info={info} />
    ) : route.page === "chat" ? (
      <ChatPage info={info} initialPanel={route.panel} />
    ) : (
      <HomePage info={info} />
    );

  return (
    <>
      {error && (
        <div className="offline-banner">
          连不上后端：{error}。请确认已启动 <code>uvicorn backend.api.app:app --port 5179</code>。
        </div>
      )}
      {page}
      <Tooltip title="模型 API 设置">
        <Button
          className="llm-settings-trigger"
          type="primary"
          shape="circle"
          icon={<SettingOutlined />}
          onClick={() => setSettingsOpen(true)}
        />
      </Tooltip>
      <LlmSettingsModal
        open={settingsOpen}
        info={info}
        onClose={() => setSettingsOpen(false)}
        onSaved={refreshInfo}
      />
    </>
  );
}
