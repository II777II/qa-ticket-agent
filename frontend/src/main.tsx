import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { XProvider } from "@ant-design/x";

import "antd/dist/reset.css";
import "./styles.css";
import App from "./App";

const container = document.getElementById("root");
if (!container) {
  throw new Error("找不到 #root 容器");
}

createRoot(container).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#0d8f6f",
          colorInfo: "#3f63f5",
          colorBgLayout: "#f6f6f7",
          colorBgContainer: "#ffffff",
          colorText: "#1c1c1f",
          colorTextSecondary: "#6a6a73",
          colorBorder: "#e6e6ea",
          borderRadius: 10,
          fontSize: 13,
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        },
        components: {
          Button: { primaryShadow: "none", defaultShadow: "none" },
          Table: { headerBg: "#fafafa" },
        },
      }}
    >
      <XProvider>
        <App />
      </XProvider>
    </ConfigProvider>
  </StrictMode>,
);
