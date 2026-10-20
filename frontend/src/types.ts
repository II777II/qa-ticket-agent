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
  git_sha: string;
  git_date: string;
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

/** 知识库检索面板的一条命中 */
export interface KnowledgeHit {
  index: number;
  source: string;
  title: string;
  snippet: string;
  score?: number | null;
  coverage?: number | null;
}

export interface MetricsKpi {
  requests: number;
  tokens: number;
  avg_first_token_ms: number;
  p95_first_token_ms: number;
  avg_latency_ms: number;
  error_rate: number;
}

export interface DayMetric {
  date: string;
  requests: number;
  tokens: number;
  avg_latency_ms: number;
}

export interface ModelMetric {
  model: string;
  calls: number;
  tokens: number;
  avg_latency_ms: number;
  success_rate: number;
}

export interface MetricsSummary {
  days: number;
  generated_at: string;
  kpis: MetricsKpi;
  by_day: DayMetric[];
  by_model: ModelMetric[];
}

/** 本地保存的一次会话（localStorage） */
export interface Conversation {
  id: string;
  threadId: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
}

export type RoutePage = "home" | "chat" | "orders" | "kb" | "admin";
export type ChatPanel = "none" | "knowledge" | "tickets";

/** ---------------- 电商订单 ---------------- */
export interface OrderItem {
  product_name: string;
  sku_spec?: string | null;
  product_img?: string | null;
  price: number;
  quantity: number;
  item_amount: number;
  discount_amount?: number;
  payable_amount: number;
}

export interface OrderAddress {
  receiver_name: string;
  receiver_phone: string;
  province: string;
  city: string;
  district: string;
  detail_address: string;
}

export interface OrderPayment {
  payment_no: string;
  channel_name?: string | null;
  amount: number;
  status: number;
  paid_at?: string | null;
}

export interface OrderRefund {
  refund_no: string;
  amount: number;
  reason?: string | null;
  status: number;
  refunded_at?: string | null;
}

export interface OrderStatusLog {
  from_status: number;
  to_status: number;
  remark: string;
  created_at: string;
}

export interface OrderRecord {
  id: number;
  order_no: string;
  user_id: number;
  order_status: number;
  pay_status: number;
  source: number;
  total_amount: number;
  discount_amount: number;
  freight_amount: number;
  payable_amount: number;
  paid_amount: number;
  refund_amount: number;
  remark: string;
  created_at: string;
  updated_at: string;
  pay_time?: string | null;
  finish_time?: string | null;
  cancel_time?: string | null;
  user?: { id: number; name: string; phone: string } | null;
  items: OrderItem[];
  address?: OrderAddress | null;
  payments: OrderPayment[];
  refunds: OrderRefund[];
  status_logs: OrderStatusLog[];
  status_label: string;
  pay_status_label: string;
  source_label: string;
}

/** ---------------- 知识库目录 ---------------- */
export interface KnowledgeArticle {
  id: number;
  article_no: string;
  title: string;
  summary: string;
  category_id: number;
  category_code: string;
  category_name: string;
  article_type: number;
  tags: string[];
  is_top: number;
  publish_time?: string | null;
  updated_at?: string | null;
  url: string;
  view_count: number;
}

export interface KnowledgeCategory {
  id: number;
  name: string;
  code: string;
  sort_no: number;
}
