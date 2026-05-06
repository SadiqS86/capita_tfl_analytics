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

export async function fetchContextualSuggestions(
  conversationId?: string | null,
  preferredCategory?: string | null,
) {
  const params = new URLSearchParams();
  if (conversationId) params.set("conversation_id", conversationId);
  if (preferredCategory) params.set("preferred_category", preferredCategory);
  const qs = params.toString() ? `?${params.toString()}` : "";
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

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
};

export async function listConversations(limit = 50) {
  return parseJson<{ enabled: boolean; items: ConversationSummary[]; error?: string }>(
    await fetch(`/api/conversations?limit=${limit}`),
  );
}

export async function fetchConversation(conversationId: string) {
  return parseJson<{
    enabled: boolean;
    conversation_id: string | null;
    messages: StoredMessage[];
    error?: string;
  }>(await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`));
}

export async function renameConversation(conversationId: string, title: string) {
  const res = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  return parseJson<{ ok: boolean; conversation_id: string; title: string }>(res);
}

export async function deleteConversation(conversationId: string) {
  const res = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
    method: "DELETE",
  });
  return parseJson<{ ok: boolean; conversation_id: string }>(res);
}

export async function fetchDashboardCharts() {
  return parseJson<{
    compliance_trend: { month: string; compliance: number | null }[];
    breach_breakdown: { name: string; count: number }[];
    error?: string;
  }>(await fetch("/api/dashboard/charts"));
}

export type BrandingResolved = {
  app_name: string;
  app_logo_url: string;
  app_logo_url_dark: string;
};

export type BrandingAsset = {
  name: string;
  mime_type: string;
  size_bytes: number;
  updated_at: string;
};

export async function fetchBrandingSettings() {
  return parseJson<{
    lakebase_enabled: boolean;
    resolved: BrandingResolved;
    saved: Partial<BrandingResolved>;
    assets: BrandingAsset[];
  }>(await fetch("/api/branding"));
}

export async function saveBrandingSettings(payload: Partial<BrandingResolved>) {
  const res = await fetch("/api/branding", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<{
    ok: boolean;
    saved: Record<string, string>;
    cleared: string[];
    resolved: BrandingResolved;
  }>(res);
}

export async function uploadBrandingLogo(file: File, variant: "light" | "dark" = "light") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("variant", variant);
  const res = await fetch("/api/branding/logo", { method: "POST", body: fd });
  return parseJson<{
    ok: boolean;
    variant: string;
    url: string;
    size_bytes: number;
    mime_type: string;
    resolved: BrandingResolved;
  }>(res);
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
  options: {
    history?: ChatTurn[];
    signal?: AbortSignal;
    preferredCategory?: string | null;
    conversationId?: string | null;
  } = {},
): Promise<void> {
  const { history = [], signal, preferredCategory = null, conversationId = null } = options;
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({
      message,
      mode,
      history,
      preferred_category: preferredCategory,
      conversation_id: conversationId,
    }),
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
