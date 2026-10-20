/**
 * 极简 hash 路由。
 *
 * `#/` 首页、`#/chat` 对话（可带 ?panel=knowledge|tickets）、`#/admin` 后台管理。
 * 用 hash 而不是 history 路由：前端产物由后端同源托管时，深链接需要服务端 SPA fallback，
 * hash 路由对静态托管没有任何额外要求，POC 够用。
 */

import { useEffect, useState } from "react";

import type { ChatPanel, RoutePage } from "./types";

export interface AppRoute {
  page: RoutePage;
  panel: ChatPanel;
}

export function parseRoute(hash: string): AppRoute {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const panel = new URLSearchParams(query).get("panel");
  const page: RoutePage = path.startsWith("/admin")
    ? "admin"
    : path.startsWith("/orders")
      ? "orders"
      : path.startsWith("/kb")
        ? "kb"
        : path.startsWith("/chat")
          ? "chat"
          : "home";
  return {
    page,
    panel: panel === "knowledge" || panel === "tickets" ? panel : "none",
  };
}

export function useRoute(): AppRoute {
  const [route, setRoute] = useState<AppRoute>(() => parseRoute(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

export function navigate(path: string): void {
  const next = `#${path}`;
  if (window.location.hash !== next) {
    window.location.hash = path;
  }
}
