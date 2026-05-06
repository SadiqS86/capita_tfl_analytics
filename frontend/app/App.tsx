import { useCallback, useEffect, useMemo, useState } from "react";
import { Send, Activity, Lightbulb, X, Moon, Sun, type LucideIcon } from "lucide-react";
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import * as LucideIcons from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  fetchBootstrap,
  fetchDashboardCharts,
  fetchKpis,
  fetchSuggestions,
  streamChat,
  type ChatStreamEvent,
  type KPIPayload,
  type SuggestionItem,
} from "./apiClient";

const CAPITA_COLORS = {
  navyBlue: "#003B5C",
  navyBlueDark: "#002A42",
  navyBlueLight: "#0D5A85",
  cyan: "#00A3E0",
  purple: "#9B62C3",
  green: "#C5D201",
  teal: "#10D6A6",
};

const CHART_FILLS = ["#00A3E0", "#C5D201", "#9B62C3", "#10D6A6", "#003B5C"];

function iconByName(name: string): LucideIcon {
  const I = (LucideIcons as unknown as Record<string, LucideIcon>)[name];
  return I || Activity;
}

/**
 * Try to parse the first GitHub-flavored markdown table from text.
 * Returns header + rows when at least one numeric column exists, else null.
 */
type ParsedTable = { headers: string[]; rows: (string | number)[][]; numericCol: number | null };

function parseFirstMarkdownTable(text: string): ParsedTable | null {
  const lines = text.split("\n");
  let headerIdx = -1;
  for (let i = 0; i < lines.length - 1; i++) {
    const t = lines[i].trim();
    const sep = lines[i + 1].trim();
    if (t.startsWith("|") && /^\|?\s*:?-{2,}.*\|/.test(sep)) {
      headerIdx = i;
      break;
    }
  }
  if (headerIdx === -1) return null;

  const headers = lines[headerIdx]
    .split("|")
    .map((s) => s.trim())
    .filter((s, i, arr) => !(i === 0 && s === "") && !(i === arr.length - 1 && s === ""));

  const rows: (string | number)[][] = [];
  for (let j = headerIdx + 2; j < lines.length; j++) {
    const r = lines[j].trim();
    if (!r.startsWith("|")) break;
    const cells = r
      .split("|")
      .map((s) => s.trim())
      .filter((s, i, arr) => !(i === 0 && s === "") && !(i === arr.length - 1 && s === ""));
    if (cells.length === 0) break;
    rows.push(
      cells.map((c) => {
        const n = Number(c.replace(/[%,£$,\s]/g, ""));
        return Number.isFinite(n) && c.match(/[0-9]/) ? n : c;
      }),
    );
  }
  if (rows.length === 0) return null;

  let numericCol: number | null = null;
  for (let c = 1; c < headers.length; c++) {
    if (rows.every((r) => typeof r[c] === "number")) {
      numericCol = c;
      break;
    }
  }
  return { headers, rows, numericCol };
}

function formatKpiValue(k: KPIPayload): string {
  if (k.error) return "—";
  if (k.value === null || k.value === undefined) return "—";
  if (k.unit === "%") return `${Number(k.value).toFixed(1)}%`;
  if (k.unit === "count" || k.unit === "points" || k.unit === "days")
    return String(Math.round(Number(k.value)));
  return String(k.value);
}

function AssistantBubbleContent({
  text,
  typing,
  darkMode,
}: {
  text: string;
  typing: boolean;
  darkMode: boolean;
}) {
  const parsed = useMemo(() => parseFirstMarkdownTable(text), [text]);

  const proseClasses = [
    "text-sm leading-relaxed space-y-2",
    "[&_strong]:font-semibold",
    "[&_h1]:text-base [&_h1]:font-semibold [&_h1]:mt-2 [&_h1]:mb-1",
    "[&_h2]:text-base [&_h2]:font-semibold [&_h2]:mt-2 [&_h2]:mb-1",
    "[&_h3]:text-sm [&_h3]:font-semibold [&_h3]:mt-2 [&_h3]:mb-1",
    "[&_p]:my-1",
    "[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-1",
    "[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-1",
    "[&_li]:my-0.5",
    "[&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs",
    darkMode ? "[&_code]:bg-slate-700/60" : "[&_code]:bg-slate-100",
    "[&_table]:w-full [&_table]:text-xs [&_table]:border-collapse [&_table]:my-2",
    "[&_th]:text-left [&_th]:font-semibold [&_th]:px-2 [&_th]:py-1",
    "[&_td]:px-2 [&_td]:py-1 [&_td]:border-t",
    darkMode ? "[&_th]:bg-slate-700/50 [&_td]:border-slate-600" : "[&_th]:bg-slate-50 [&_td]:border-slate-200",
    "[&_a]:underline",
  ].join(" ");

  const showChart = !typing && parsed && parsed.numericCol !== null;
  const chartData =
    showChart && parsed
      ? parsed.rows.map((r) => ({
          name: String(r[0]),
          value: Number(r[parsed.numericCol as number]),
        }))
      : [];

  return (
    <div className={proseClasses}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || ""}</ReactMarkdown>
      {typing && (
        <span
          className="inline-block w-[2px] h-4 align-middle ml-0.5 animate-pulse"
          style={{ backgroundColor: CAPITA_COLORS.cyan }}
        />
      )}
      {showChart && parsed && (
        <div
          className="mt-3 p-3 rounded-lg border"
          style={{
            backgroundColor: darkMode ? "rgba(15,23,42,0.6)" : "rgba(255,255,255,0.7)",
            borderColor: darkMode ? "rgba(0,163,224,0.3)" : "rgba(0,163,224,0.25)",
          }}
        >
          <div className={`text-xs font-medium mb-2 ${darkMode ? "text-slate-300" : "text-slate-600"}`}>
            {parsed.headers[parsed.numericCol as number]} by {parsed.headers[0]}
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke={darkMode ? "#475569" : "#e2e8f0"} />
              <XAxis dataKey="name" stroke="#94a3b8" style={{ fontSize: 10 }} />
              <YAxis stroke="#94a3b8" style={{ fontSize: 10 }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: darkMode ? "#1e293b" : "#fff",
                  border: darkMode ? "1px solid #475569" : "1px solid #e2e8f0",
                  fontSize: 12,
                }}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {chartData.map((_, i) => (
                  <Cell key={i} fill={CHART_FILLS[i % CHART_FILLS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"chat" | "dashboard">("chat");
  const [darkMode, setDarkMode] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showNextActions, setShowNextActions] = useState(false);

  const [personaName, setPersonaName] = useState("Adam");
  const [personaTitle, setPersonaTitle] = useState("");

  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  type ChatMessage = {
    role: "user" | "assistant";
    content: string;
    followups?: string[];
    routed?: string;
    elapsedMs?: number;
    typing?: boolean;
    fullContent?: string;
  };
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [statusLabel, setStatusLabel] = useState<string | null>(null);
  const [statusElapsedMs, setStatusElapsedMs] = useState<number>(0);

  // Typewriter animation: progressively reveal content of any message with `typing: true`.
  useEffect(() => {
    const target = messages.findIndex((m) => m.role === "assistant" && m.typing);
    if (target === -1) return;
    const m = messages[target];
    const full = m.fullContent ?? m.content;
    if (m.content.length >= full.length) {
      setMessages((curr) =>
        curr.map((mm, i) => (i === target ? { ...mm, typing: false, content: full } : mm)),
      );
      return;
    }
    const remaining = full.length - m.content.length;
    const step = Math.max(1, Math.min(8, Math.ceil(remaining / 60)));
    const id = setTimeout(() => {
      setMessages((curr) =>
        curr.map((mm, i) =>
          i === target ? { ...mm, content: full.slice(0, mm.content.length + step) } : mm,
        ),
      );
    }, 16);
    return () => clearTimeout(id);
  }, [messages]);

  const [kpis, setKpis] = useState<KPIPayload[]>([]);
  const [complianceSeries, setComplianceSeries] = useState<{ month: string; compliance: number }[]>([]);
  const [breachSeries, setBreachSeries] = useState<{ name: string; count: number }[]>([]);

  useEffect(() => {
    fetchBootstrap()
      .then((b) => {
        setPersonaName(b.persona_name.split(" ")[0] || "Adam");
        setPersonaTitle(b.persona_title);
      })
      .catch(() => {});

    fetchSuggestions()
      .then((r) => setSuggestions(r.items || []))
      .catch(() => setSuggestions([]));
  }, []);

  useEffect(() => {
    if (activeTab !== "dashboard") return;
    fetchKpis()
      .then(setKpis)
      .catch(() => setKpis([]));
    fetchDashboardCharts()
      .then((c) => {
        const t = c.compliance_trend || [];
        setComplianceSeries(
          t
            .filter((x) => x.compliance != null)
            .map((x) => ({ month: String(x.month), compliance: x.compliance as number })),
        );
        setBreachSeries(c.breach_breakdown || []);
      })
      .catch(() => {
        setComplianceSeries([]);
        setBreachSeries([]);
      });
  }, [activeTab]);

  const submitMessage = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || sending) return;
      setChatInput("");
      setSending(true);
      setStatusLabel("Routing question…");
      setStatusElapsedMs(0);
      setMessages((m) => [...m, { role: "user", content: text }]);

      try {
        await streamChat(text, "supervisor", (e: ChatStreamEvent) => {
          if (e.type === "start") {
            setStatusLabel(`Routing to ${e.label}`);
          } else if (e.type === "status") {
            setStatusLabel(e.label);
            setStatusElapsedMs(e.elapsed_ms);
          } else if (e.type === "heartbeat") {
            setStatusElapsedMs(e.elapsed_ms);
          } else if (e.type === "answer") {
            setMessages((m) => [
              ...m,
              {
                role: "assistant",
                content: "",
                fullContent: e.answer,
                typing: true,
                followups: e.suggested_followups,
                routed: e.routed_to || e.route || undefined,
                elapsedMs: e.elapsed_ms,
              },
            ]);
          } else if (e.type === "error") {
            setMessages((m) => [
              ...m,
              { role: "assistant", content: `Sorry — ${e.message}` },
            ]);
          }
        });
      } catch (err) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Sorry — could not reach the API (${String(err)}).` },
        ]);
      } finally {
        setSending(false);
        setStatusLabel(null);
        setStatusElapsedMs(0);
      }
    },
    [sending],
  );

  const onSend = useCallback(() => {
    void submitMessage(chatInput);
  }, [chatInput, submitMessage]);

  const refreshSuggestions = () => {
    fetchSuggestions()
      .then((r) => setSuggestions(r.items || []))
      .catch(() => {});
  };

  const chipColor = (i: number) =>
    [CAPITA_COLORS.navyBlue, CAPITA_COLORS.cyan, CAPITA_COLORS.teal, CAPITA_COLORS.purple, CAPITA_COLORS.green][
      i % 5
    ];

  const priorityActions = [
    {
      id: 1,
      title: "Review underperforming suppliers",
      description: "Two suppliers scored below 70 for 3 consecutive months",
      urgency: "high" as const,
      impact: "Contract penalties may apply if not addressed by end of quarter",
      dueDate: "Next 7 days",
    },
    {
      id: 2,
      title: "Address SLA compliance drop",
      description: "Overall compliance decreased from 93% to 88% in last 3 months",
      urgency: "high" as const,
      impact: "Trend indicates potential breach of contractual obligations",
      dueDate: "Next 14 days",
    },
  ];

  const starterChips = suggestions.slice(0, 5);
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const followupChips = lastAssistant?.followups?.length ? lastAssistant.followups : [];

  return (
    <div className={`size-full flex flex-col min-h-0 ${darkMode ? "bg-slate-900" : "bg-slate-50"}`}>
      <div
        className={`border-b px-6 shrink-0 ${darkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex gap-6">
            <button
              type="button"
              onClick={() => setActiveTab("dashboard")}
              className={`px-4 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "dashboard" ? "" : darkMode ? "border-transparent text-slate-400" : "border-transparent text-slate-600"
              }`}
              style={
                activeTab === "dashboard"
                  ? { borderColor: CAPITA_COLORS.navyBlue, color: CAPITA_COLORS.navyBlue }
                  : undefined
              }
            >
              Dashboard
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("chat")}
              className={`px-4 py-4 text-sm font-medium border-b-2 transition-colors ${
                activeTab === "chat" ? "" : darkMode ? "border-transparent text-slate-400" : "border-transparent text-slate-600"
              }`}
              style={
                activeTab === "chat" ? { borderColor: CAPITA_COLORS.navyBlue, color: CAPITA_COLORS.navyBlue } : undefined
              }
            >
              Chat
            </button>
          </div>
          <button
            type="button"
            onClick={() => setDarkMode(!darkMode)}
            className={`p-2 rounded-lg transition-colors ${
              darkMode ? "bg-slate-700 text-yellow-400 hover:bg-slate-600" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {activeTab === "chat" ? (
        <div className="flex-1 flex flex-col min-h-0 relative">
          <div className={`px-6 py-4 shrink-0 ${darkMode ? "bg-slate-800/80" : "bg-white border-b border-slate-200"}`}>
            <div className={`text-sm mb-1 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
              {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" })}
            </div>
            <h2 className={`text-2xl font-semibold mb-1 ${darkMode ? "text-white" : "text-slate-900"}`}>
              Good morning, {personaName}
            </h2>
            <p className={`text-sm ${darkMode ? "text-slate-400" : "text-slate-600"}`}>
              {personaTitle || "TfL contract intelligence"} — click a suggestion or ask anything.
            </p>
          </div>

          <div className="flex-1 overflow-auto p-6 space-y-4 min-h-0">
            {messages.length === 0 && (
              <p className={`text-sm ${darkMode ? "text-slate-400" : "text-slate-600"}`}>
                Start from a suggested question below, or type your own.
              </p>
            )}
            {messages.map((msg, idx) => {
              const isUser = msg.role === "user";
              const assistantBg = darkMode
                ? "rgba(0,163,224,0.08)"
                : "rgba(0,163,224,0.06)";
              const assistantBorder = darkMode
                ? "rgba(0,163,224,0.30)"
                : "rgba(0,163,224,0.25)";
              return (
                <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                  <div
                    className="max-w-3xl rounded-lg p-4 whitespace-pre-wrap border"
                    style={
                      isUser
                        ? {
                            backgroundColor: CAPITA_COLORS.navyBlue,
                            borderColor: CAPITA_COLORS.navyBlue,
                            color: "white",
                          }
                        : {
                            backgroundColor: assistantBg,
                            borderColor: assistantBorder,
                            color: darkMode ? "#e2e8f0" : "#0f172a",
                          }
                    }
                  >
                    {isUser ? (
                      <p className="text-sm text-white whitespace-pre-wrap">{msg.content}</p>
                    ) : (
                      <AssistantBubbleContent
                        text={msg.content}
                        typing={!!msg.typing}
                        darkMode={darkMode}
                      />
                    )}
                    {msg.role === "assistant" && !msg.typing && (msg.routed || msg.elapsedMs != null) && (
                      <p className={`text-xs mt-2 ${darkMode ? "text-slate-500" : "text-slate-500"}`}>
                        {msg.routed ? `Routed: ${msg.routed}` : ""}
                        {msg.routed && msg.elapsedMs != null ? " · " : ""}
                        {msg.elapsedMs != null ? `${(msg.elapsedMs / 1000).toFixed(1)}s` : ""}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
            {sending && (
              <div className="flex justify-start">
                <div
                  className={`max-w-3xl rounded-lg px-4 py-3 flex items-center gap-3 ${
                    darkMode ? "bg-slate-800 border border-slate-700" : "bg-white border border-slate-200"
                  }`}
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full animate-pulse"
                    style={{ backgroundColor: CAPITA_COLORS.cyan }}
                  />
                  <span className={`text-sm ${darkMode ? "text-slate-200" : "text-slate-700"}`}>
                    {statusLabel || "Thinking…"}
                  </span>
                  {statusElapsedMs > 1000 && (
                    <span className={`text-xs ${darkMode ? "text-slate-500" : "text-slate-500"}`}>
                      {(statusElapsedMs / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className={`border-t p-4 shrink-0 space-y-3 ${darkMode ? "border-slate-700 bg-slate-800" : "border-slate-200 bg-white"}`}>
            <div className="flex flex-wrap gap-2">
              {(followupChips.length ? followupChips : starterChips.map((s) => s.question)).map((q, i) => (
                <button
                  type="button"
                  key={`${q}-${i}`}
                  onClick={() => void submitMessage(q)}
                  className={`text-left text-xs px-3 py-2 rounded-full border max-w-full transition-colors ${
                    darkMode ? "border-slate-600 text-slate-200 hover:bg-slate-700" : "border-slate-200 text-slate-700 hover:bg-slate-50"
                  }`}
                  style={{ borderColor: chipColor(i) }}
                >
                  {q}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={refreshSuggestions}
              className={`text-xs underline ${darkMode ? "text-slate-500" : "text-slate-600"}`}
            >
              Refresh suggestions
            </button>

            <div className="flex gap-3">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && onSend()}
                placeholder="Ask about SLAs, obligations, suppliers, or contract terms..."
                className={`flex-1 px-4 py-3 border rounded-lg text-sm focus:outline-none focus:ring-2 ${
                  darkMode ? "bg-slate-700 border-slate-600 text-white placeholder-slate-400" : "bg-slate-50 border-slate-200 text-slate-900"
                }`}
                style={{ "--tw-ring-color": CAPITA_COLORS.navyBlue } as React.CSSProperties}
              />
              <button
                type="button"
                onClick={onSend}
                disabled={sending}
                className="px-6 py-3 text-white rounded-lg flex items-center gap-2 disabled:opacity-50"
                style={{ backgroundColor: CAPITA_COLORS.navyBlue }}
              >
                <Send className="w-4 h-4" />
                Send
              </button>
            </div>

            <button
              type="button"
              onClick={() => setShowNextActions(true)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg transition-colors border"
              style={{
                backgroundColor: `${CAPITA_COLORS.green}${darkMode ? "33" : "1A"}`,
                color: darkMode ? CAPITA_COLORS.green : "#8B9600",
                borderColor: `${CAPITA_COLORS.green}66`,
              }}
            >
              <Lightbulb className="w-4 h-4" />
              <span className="text-sm font-medium">Suggest next best actions (preview)</span>
            </button>
          </div>

          {showNextActions && (
            <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6">
              <div className={`rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] overflow-auto ${darkMode ? "bg-slate-800" : "bg-white"}`}>
                <div className={`sticky top-0 border-b p-6 flex justify-between ${darkMode ? "border-slate-700" : "border-slate-200"}`}>
                  <h3 className={`text-xl font-semibold ${darkMode ? "text-white" : "text-slate-900"}`}>Recommended Next Actions</h3>
                  <button type="button" onClick={() => setShowNextActions(false)} className="text-slate-400 hover:text-slate-600">
                    <X className="w-5 h-5" />
                  </button>
                </div>
                <div className="p-6 space-y-4">
                  {priorityActions.map((action) => (
                    <div key={action.id} className={`border rounded-lg p-4 ${darkMode ? "border-slate-700" : "border-slate-200"}`}>
                      <h4 className={`font-semibold ${darkMode ? "text-white" : "text-slate-900"}`}>{action.title}</h4>
                      <p className={`text-sm mt-2 ${darkMode ? "text-slate-300" : "text-slate-700"}`}>{action.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-8">
          <div className="mb-8">
            <h2 className={`text-3xl font-semibold mb-2 ${darkMode ? "text-white" : "text-slate-900"}`}>TfL Contract Overview</h2>
            <p className={`text-sm ${darkMode ? "text-slate-400" : "text-slate-600"}`}>Live KPIs from Unity Catalog</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 mb-8">
            {kpis.map((kpi) => {
              const Icon = iconByName(kpi.icon);
              return (
                <div
                  key={kpi.kpi_id}
                  className={`relative border-2 rounded-xl p-6 ${darkMode ? "bg-slate-800 border-slate-600" : "bg-white border-slate-200"}`}
                >
                  <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: CAPITA_COLORS.cyan }} />
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-12 h-12 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${CAPITA_COLORS.cyan}22` }}>
                      <Icon className="w-6 h-6" style={{ color: CAPITA_COLORS.cyan }} />
                    </div>
                  </div>
                  <div className={`text-3xl font-bold mb-2 ${darkMode ? "text-white" : "text-slate-900"}`}>{formatKpiValue(kpi)}</div>
                  <div className={`text-sm font-medium ${darkMode ? "text-slate-200" : "text-slate-800"}`}>{kpi.label}</div>
                  <div className={`text-xs mt-1 ${darkMode ? "text-slate-500" : "text-slate-500"}`}>{kpi.unit}</div>
                  {kpi.error && <div className="text-xs text-red-500 mt-2">{kpi.error}</div>}
                </div>
              );
            })}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className={`border rounded-lg p-6 ${darkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"}`}>
              <h3 className={`text-sm font-semibold mb-4 ${darkMode ? "text-white" : "text-slate-900"}`}>SLA Compliance Trend</h3>
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={complianceSeries.length ? complianceSeries : [{ month: "—", compliance: 0 }]}>
                  <defs>
                    <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={CAPITA_COLORS.green} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={CAPITA_COLORS.green} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={darkMode ? "#475569" : "#e2e8f0"} />
                  <XAxis dataKey="month" stroke="#94a3b8" style={{ fontSize: 11 }} />
                  <YAxis stroke="#94a3b8" style={{ fontSize: 11 }} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: darkMode ? "#1e293b" : "#fff",
                      border: darkMode ? "1px solid #475569" : "1px solid #e2e8f0",
                    }}
                  />
                  <Area type="monotone" dataKey="compliance" stroke={CAPITA_COLORS.green} fill="url(#cg)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className={`border rounded-lg p-6 ${darkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"}`}>
              <h3 className={`text-sm font-semibold mb-4 ${darkMode ? "text-white" : "text-slate-900"}`}>Breaches by KPI (recent)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={breachSeries.length ? breachSeries : [{ name: "—", count: 0 }]} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke={darkMode ? "#475569" : "#e2e8f0"} />
                  <XAxis type="number" stroke="#94a3b8" />
                  <YAxis type="category" dataKey="name" stroke="#94a3b8" width={120} style={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: darkMode ? "#1e293b" : "#fff",
                      border: darkMode ? "1px solid #475569" : "1px solid #e2e8f0",
                    }}
                  />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {(breachSeries.length ? breachSeries : [{ name: "", count: 0 }]).map((_, i) => (
                      <Cell key={i} fill={CHART_FILLS[i % CHART_FILLS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
