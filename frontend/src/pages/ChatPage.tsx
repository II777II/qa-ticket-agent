import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RobotOutlined } from "@ant-design/icons";

import { searchKnowledge } from "../api/agent";
import Composer from "../components/Composer";
import KnowledgePanel from "../components/KnowledgePanel";
import MessageList from "../components/MessageList";
import OrderPanel from "../components/OrderPanel";
import Sidebar from "../components/Sidebar";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";
import { PENDING_QUESTION_KEY, PROMPTS } from "../prompts";
import { navigate } from "../router";
import type { AgentInfo, ChatPanel, Conversation, KnowledgeHit } from "../types";

export interface ChatPageProps {
  info: AgentInfo | null;
  initialPanel: ChatPanel;
}

/** 第 2/3/4 屏：会话列表 + 对话；右侧面板跟随「某一轮问答」，而不是全局缓存。 */
export default function ChatPage({ info, initialPanel }: ChatPageProps) {
  const { messages, busy, threadId, send, stop, reset, hydrate } = useChat();
  const { items, save, remove } = useConversations();

  const [input, setInput] = useState("");
  const [panel, setPanel] = useState<ChatPanel>(initialPanel);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [focusedTurnKey, setFocusedTurnKey] = useState<string | null>(null);
  const [knowledgeOverride, setKnowledgeOverride] = useState<{ key: string; hits: KnowledgeHit[] } | null>(null);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);

  const pendingSent = useRef(false);
  const restored = useRef(false);
  const streamRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPanel(initialPanel);
  }, [initialPanel]);

  const lastAiKey = useMemo(() => {
    const last = [...messages].reverse().find((message) => message.role === "ai");
    return last?.key ?? null;
  }, [messages]);

  // 新的一轮开始：面板回到「本轮」，清掉上一轮的重查结果
  useEffect(() => {
    setFocusedTurnKey(lastAiKey);
    setKnowledgeOverride(null);
  }, [lastAiKey]);

  const turn = useMemo(() => {
    if (!focusedTurnKey) return null;
    const index = messages.findIndex((message) => message.key === focusedTurnKey);
    if (index < 0) return null;
    const ai = messages[index];
    const question =
      [...messages.slice(0, index)].reverse().find((message) => message.role === "user")?.content ?? "";
    return { ai, question };
  }, [messages, focusedTurnKey]);

  // 知识结果默认直接来自这一轮收到的 citation 事件；「重查」才走一次检索接口
  const knowledgeHits: KnowledgeHit[] = (() => {
    if (knowledgeOverride && turn && knowledgeOverride.key === turn.ai.key) {
      return knowledgeOverride.hits;
    }
    return (turn?.ai.citations ?? []).map((citation) => ({
      index: citation.index,
      source: citation.source,
      title: citation.title,
      snippet: citation.snippet ?? "",
      score: citation.score ?? null,
    }));
  })();

  const refreshKnowledge = useCallback(async () => {
    if (!turn?.question) return;
    setKnowledgeLoading(true);
    try {
      setKnowledgeOverride({ key: turn.ai.key, hits: await searchKnowledge(turn.question, 5) });
    } catch {
      setKnowledgeOverride({ key: turn.ai.key, hits: [] });
    } finally {
      setKnowledgeLoading(false);
    }
  }, [turn]);

  // 首页带过来的问题：进入对话页后自动发一次
  useEffect(() => {
    if (pendingSent.current) return;
    const pending = sessionStorage.getItem(PENDING_QUESTION_KEY);
    if (!pending) return;
    pendingSent.current = true;
    sessionStorage.removeItem(PENDING_QUESTION_KEY);
    void send(pending);
  }, [send]);

  // 首次进入（不是从首页带问题跳过来）时，恢复最近一次会话
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

  // 新消息 / 恢复会话后滚到底部
  useEffect(() => {
    const element = streamRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const submit = (text: string) => {
    setInput("");
    void send(text);
  };

  const openPanel = (next: Exclude<ChatPanel, "none">) => {
    const value: ChatPanel = panel === next ? "none" : next;
    setPanel(value);
    navigate(value === "none" ? "/chat" : `/chat?panel=${value}`);
  };

  /** 点击历史消息里的引用/订单标签：把右侧面板切到那一轮 */
  const focusTurn = (messageKey: string, target: "knowledge" | "orders") => {
    setFocusedTurnKey(messageKey);
    setKnowledgeOverride(null);
    setPanel(target);
    navigate(`/chat?panel=${target}`);
  };

  const selectConversation = (conversation: Conversation) => {
    hydrate(conversation.messages, conversation.threadId);
    setActiveId(conversation.id);
  };

  const startNewChat = () => {
    reset();
    setActiveId(null);
    setFocusedTurnKey(null);
    setKnowledgeOverride(null);
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
          <button type="button" className={panel === "orders" ? "toggle active" : "toggle"} onClick={() => openPanel("orders")}>
            订单
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
                  <p>订单、物流、退换与发票问题可以问我，也可以直接查订单进度。</p>
                  <div className="prompt-row">
                    {PROMPTS.map((prompt) => (
                      <button type="button" key={prompt} className="prompt-chip" onClick={() => submit(prompt)}>
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <MessageList messages={messages} onFocusTurn={focusTurn} />
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
            <KnowledgePanel
              question={turn?.question ?? ""}
              hits={knowledgeHits}
              loading={knowledgeLoading}
              onRefresh={() => void refreshKnowledge()}
            />
          )}
          {panel === "orders" && (
            <OrderPanel orders={turn?.ai.orders ?? []} question={turn?.question ?? ""} />
          )}
        </div>
      </div>
    </div>
  );
}
