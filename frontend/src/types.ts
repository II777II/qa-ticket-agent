/** 与后端 backend/schemas.py 一一对应的类型定义。 */

export type Role = "user" | "ai";

export interface StartEvent {
  thread_id: string;
  provider: string;
  mock: boolean;
}

export interface ToolEvent {
  phase: "call" | "result";
  name: string;
  ok?: boolean;
  message?: string;
}

/** RAG 引用：模型这句回答的依据来自哪篇文档的哪一小节 */
export interface CitationEvent {
  index: number;
  title: string;
  source: string;
  snippet?: string;
  score?: number;
}

export interface ErrorEvent {
  type: string;
  message: string;
}

export interface TicketEvent {
  at: string;
  action: string;
  note: string;
  actor: string;
}

export interface Ticket {
  id: string;
  title: string;
  description: string;
  category: string;
  priority: string;
  contact: string;
  status: string;
  source: string;
  created_at: string;
  updated_at: string;
  events: TicketEvent[];
}

export interface AgentInfo {
  status: string;
  provider: string;
  mock: boolean;
  model: string;
  tickets: number;
  checkpointer: string | null;
  retriever: string | null;
  ticket_store: string | null;
  rag_top_k: number;
  extensions: string[];
}

/** 一条工具调用在界面上的展示状态 */
export interface ToolCallView {
  key: string;
  name: string;
  phase: "call" | "result";
  ok?: boolean;
  message?: string;
}

export interface ChatMessage {
  key: string;
  role: Role;
  content: string;
  loading?: boolean;
  error?: string;
  tools: ToolCallView[];
  tickets: Ticket[];
  citations: CitationEvent[];
}

export interface StreamHandlers {
  onStart?: (event: StartEvent) => void;
  onToken?: (text: string) => void;
  onTool?: (event: ToolEvent) => void;
  onTicket?: (tickets: Ticket[]) => void;
  onCitation?: (event: CitationEvent) => void;
  onDone?: () => void;
  onError?: (event: ErrorEvent) => void;
}
