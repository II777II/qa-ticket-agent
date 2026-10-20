/**
 * 会话历史（浏览器 localStorage）。
 *
 * POC 不做服务端会话列表：消息与 thread_id 都在本地，刷新/重开浏览器还在，换设备不同步。
 * 后端仍按 thread_id 维护短期记忆，所以恢复会话时上下文仍在同一个 thread 上。
 */

import { useCallback, useState } from "react";

import type { ChatMessage, Conversation } from "../types";

const STORAGE_KEY = "qa-ticket.conversations.v1";
const MAX_CONVERSATIONS = 30;
const MAX_MESSAGES = 60;

function read(): Conversation[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Conversation[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function write(items: Conversation[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* 隐私模式或配额满：忽略，不影响对话 */
  }
}

export function makeTitle(messages: ChatMessage[]): string {
  const first = messages.find((message) => message.role === "user");
  const text = first?.content?.trim() ?? "";
  return text ? (text.length > 22 ? `${text.slice(0, 22)}…` : text) : "新对话";
}

export interface UseConversationsResult {
  items: Conversation[];
  save: (threadId: string, messages: ChatMessage[]) => void;
  remove: (id: string) => void;
}

export function useConversations(): UseConversationsResult {
  const [items, setItems] = useState<Conversation[]>(read);

  const save = useCallback((threadId: string, messages: ChatMessage[]) => {
    if (!messages.length) return;
    const conversation: Conversation = {
      id: threadId,
      threadId,
      title: makeTitle(messages),
      updatedAt: Date.now(),
      messages: messages.slice(-MAX_MESSAGES),
    };
    setItems((prev) => {
      const next = [conversation, ...prev.filter((item) => item.id !== threadId)].slice(0, MAX_CONVERSATIONS);
      write(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setItems((prev) => {
      const next = prev.filter((item) => item.id !== id);
      write(next);
      return next;
    });
  }, []);

  return { items, save, remove };
}
