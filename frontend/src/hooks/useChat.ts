/**
 * 会话状态：消息列表 + 发送 + 流式增量。
 *
 * 一个会话 = 一个 thread_id，后端按它隔离短期记忆，所以刷新页面就是「新会话」。
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { streamChat } from "../api/agent";
import type { ChatMessage, Ticket, ToolCallView, ToolEvent } from "../types";

function newKey(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function emptyMessage(role: ChatMessage["role"], key: string): ChatMessage {
  return { key, role, content: "", tools: [], tickets: [], citations: [] };
}

/** 工具事件落成界面条目：call 新建一条，result 挂到同名的那条上 */
function mergeTool(tools: ToolCallView[], event: ToolEvent): ToolCallView[] {
  if (event.phase === "call") {
    return [...tools, { key: newKey("tool"), name: event.name, phase: "call" }];
  }
  const index = [...tools].reverse().findIndex((tool) => tool.name === event.name && tool.phase === "call");
  if (index < 0) {
    return [...tools, { key: newKey("tool"), name: event.name, phase: "result", ok: event.ok, message: event.message }];
  }
  const target = tools.length - 1 - index;
  return tools.map((tool, position) =>
    position === target ? { ...tool, phase: "result", ok: event.ok, message: event.message } : tool,
  );
}

function mergeTickets(current: Ticket[], incoming: Ticket[]): Ticket[] {
  const byId = new Map(current.map((ticket) => [ticket.id, ticket]));
  incoming.forEach((ticket) => byId.set(ticket.id, ticket));
  return [...byId.values()];
}

export interface UseChatResult {
  messages: ChatMessage[];
  busy: boolean;
  threadId: string;
  send: (text: string, onTicket?: (tickets: Ticket[]) => void) => Promise<void>;
  stop: () => void;
  reset: () => void;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [round, setRound] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);

  // 同一轮对话用同一个 thread_id；点「新会话」才换一个
  const threadId = useMemo(() => `web-${Date.now().toString(36)}-${round}`, [round]);

  const send = useCallback(
    async (text: string, onTicket?: (tickets: Ticket[]) => void) => {
      const question = text.trim();
      if (!question || busy) return;

      const userKey = newKey("user");
      const aiKey = newKey("ai");
      setMessages((prev) => [
        ...prev,
        { ...emptyMessage("user", userKey), content: question },
        { ...emptyMessage("ai", aiKey), loading: true },
      ]);
      setBusy(true);

      const controller = new AbortController();
      controllerRef.current = controller;
      const patch = (fn: (message: ChatMessage) => ChatMessage) =>
        setMessages((prev) => prev.map((message) => (message.key === aiKey ? fn(message) : message)));

      try {
        await streamChat(
          { message: question, threadId },
          {
            onToken: (token) =>
              patch((message) => ({ ...message, content: message.content + token, loading: false })),
            onTool: (event) =>
              patch((message) => ({ ...message, loading: false, tools: mergeTool(message.tools, event) })),
            onTicket: (tickets) => {
              patch((message) => ({ ...message, loading: false, tickets: mergeTickets(message.tickets, tickets) }));
              onTicket?.(tickets);
            },
            onCitation: (citation) =>
              patch((message) => ({ ...message, citations: [...message.citations, citation] })),
            onError: (error) =>
              patch((message) => ({ ...message, loading: false, error: `${error.type}: ${error.message}` })),
            onDone: () => patch((message) => ({ ...message, loading: false })),
          },
          controller.signal,
        );
      } catch (error) {
        // 主动中断不算错误，界面上只收掉 loading
        const aborted = controller.signal.aborted;
        patch((message) => ({
          ...message,
          loading: false,
          error: aborted ? undefined : error instanceof Error ? error.message : String(error),
        }));
      } finally {
        setBusy(false);
        controllerRef.current = null;
      }
    },
    [busy, threadId],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setMessages([]);
    setBusy(false);
    setRound((value) => value + 1); // 换 thread_id，后端那边就是一段全新的记忆
  }, []);

  return { messages, busy, threadId, send, stop, reset };
}
