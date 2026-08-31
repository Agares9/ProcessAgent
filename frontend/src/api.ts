import type { ChatMessage, SessionSummary } from "./types";

const TOKEN_KEY = "processagent_auth_token";

function headers(extra?: HeadersInit) {
  const token = localStorage.getItem(TOKEN_KEY);
  return { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: headers(init?.headers) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.detail || payload?.message || `请求失败（${response.status}）`);
  return (payload?.data ?? payload) as T;
}

export function createSessionId() { return `web-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`; }
export function createMessageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `msg-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
}

export interface ChatTask {
  task_id: string;
  session_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  progress?: { label?: string; percent?: number; stage?: string };
  result?: { answer?: string; citations?: ChatMessage["citations"]; error?: string };
  error?: string;
}

export const api = {
  listSessions: async () => { const result = await request<{ items?: SessionSummary[] }>("/api/conversations/recent?limit=20"); return result.items || []; },
  history: async (sessionId: string) => { const result = await request<{ items?: ChatMessage[] }>(`/api/chat/history/${encodeURIComponent(sessionId)}`); return result.items || []; },
  deleteSession: (sessionId: string) => request(`/api/chat/session/${encodeURIComponent(sessionId)}`, { method: "DELETE" }),
  startChat: (question: string, sessionId: string, signal?: AbortSignal) => request<{ task_id: string; session_id: string }>("/api/chat/start", { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, session_id: sessionId }) }),
  task: (taskId: string, signal?: AbortSignal) => request<ChatTask>(`/api/chat/status/${encodeURIComponent(taskId)}`, { signal }),
};
