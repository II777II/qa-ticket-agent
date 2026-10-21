/** 与后端 backend/schemas.py 一一对应的类型定义。 */

export type Role = "user" | "ai";

export interface StartEvent {
  thread_id: string;
  provider: string;
  mock: boolean;
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

export interface IntentEvent {
  intent: "read" | "write" | "human";
  confidence: number;
  reason: string;
  slots: Record<string, string>;
}

export type ServiceType = "退货" | "换货" | "维修" | "退款" | "补发" | "价保" | "其他";

/** service_draft 事件：右侧业务办理面板的完整草稿。 */
export interface ServiceDraft {
  status: "draft" | "ready";
  title: string;
  description: string;
  category: string;
  priority: string;
  order_no: string;
  contact: string;
  service_type: ServiceType | "";
  slots: Record<string, string>;
  missing: string[];
  ready: boolean;
  requires_confirmation: boolean;
}

export interface ServiceConfirmPayload {
  order_no: string;
  contact: string;
  service_type: ServiceType;
  category: string;
  priority: string;
  description: string;
}

export interface ServiceConfirmResult {
  ok: boolean;
  ticket_id: string;
  status: string;
  duplicated: boolean;
  message: string;
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

export interface LlmConfigPayload {
  provider: "mock" | "deepseek" | "openai";
  api_key?: string;
  model?: string;
  base_url?: string;
}

export interface LlmConfigResult {
  provider: string;
  mock: boolean;
  model: string;
}

export interface ChatMessage {
  key: string;
  role: Role;
  content: string;
  loading?: boolean;
  error?: string;
  orders: OrderSummary[];
  citations: CitationEvent[];
  intent?: IntentEvent;
  serviceDraft?: ServiceDraft;
}

export interface StreamHandlers {
  onStart?: (event: StartEvent) => void;
  onToken?: (text: string) => void;
  onOrder?: (orders: OrderSummary[]) => void;
  onIntent?: (event: IntentEvent) => void;
  onServiceDraft?: (draft: ServiceDraft) => void;
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
}

export interface MetricsKpi {
  requests: number;
  tokens: number;
  avg_first_token_ms: number;
  avg_latency_ms: number;
  error_rate: number;
}

export interface IntentMetric {
  intent: string;
  calls: number;
  tokens: number;
  avg_latency_ms: number;
  success_rate: number;
}

export interface MetricsSummary {
  days: number;
  generated_at: string;
  kpis: MetricsKpi;
  by_intent: IntentMetric[];
}

export interface EvaluationRow {
  id: string;
  query: string;
  expected_intent: string;
  expected_tool?: string | null;
  expected_source?: string | null;
  actual_intent: string;
  actual_tool: string | null;
  retrieved_sources: string[];
  intent_ok: boolean;
  tool_ok: boolean | null;
  rag_hit: boolean | null;
}

export interface EvaluationSummary {
  generated_at: string;
  classifier: string;
  total: number;
  intent_accuracy: number;
  tool_accuracy: number;
  rag_hit_rate: number;
  rows: EvaluationRow[];
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
export type ChatPanel = "none" | "knowledge" | "orders" | "service";

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

/** order_query 工具产生的订单摘要（order 事件载荷） */
export interface OrderSummary {
  order_no: string;
  status: string;
  pay_status: string;
  customer: string | number;
  payable_amount: number;
  paid_amount: number;
  refund_amount: number;
  created_at: string;
  items: { name: string; spec?: string | null; quantity: number; price: number }[];
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
