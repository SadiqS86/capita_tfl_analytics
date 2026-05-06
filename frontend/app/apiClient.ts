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
