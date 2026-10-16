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
    <ConfigProvider locale={zhCN}>
      <XProvider>
        <App />
      </XProvider>
    </ConfigProvider>
  </StrictMode>,
);
