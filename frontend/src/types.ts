export type MessageRole = "user" | "assistant";

export interface Evidence {
  doc_id?: string;
  chunk_id?: string;
  title?: string;
  source?: string;
  document_type?: string;
  version?: string;
  page?: string | number;
  content?: string;
  industry?: string;
  region?: string;
  status?: string;
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  citations?: Evidence[];
  loading?: boolean;
  error?: boolean;
}

export interface SessionSummary {
  session_id: string;
  title: string;
  message_count?: number;
  updated_at?: string;
}

export interface ChatResponse {
  session_id?: string;
  answer?: string;
  citations?: Evidence[];
  intent_type?: string;
  confidence?: number;
  retrieved_count?: number;
  route?: Record<string, unknown>;
}

export interface ProgressState {
  label: string;
  percent: number;
}
