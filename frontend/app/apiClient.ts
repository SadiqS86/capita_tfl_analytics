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
  }>(await fetch("/api/bootstrap"));
}

export async function fetchSuggestions() {
  return parseJson<{ items: SuggestionItem[] }>(await fetch("/api/suggestions"));
}

export async function fetchKpis() {
  return parseJson<KPIPayload[]>(await fetch("/api/kpis"));
}

export async function fetchDashboardCharts() {
  return parseJson<{
    compliance_trend: { month: string; compliance: number | null }[];
    breach_breakdown: { name: string; count: number }[];
    error?: string;
  }>(await fetch("/api/dashboard/charts"));
}

export async function sendChatMessage(message: string, mode: "supervisor" | "genie" | "rag" = "supervisor") {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, mode }),
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
  | { type: "start"; route: string; label: string }
  | { type: "status"; label: string; elapsed_ms: number }
  | { type: "heartbeat"; elapsed_ms: number }
  | {
      type: "answer";
      answer: string;
      routed_to: string | null;
      route: string | null;
      sql?: string | null;
      sources?: { document?: string; page?: number | null; url?: string }[];
      suggested_followups: string[];
      elapsed_ms: number;
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
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ message, mode }),
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
