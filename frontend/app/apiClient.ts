/**
 * API base: Vite dev server proxies /api to FastAPI; production same-origin.
 */

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!res.ok) {
    throw new Error(text || res.statusText);
  }
  return JSON.parse(text) as T;
}

export type SuggestionItem = {
  question: string;
  category: string;
  weight: number;
  ask_count?: number;
  source?: string;
};

export type KPIPayload = {
  kpi_id: string;
  label: string;
  unit: string;
  icon: string;
  value: number | string | null;
  error: string | null;
};

export async function fetchBootstrap() {
  return parseJson<{
    persona_name: string;
    persona_title: string;
    domain_summary: string;
    use_case_id: string;
    app_name?: string;
    app_logo_url?: string;
    app_logo_url_dark?: string;
  }>(await fetch("/api/bootstrap"));
}

export async function fetchSuggestions() {
  return parseJson<{ items: SuggestionItem[] }>(await fetch("/api/suggestions"));
}

export async function fetchContextualSuggestions(conversationId?: string | null) {
  const qs = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
  return parseJson<{ items: SuggestionItem[]; source?: string }>(
    await fetch(`/api/suggestions/contextual${qs}`),
  );
}

export async function fetchKpis() {
  return parseJson<KPIPayload[]>(await fetch("/api/kpis"));
}

export type StoredMessage = {
  role: "user" | "assistant";
  content: string;
  routed_to?: string | null;
  elapsed_ms?: number | null;
  created_at?: string;
};

export async function fetchCurrentConversation() {
  return parseJson<{
    enabled: boolean;
    conversation_id: string | null;
    messages: StoredMessage[];
    error?: string;
  }>(await fetch("/api/conversation/current"));
}

export async function startNewConversation() {
  return parseJson<{
    enabled: boolean;
    conversation_id: string | null;
    error?: string;
  }>(await fetch("/api/conversation/new", { method: "POST" }));
}

export async function fetchDashboardCharts() {
  return parseJson<{
    compliance_trend: { month: string; compliance: number | null }[];
    breach_breakdown: { name: string; count: number }[];
    error?: string;
  }>(await fetch("/api/dashboard/charts"));
}

export type NextBestAction = {
  action: string;
  urgency: "Immediate" | "This Week" | "Monitor";
  rationale: string;
  owner_role: string;
  contract_ref: string;
};

export async function fetchPriorityActions() {
  return parseJson<{
    actions: NextBestAction[];
    summary: Record<string, number>;
    metrics: Record<string, unknown>;
    matched_rule_count: number;
  }>(await fetch("/api/priority-actions"));
}

export async function generateNba(
  history: { role: "user" | "assistant"; content: string }[],
  answer = "",
  conversationId: string | null = null,
) {
  const res = await fetch("/api/nba", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ history, answer, conversation_id: conversationId }),
  });
  return parseJson<{
    actions: NextBestAction[];
    matched_rule_count: number;
    data_context: Record<string, unknown>;
  }>(res);
}

export type ChatTurn = { role: "user" | "assistant"; content: string };

export async function sendChatMessage(
  message: string,
  mode: "supervisor" | "genie" | "rag" = "supervisor",
  history: ChatTurn[] = [],
) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode, history }),
  });
  return parseJson<{
    answer: string;
    routed_to: string | null;
    route: string | null;
    suggested_followups: string[];
    sql?: string | null;
  }>(res);
}

export type ChatStreamEvent =
  | {
      type: "start";
      route: string;
      label: string;
      conversation_id?: string | null;
      nba_intent?: boolean;
    }
  | { type: "status"; label: string; elapsed_ms: number }
  | { type: "heartbeat"; elapsed_ms?: number; phase?: string }
  | {
      type: "answer";
      answer: string;
      routed_to: string | null;
      route: string | null;
      sql?: string | null;
      sources?: { document?: string; page?: number | null; url?: string }[];
      suggested_followups: string[];
      elapsed_ms: number;
      conversation_id?: string | null;
    }
  | { type: "suggestions"; items: SuggestionItem[] }
  | {
      type: "nba";
      actions: NextBestAction[];
      matched_rule_count: number;
      data_context: Record<string, unknown>;
    }
  | { type: "error"; message: string }
  | { type: "done" };

/**
 * Open an SSE chat stream. Calls `onEvent` for each parsed event.
 * Returns a promise that resolves when the stream ends (after `done` or error).
 *
 * Uses `fetch` + ReadableStream rather than EventSource because EventSource
 * doesn't support POST with a JSON body.
 */
export async function streamChat(
  message: string,
  mode: "supervisor" | "genie" | "rag",
  onEvent: (e: ChatStreamEvent) => void,
  options: { history?: ChatTurn[]; signal?: AbortSignal } = {},
): Promise<void> {
  const { history = [], signal } = options;
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, mode, history }),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || `Stream failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  const flush = (raw: string) => {
    let evt = "message";
    let data = "";
    for (const line of raw.split("\n")) {
      if (line.startsWith("event:")) evt = line.slice(6).trim();
      else if (line.startsWith("data:")) data += (data ? "\n" : "") + line.slice(5).trim();
    }
    if (!data) return;
    try {
      const parsed = JSON.parse(data);
      onEvent({ type: evt as ChatStreamEvent["type"], ...parsed } as ChatStreamEvent);
    } catch {
      /* ignore malformed chunk */
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (raw.trim()) flush(raw);
    }
  }
  if (buffer.trim()) flush(buffer);
}
