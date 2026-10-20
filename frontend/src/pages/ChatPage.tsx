import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RobotOutlined } from "@ant-design/icons";

import { listTickets, searchKnowledge } from "../api/agent";
import Composer from "../components/Composer";
import KnowledgePanel from "../components/KnowledgePanel";
import MessageList from "../components/MessageList";
import Sidebar from "../components/Sidebar";
import TicketPanel from "../components/TicketPanel";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";
import { PENDING_QUESTION_KEY, PROMPTS } from "../prompts";
import { navigate } from "../router";
import type { AgentInfo, ChatPanel, Conversation, KnowledgeHit, Ticket } from "../types";

export interface ChatPageProps {
  info: AgentInfo | null;
  initialPanel: ChatPanel;
}

/** 第 2/3/4 屏：会话列表 + 对话，可按需在右侧挂知识库或工单面板。 */
export default function ChatPage({ info, initialPanel }: ChatPageProps) {
  const { messages, busy, threadId, send, stop, reset, hydrate } = useChat();
  const { items, save, remove } = useConversations();

  const [input, setInput] = useState("");
  const [panel, setPanel] = useState<ChatPanel>(initialPanel);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hits, setHits] = useState<KnowledgeHit[]>([]);
  const [hitsLoading, setHitsLoading] = useState(false);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const pendingSent = useRef(false);
  const restored = useRef(false);
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPanel(initialPanel);
  }, [initialPanel]);

  const refreshTickets = useCallback(async () => {
    setTicketsLoading(true);
    try {
      setTickets(await listTickets());
    } catch {
      setTickets([]);
    } finally {
      setTicketsLoading(false);
    }
  }, []);

  const lastQuestion = useMemo(() => {
    const question = [...messages].reverse().find((message) => message.role === "user");
    return question?.content ?? "";
  }, [messages]);

  const refreshHits = useCallback(async () => {
    if (!lastQuestion) {
      setHits([]);
      return;
    }
    setHitsLoading(true);
    try {
      setHits(await searchKnowledge(lastQuestion, 5));
    } catch {
      setHits([]);
    } finally {
      setHitsLoading(false);
    }
  }, [lastQuestion]);

  // 首页带过来的问题：进入对话页后自动发一次
  useEffect(() => {
    if (pendingSent.current) return;
    const pending = sessionStorage.getItem(PENDING_QUESTION_KEY);
    if (!pending) return;
    pendingSent.current = true;
    sessionStorage.removeItem(PENDING_QUESTION_KEY);
    void send(pending, () => void refreshTickets());
  }, [send, refreshTickets]);

  // 首次进入（不是从首页带着问题跳过来）时，恢复最近一次会话，像常见对话产品一样
  useEffect(() => {
    if (restored.current) return;
    restored.current = true;
    if (sessionStorage.getItem(PENDING_QUESTION_KEY)) return;
    const latest = items[0];
    if (!latest) return;
    hydrate(latest.messages, latest.threadId);
    setActiveId(latest.id);
  }, [items, hydrate]);

  // 会话持久化（防抖，避免每个 token 都写 localStorage）
  useEffect(() => {
    if (!messages.length) return;
    const timer = window.setTimeout(() => {
      save(threadId, messages);
      setActiveId(threadId);
    }, 400);
    return () => window.clearTimeout(timer);
  }, [messages, threadId, save]);

  useEffect(() => {
    if (panel === "knowledge") void refreshHits();
  }, [panel, refreshHits]);

  useEffect(() => {
    if (panel === "tickets" || messages.length > 0) void refreshTickets();
  }, [panel, messages.length, refreshTickets]);

  // 新消息 / 恢复会话后滚到底部（参考页的行为：看到最新一轮）
  useEffect(() => {
    const element = streamRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const submit = (text: string) => {
    setInput("");
    void send(text, () => void refreshTickets());
  };

  const openPanel = (next: Exclude<ChatPanel, "none">) => {
    const value: ChatPanel = panel === next ? "none" : next;
    setPanel(value);
    navigate(value === "none" ? "/chat" : `/chat?panel=${value}`);
  };

  const selectConversation = (conversation: Conversation) => {
    hydrate(conversation.messages, conversation.threadId);
    setActiveId(conversation.id);
    setSelectedTicketId(null);
  };

  const startNewChat = () => {
    reset();
    setActiveId(null);
    setSelectedTicketId(null);
    setHits([]);
  };

  const title = items.find((item) => item.id === activeId)?.title ?? (messages.length ? "会话进行中" : "新对话");

  return (
    <div className="shell">
      <Sidebar
        conversations={items}
        activeId={activeId}
        onSelect={selectConversation}
        onNew={startNewChat}
        onDelete={(id) => {
          remove(id);
          if (id === activeId) startNewChat();
        }}
        provider={info?.provider ?? "Agent"}
        mock={info?.mock ?? false}
        sha={info?.git_sha}
        date={info?.git_date}
      />

      <div className="main">
        <header className="topbar">
          <span className="topbar-title">{title}</span>
          <span className="pill">{info?.mock ? "演示模式" : info?.provider ?? "Agent"}</span>
          <span className="pill">记忆 · {info?.checkpointer ?? "未接入"}</span>
          <span className="spacer" />
          <button type="button" className={panel === "knowledge" ? "toggle active" : "toggle"} onClick={() => openPanel("knowledge")}>
            知识库
          </button>
          <button type="button" className={panel === "tickets" ? "toggle active" : "toggle"} onClick={() => openPanel("tickets")}>
            工单
          </button>
        </header>

        <div className="workspace">
          <section className="chat-col">
            <div className="stream" ref={streamRef}>
              {messages.length === 0 ? (
                <div className="chat-empty">
                  <span className="brand-mark big">
                    <RobotOutlined />
                  </span>
                  <h2>有什么可以帮您？</h2>
                  <p>知识库解决不了、或你明确要求时，我会帮你建工单。</p>
                  <div className="prompt-row">
                    {PROMPTS.map((prompt) => (
                      <button type="button" key={prompt} className="prompt-chip" onClick={() => submit(prompt)}>
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <MessageList messages={messages} onOpenTicket={(ticketId) => setSelectedTicketId(ticketId)} />
              )}
            </div>
            <div className="composer-wrap">
              <Composer
                value={input}
                onChange={setInput}
                onSubmit={submit}
                onStop={stop}
                busy={busy}
                model={info?.model || info?.provider || "Agent"}
                placeholder="描述你遇到的问题，Enter 发送"
              />
            </div>
          </section>

          {panel === "knowledge" && (
            <KnowledgePanel question={lastQuestion} hits={hits} loading={hitsLoading} onRefresh={() => void refreshHits()} />
          )}
          {panel === "tickets" && (
            <TicketPanel
              tickets={tickets}
              loading={ticketsLoading}
              selectedId={selectedTicketId}
              onSelect={setSelectedTicketId}
              onRefresh={() => void refreshTickets()}
            />
          )}
        </div>
      </div>
    </div>
  );
}
