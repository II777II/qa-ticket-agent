/**
 * API 层：界面只跟这里打交道，不直接写 fetch。
 *
 * 之所以单独封一层：以后换 useStream / WebSocket、或者前端独立部署到别的域名，
 * 只改这个文件，页面组件不用动。
 */

import type { AgentInfo, StreamHandlers, Ticket } from "../types";

/** 默认空字符串 = 同源（走 Vite 代理）。需要直连后端时设 VITE_API_BASE=http://127.0.0.1:5179 */
const API_BASE: string = import.meta.env.VITE_API_BASE ?? "";

export interface ChatRequestPayload {
  message: string;
  threadId: string;
  userId?: string;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} 失败：${response.status} ${text.slice(0, 120)}`);
  }
  return (await response.json()) as T;
}

export function getAgentInfo(): Promise<AgentInfo> {
  return requestJson<AgentInfo>("/api/agent-info");
}

export function listTickets(): Promise<Ticket[]> {
  return requestJson<Ticket[]>("/api/tickets?limit=50");
}

export function getTicket(ticketId: string): Promise<Ticket> {
  return requestJson<Ticket>(`/api/tickets/${encodeURIComponent(ticketId)}`);
}

/** 把一段 SSE 报文拆成事件名与 JSON 载荷 */
function parseSseBlock(block: string): { event: string; data: string } {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  return { event, data: dataLines.join("\n") };
}

/**
 * 流式对话。用 fetch + ReadableStream 手动解析 SSE——
 * EventSource 只支持 GET 且不能带请求体，而 /chat 是 POST + JSON。
 */
export async function streamChat(
  payload: ChatRequestPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: payload.message,
      thread_id: payload.threadId,
      user_id: payload.userId,
    }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`对话接口返回 ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE 以空行分隔事件；分片到达时可能只到半个事件，留在 buffer 里等下一片
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
      if (!block.trim()) continue;

      const { event, data } = parseSseBlock(block);
      let json: unknown = {};
      try {
        json = data ? JSON.parse(data) : {};
      } catch {
        json = { raw: data };
      }
      dispatch(event, json as Record<string, unknown>, handlers);
    }
  }
}

function dispatch(
  event: string,
  payload: Record<string, unknown>,
  handlers: StreamHandlers,
): void {
  const optionalText = (value: unknown): string | undefined =>
    value === undefined || value === null ? undefined : String(value);

  switch (event) {
    case "start":
      handlers.onStart?.({
        thread_id: String(payload.thread_id ?? ""),
        provider: String(payload.provider ?? ""),
        mock: Boolean(payload.mock),
      });
      break;
    case "token":
      handlers.onToken?.(String(payload.text ?? ""));
      break;
    case "tool":
      handlers.onTool?.({
        phase: payload.phase === "result" ? "result" : "call",
        name: String(payload.name ?? ""),
        ok: payload.ok === undefined ? undefined : Boolean(payload.ok),
        message: optionalText(payload.message),
      });
      break;
    case "ticket":
      handlers.onTicket?.((payload.tickets ?? []) as Ticket[]);
      break;
    case "citation":
      handlers.onCitation?.({
        title: String(payload.title ?? ""),
        source: String(payload.source ?? ""),
        snippet: optionalText(payload.snippet),
      });
      break;
    case "done":
      handlers.onDone?.();
      break;
    case "error":
      handlers.onError?.({
        type: String(payload.type ?? "Error"),
        message: String(payload.message ?? "未知错误"),
      });
      break;
    default:
      break;
  }
}
