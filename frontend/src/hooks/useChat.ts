/**
 * 会话状态：消息列表 + 发送 + 流式增量。
 *
 * 一个会话 = 一个 thread_id，后端按它隔离短期记忆，所以刷新页面就是「新会话」。
 */

import { useCallback, useRef, useState } from "react";

import { streamChat } from "../api/agent";
import type {
  ChatMessage,
  IntentEvent,
  OrderSummary,
  ServiceDraft,
} from "../types";

function newKey(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function emptyMessage(role: ChatMessage["role"], key: string): ChatMessage {
  return { key, role, content: "", orders: [], citations: [] };
}

function mergeOrders(current: OrderSummary[] = [], incoming: OrderSummary[]): OrderSummary[] {
  const byNo = new Map(current.map((order) => [order.order_no, order]));
  incoming.forEach((order) => byNo.set(order.order_no, order));
  return [...byNo.values()];
}

export interface UseChatResult {
  messages: ChatMessage[];
  busy: boolean;
  threadId: string;
  send: (text: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
  updateServiceDraft: (messageKey: string, draft: ServiceDraft) => void;
  /** 从历史会话恢复消息（thread_id 一并恢复，后端短期记忆仍按它隔离） */
  hydrate: (messages: ChatMessage[], threadId: string) => void;
}

function newThreadId(): string {
  return `web-${Date.now().toString(36)}-${Math.round(Math.random() * 1e6).toString(36)}`;
}

export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState(newThreadId);
  const controllerRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async (text: string) => {
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
            onOrder: (orders) =>
              patch((message) => ({ ...message, loading: false, orders: mergeOrders(message.orders, orders) })),
            onIntent: (intent: IntentEvent) => patch((message) => ({ ...message, intent })),
            onServiceDraft: (serviceDraft: ServiceDraft) =>
              patch((message) => ({ ...message, loading: false, serviceDraft })),
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

  const updateServiceDraft = useCallback((messageKey: string, draft: ServiceDraft) => {
    setMessages((prev) =>
      prev.map((message) =>
        message.key === messageKey ? { ...message, serviceDraft: draft } : message,
      ),
    );
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    setMessages([]);
    setBusy(false);
    setThreadId(newThreadId());
  }, []);

  const hydrate = useCallback((history: ChatMessage[], nextThreadId: string) => {
    controllerRef.current?.abort();
    setMessages(history);
    setBusy(false);
    setThreadId(nextThreadId);
  }, []);

  return { messages, busy, threadId, send, stop, reset, updateServiceDraft, hydrate };
}
