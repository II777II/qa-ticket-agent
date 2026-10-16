import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 后端地址。POC 阶段前后端在同机：后端 127.0.0.1:5179，前端 dev server 127.0.0.1:5173。
const BACKEND = "http://127.0.0.1:5179";

export default defineConfig({
  plugins: [react()],
  server: {
    // 显式绑 IPv4：localhost 在某些 Windows 上会先解析到 ::1，导致连不上
    host: "127.0.0.1",
    port: 5173,
    // 用代理让浏览器始终同源：页面只跟 5173 说话，/chat 与 /api 由 Vite 转发给后端。
    // 这样 SSE 不受 CORS 约束，后端的 CORS 白名单只作为「绕过代理直连」的兜底。
    proxy: {
      "/chat": { target: BACKEND, changeOrigin: true },
      "/api": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
});
