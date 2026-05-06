import { useCallback, useEffect, useMemo, useState } from "react";
import { Send, Activity, Lightbulb, X, Moon, Sun, RotateCcw, Settings, Upload, type LucideIcon } from "lucide-react";
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import * as LucideIcons from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  fetchBootstrap,
  fetchBrandingSettings,
  fetchContextualSuggestions,
  fetchCurrentConversation,
  fetchDashboardCharts,
  fetchKpis,
  fetchPriorityActions,
  fetchSuggestions,
  generateNba,
  saveBrandingSettings,
  startNewConversation,
  streamChat,
  uploadBrandingLogo,
  type BrandingResolved,
  type ChatStreamEvent,
  type KPIPayload,
  type NextBestAction,
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

const CATEGORY_COLORS: Record<string, string> = {
  SLA: "#003B5C",
  Obligations: "#00A3E0",
  Trends: "#10D6A6",
  Suppliers: "#C5D201",
  Risk: "#E0566A",
  Contract: "#9B62C3",
  Insights: "#0D5A85",
};

function categoryColor(c?: string | null): string {
  if (!c) return CAPITA_COLORS.navyBlue;
  return CATEGORY_COLORS[c] || CAPITA_COLORS.navyBlue;
}

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

type NBAModalProps = {
  actions: NextBestAction[] | null;
  loading: boolean;
  error: string | null;
  darkMode: boolean;
  onClose: () => void;
};

function urgencyStyle(urgency: NextBestAction["urgency"], darkMode: boolean) {
  if (urgency === "Immediate") {
    return {
      dot: "#E0566A",
      bg: darkMode ? "rgba(224,86,106,0.15)" : "rgba(224,86,106,0.08)",
      border: "rgba(224,86,106,0.45)",
      label: "Immediate",
    };
  }
  if (urgency === "This Week") {
    return {
      dot: "#F59E0B",
      bg: darkMode ? "rgba(245,158,11,0.15)" : "rgba(245,158,11,0.08)",
      border: "rgba(245,158,11,0.45)",
      label: "This Week",
    };
  }
  return {
    dot: "#10D6A6",
    bg: darkMode ? "rgba(16,214,166,0.12)" : "rgba(16,214,166,0.08)",
    border: "rgba(16,214,166,0.45)",
    label: "Monitor",
  };
}

function NBAModal({ actions, loading, error, darkMode, onClose }: NBAModalProps) {
  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-auto ${darkMode ? "bg-slate-800" : "bg-white"}`}
      >
        <div
          className={`sticky top-0 z-10 border-b p-6 flex items-center justify-between ${darkMode ? "border-slate-700 bg-slate-800" : "border-slate-200 bg-white"}`}
        >
          <div>
            <h3 className={`text-xl font-semibold ${darkMode ? "text-white" : "text-slate-900"}`}>
              Priority Actions
            </h3>
            <p className={`text-xs mt-0.5 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
              Based on your conversation context
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`p-1 rounded transition-colors ${darkMode ? "text-slate-400 hover:bg-slate-700" : "text-slate-400 hover:bg-slate-100"}`}
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-4">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <span
                className="inline-block w-2 h-2 rounded-full animate-pulse mr-3"
                style={{ backgroundColor: CAPITA_COLORS.cyan }}
              />
              <span className={`text-sm ${darkMode ? "text-slate-200" : "text-slate-700"}`}>
                Generating recommended actions…
              </span>
            </div>
          )}
          {!loading && error && (
            <div className="text-sm text-red-500 px-2 py-3">{error}</div>
          )}
          {!loading && !error && actions && actions.length === 0 && (
            <div className={`text-sm ${darkMode ? "text-slate-300" : "text-slate-700"}`}>
              No urgent actions surfaced — current contract data looks healthy.
            </div>
          )}
          {!loading && !error &&
            (actions || []).map((action, idx) => {
              const u = urgencyStyle(action.urgency, darkMode);
              return (
                <div
                  key={`${action.action}-${idx}`}
                  className="border rounded-lg p-4"
                  style={{ borderColor: u.border, backgroundColor: u.bg }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: u.dot }} />
                    <span
                      className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                      style={{ color: u.dot, backgroundColor: `${u.dot}22` }}
                    >
                      {u.label}
                    </span>
                  </div>
                  <p className={`text-sm font-medium leading-snug ${darkMode ? "text-white" : "text-slate-900"}`}>
                    {action.action}
                  </p>
                  {action.rationale && (
                    <p className={`text-xs mt-2 ${darkMode ? "text-slate-300" : "text-slate-700"}`}>
                      {action.rationale}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-3 mt-3 text-[11px]">
                    {action.contract_ref && (
                      <span className={darkMode ? "text-slate-400" : "text-slate-500"}>
                        Clause: <span className={darkMode ? "text-slate-200" : "text-slate-700"}>{action.contract_ref}</span>
                      </span>
                    )}
                    {action.owner_role && (
                      <span className={darkMode ? "text-slate-400" : "text-slate-500"}>
                        Owner: <span className={darkMode ? "text-slate-200" : "text-slate-700"}>{action.owner_role}</span>
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}

type PriorityActionsWidgetProps = {
  actions: NextBestAction[];
  summary: Record<string, number>;
  ruleCount: number;
  loading: boolean;
  darkMode: boolean;
  onRefresh: () => void;
};

function PriorityActionsWidget({
  actions,
  summary,
  ruleCount,
  loading,
  darkMode,
  onRefresh,
}: PriorityActionsWidgetProps) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? actions : actions.slice(0, 4);
  const sumImmediate = summary["Immediate"] || 0;
  const sumWeek = summary["This Week"] || 0;
  const sumMonitor = summary["Monitor"] || 0;

  return (
    <div
      className={`border rounded-xl p-6 mb-6 ${darkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"}`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Lightbulb className="w-5 h-5" style={{ color: CAPITA_COLORS.green }} />
          <h3 className={`text-lg font-semibold ${darkMode ? "text-white" : "text-slate-900"}`}>
            Priority Actions
          </h3>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 ${
            darkMode ? "text-slate-300 hover:bg-slate-700" : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <RotateCcw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <p className={`text-xs mb-4 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
        Based on current contract data ({ruleCount} rule{ruleCount === 1 ? "" : "s"} matched)
      </p>

      <div className="flex flex-wrap gap-3 mb-4 text-xs">
        <span
          className="px-3 py-1 rounded-full font-medium"
          style={{ color: "#E0566A", backgroundColor: "rgba(224,86,106,0.12)" }}
        >
          ● Immediate ({sumImmediate})
        </span>
        <span
          className="px-3 py-1 rounded-full font-medium"
          style={{ color: "#F59E0B", backgroundColor: "rgba(245,158,11,0.12)" }}
        >
          ● This Week ({sumWeek})
        </span>
        <span
          className="px-3 py-1 rounded-full font-medium"
          style={{ color: "#10A37F", backgroundColor: "rgba(16,214,166,0.12)" }}
        >
          ● Monitor ({sumMonitor})
        </span>
      </div>

      {actions.length === 0 && !loading && (
        <p className={`text-sm py-4 ${darkMode ? "text-slate-300" : "text-slate-600"}`}>
          No actions surfaced — current contract data looks healthy.
        </p>
      )}

      <div className="space-y-3">
        {visible.map((a, i) => {
          const u = urgencyStyle(a.urgency, darkMode);
          return (
            <div
              key={`${a.action}-${i}`}
              className="border rounded-lg p-3 flex gap-3"
              style={{ borderColor: u.border, backgroundColor: u.bg }}
            >
              <span className="inline-block w-2 h-2 rounded-full mt-2 shrink-0" style={{ backgroundColor: u.dot }} />
              <div className="flex-1">
                <p className={`text-sm font-medium leading-snug ${darkMode ? "text-white" : "text-slate-900"}`}>
                  {a.action}
                </p>
                <div className={`text-[11px] mt-1 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
                  {a.contract_ref ? <>Clause: <span className={darkMode ? "text-slate-200" : "text-slate-700"}>{a.contract_ref}</span></> : null}
                  {a.contract_ref && a.owner_role ? " · " : ""}
                  {a.owner_role ? <>Owner: <span className={darkMode ? "text-slate-200" : "text-slate-700"}>{a.owner_role}</span></> : null}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {actions.length > 4 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className={`mt-3 text-xs underline ${darkMode ? "text-slate-300" : "text-slate-600"}`}
        >
          {showAll ? "Show less" : `Show all (${actions.length})`}
        </button>
      )}
    </div>
  );
}

type BrandingModalProps = {
  darkMode: boolean;
  onClose: () => void;
  onSaved: (resolved: BrandingResolved) => void;
};

function BrandingModal({ darkMode, onClose, onSaved }: BrandingModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [lakebaseEnabled, setLakebaseEnabled] = useState(true);
  const [resolved, setResolved] = useState<BrandingResolved>({
    app_name: "",
    app_logo_url: "",
    app_logo_url_dark: "",
  });
  const [appName, setAppName] = useState("");
  const [logoUrl, setLogoUrl] = useState("");
  const [logoUrlDark, setLogoUrlDark] = useState("");

  useEffect(() => {
    fetchBrandingSettings()
      .then((b) => {
        setLakebaseEnabled(b.lakebase_enabled);
        setResolved(b.resolved);
        setAppName(b.saved.app_name ?? b.resolved.app_name ?? "");
        setLogoUrl(b.saved.app_logo_url ?? b.resolved.app_logo_url ?? "");
        setLogoUrlDark(b.saved.app_logo_url_dark ?? "");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const r = await saveBrandingSettings({
        app_name: appName,
        app_logo_url: logoUrl,
        app_logo_url_dark: logoUrlDark,
      });
      setResolved(r.resolved);
      setInfo("Saved.");
      onSaved(r.resolved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const onResetToDefaults = async () => {
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const r = await saveBrandingSettings({
        app_name: "",
        app_logo_url: "",
        app_logo_url_dark: "",
      });
      setResolved(r.resolved);
      setAppName(r.resolved.app_name);
      setLogoUrl(r.resolved.app_logo_url);
      setLogoUrlDark("");
      setInfo("Reset to environment / file defaults.");
      onSaved(r.resolved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to reset");
    } finally {
      setSaving(false);
    }
  };

  const onUploadFile = async (file: File, variant: "light" | "dark") => {
    setSaving(true);
    setError(null);
    setInfo(null);
    try {
      const r = await uploadBrandingLogo(file, variant);
      setResolved(r.resolved);
      if (variant === "light") setLogoUrl(r.resolved.app_logo_url);
      else setLogoUrlDark(r.resolved.app_logo_url_dark || "");
      setInfo(`Uploaded ${variant} logo (${Math.round(r.size_bytes / 1024)} KB).`);
      onSaved(r.resolved);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setSaving(false);
    }
  };

  const inputBase = `w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 ${
    darkMode ? "bg-slate-700 border-slate-600 text-white placeholder-slate-400" : "bg-slate-50 border-slate-200 text-slate-900"
  }`;

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`rounded-xl shadow-2xl max-w-xl w-full max-h-[90vh] overflow-auto ${darkMode ? "bg-slate-800" : "bg-white"}`}
      >
        <div
          className={`sticky top-0 z-10 border-b p-5 flex items-center justify-between ${darkMode ? "border-slate-700 bg-slate-800" : "border-slate-200 bg-white"}`}
        >
          <div>
            <h3 className={`text-lg font-semibold ${darkMode ? "text-white" : "text-slate-900"}`}>
              App Branding
            </h3>
            <p className={`text-xs mt-0.5 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
              Changes apply instantly — no redeploy needed.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`p-1 rounded transition-colors ${darkMode ? "text-slate-400 hover:bg-slate-700" : "text-slate-400 hover:bg-slate-100"}`}
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {!lakebaseEnabled && (
            <div className="text-xs px-3 py-2 rounded border border-amber-300 bg-amber-50 text-amber-800">
              Lakebase isn't configured for this app — you can still preview locally,
              but saves will fail. Set <code>LAKEBASE_HOST</code> + database env vars.
            </div>
          )}
          {loading && (
            <div className={`text-sm ${darkMode ? "text-slate-300" : "text-slate-600"}`}>Loading…</div>
          )}

          {!loading && (
            <>
              <div>
                <label className={`block text-xs font-medium mb-1 ${darkMode ? "text-slate-300" : "text-slate-700"}`}>
                  App name
                </label>
                <input
                  type="text"
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder="Capita TfL Analytics"
                  className={inputBase}
                  style={{ "--tw-ring-color": CAPITA_COLORS.navyBlue } as React.CSSProperties}
                />
                <p className={`text-[11px] mt-1 ${darkMode ? "text-slate-500" : "text-slate-500"}`}>
                  Shown in the browser tab and (when no logo is set) in the header.
                </p>
              </div>

              <div>
                <label className={`block text-xs font-medium mb-1 ${darkMode ? "text-slate-300" : "text-slate-700"}`}>
                  Logo URL (light mode)
                </label>
                <input
                  type="text"
                  value={logoUrl}
                  onChange={(e) => setLogoUrl(e.target.value)}
                  placeholder="/api/assets/logo  or  https://cdn.example.com/logo.svg"
                  className={inputBase}
                  style={{ "--tw-ring-color": CAPITA_COLORS.navyBlue } as React.CSSProperties}
                />
                <div className="flex items-center gap-3 mt-2">
                  <label
                    className={`inline-flex items-center gap-2 text-xs px-3 py-2 rounded-lg cursor-pointer border transition-colors ${
                      darkMode ? "border-slate-600 text-slate-200 hover:bg-slate-700" : "border-slate-200 text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload file…</span>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/svg+xml,image/webp,image/gif"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void onUploadFile(f, "light");
                        e.target.value = "";
                      }}
                    />
                  </label>
                  {logoUrl && !logoUrl.endsWith("undefined") && (
                    <img
                      src={logoUrl}
                      alt="Light preview"
                      className={`h-8 max-w-[160px] object-contain border rounded ${darkMode ? "border-slate-700 bg-white" : "border-slate-200 bg-white"} px-2 py-1`}
                    />
                  )}
                </div>
              </div>

              <div>
                <label className={`block text-xs font-medium mb-1 ${darkMode ? "text-slate-300" : "text-slate-700"}`}>
                  Logo URL (dark mode — optional)
                </label>
                <input
                  type="text"
                  value={logoUrlDark}
                  onChange={(e) => setLogoUrlDark(e.target.value)}
                  placeholder="Leave blank to reuse the light logo"
                  className={inputBase}
                  style={{ "--tw-ring-color": CAPITA_COLORS.navyBlue } as React.CSSProperties}
                />
                <div className="flex items-center gap-3 mt-2">
                  <label
                    className={`inline-flex items-center gap-2 text-xs px-3 py-2 rounded-lg cursor-pointer border transition-colors ${
                      darkMode ? "border-slate-600 text-slate-200 hover:bg-slate-700" : "border-slate-200 text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload file…</span>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/svg+xml,image/webp,image/gif"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) void onUploadFile(f, "dark");
                        e.target.value = "";
                      }}
                    />
                  </label>
                  {logoUrlDark && (
                    <img
                      src={logoUrlDark}
                      alt="Dark preview"
                      className="h-8 max-w-[160px] object-contain border rounded border-slate-700 bg-slate-900 px-2 py-1"
                    />
                  )}
                </div>
              </div>

              {(error || info) && (
                <div
                  className={`text-xs px-3 py-2 rounded ${
                    error
                      ? "border border-red-300 bg-red-50 text-red-700"
                      : "border border-emerald-300 bg-emerald-50 text-emerald-700"
                  }`}
                >
                  {error || info}
                </div>
              )}

              <div className="text-[11px] space-y-1 px-1 pb-1">
                <div className={darkMode ? "text-slate-500" : "text-slate-500"}>
                  Currently resolved:
                </div>
                <div className={darkMode ? "text-slate-300" : "text-slate-600"}>
                  • app_name: <code>{resolved.app_name || "(empty)"}</code>
                </div>
                <div className={darkMode ? "text-slate-300" : "text-slate-600"}>
                  • app_logo_url: <code>{resolved.app_logo_url || "(empty)"}</code>
                </div>
                <div className={darkMode ? "text-slate-300" : "text-slate-600"}>
                  • app_logo_url_dark: <code>{resolved.app_logo_url_dark || "(empty)"}</code>
                </div>
              </div>
            </>
          )}
        </div>

        <div
          className={`sticky bottom-0 border-t p-4 flex items-center justify-between gap-3 ${
            darkMode ? "border-slate-700 bg-slate-800" : "border-slate-200 bg-white"
          }`}
        >
          <button
            type="button"
            onClick={() => void onResetToDefaults()}
            disabled={saving || loading || !lakebaseEnabled}
            className={`text-xs underline disabled:opacity-50 ${darkMode ? "text-slate-400" : "text-slate-500"}`}
          >
            Reset to defaults
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className={`px-4 py-2 text-sm rounded-lg ${darkMode ? "text-slate-300 hover:bg-slate-700" : "text-slate-600 hover:bg-slate-100"}`}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving || loading || !lakebaseEnabled}
              className="px-4 py-2 text-sm text-white rounded-lg disabled:opacity-50"
              style={{ backgroundColor: CAPITA_COLORS.navyBlue }}
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"chat" | "dashboard">("chat");
  const [darkMode, setDarkMode] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [sending, setSending] = useState(false);
  const [personaName, setPersonaName] = useState("Adam");
  const [personaTitle, setPersonaTitle] = useState("");
  const [appName, setAppName] = useState("");
  const [appLogoUrl, setAppLogoUrl] = useState("");
  const [appLogoUrlDark, setAppLogoUrlDark] = useState("");
  const [logoBroken, setLogoBroken] = useState(false);
  const [brandingOpen, setBrandingOpen] = useState(false);

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
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [suggestionsRefreshing, setSuggestionsRefreshing] = useState(false);

  const [nbaModalOpen, setNbaModalOpen] = useState(false);
  const [nbaActions, setNbaActions] = useState<NextBestAction[] | null>(null);
  const [nbaLoading, setNbaLoading] = useState(false);
  const [nbaError, setNbaError] = useState<string | null>(null);

  const [priorityActions, setPriorityActions] = useState<NextBestAction[]>([]);
  const [prioritySummary, setPrioritySummary] = useState<Record<string, number>>({});
  const [priorityLoading, setPriorityLoading] = useState(false);
  const [priorityRuleCount, setPriorityRuleCount] = useState(0);

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
        setAppName(b.app_name || "");
        setAppLogoUrl(b.app_logo_url || "");
        setAppLogoUrlDark(b.app_logo_url_dark || b.app_logo_url || "");
        setLogoBroken(false);
        if (b.app_name) document.title = b.app_name;
      })
      .catch(() => {});

    fetchSuggestions()
      .then((r) => setSuggestions(r.items || []))
      .catch(() => setSuggestions([]));

    // Rehydrate the latest conversation from Lakebase (if enabled server-side)
    fetchCurrentConversation()
      .then((c) => {
        if (!c.enabled) return;
        setConversationId(c.conversation_id);
        if (!c.messages || c.messages.length === 0) return;
        setMessages(
          c.messages.map((m) => ({
            role: m.role,
            content: m.content,
            routed: m.routed_to || undefined,
            elapsedMs: m.elapsed_ms ?? undefined,
          })),
        );
        // Refresh suggestions to be contextual to the rehydrated thread
        fetchContextualSuggestions(c.conversation_id || undefined)
          .then((r) => {
            if (r.items?.length) setSuggestions(r.items);
          })
          .catch(() => {});
      })
      .catch(() => {});
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

      const HISTORY_TURNS = 6;
      const history = messages
        .filter((m) => (m.fullContent ?? m.content).trim().length > 0)
        .slice(-HISTORY_TURNS)
        .map((m) => ({
          role: m.role,
          content: (m.fullContent ?? m.content).trim(),
        }));

      try {
        await streamChat(
          text,
          "supervisor",
          (e: ChatStreamEvent) => {
            if (e.type === "start") {
              setStatusLabel(`Routing to ${e.label}`);
              if (e.conversation_id) setConversationId(e.conversation_id);
            } else if (e.type === "status") {
              setStatusLabel(e.label);
              setStatusElapsedMs(e.elapsed_ms);
            } else if (e.type === "heartbeat") {
              if (typeof e.elapsed_ms === "number") setStatusElapsedMs(e.elapsed_ms);
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
              if (e.conversation_id) setConversationId(e.conversation_id);
            } else if (e.type === "suggestions") {
              if (e.items?.length) setSuggestions(e.items);
            } else if (e.type === "nba") {
              setNbaActions(e.actions || []);
              setNbaError(null);
              setNbaLoading(false);
              setNbaModalOpen(true);
            } else if (e.type === "error") {
              setMessages((m) => [
                ...m,
                { role: "assistant", content: `Sorry — ${e.message}` },
              ]);
            }
          },
          { history },
        );
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
    [sending, messages],
  );

  const onSend = useCallback(() => {
    void submitMessage(chatInput);
  }, [chatInput, submitMessage]);

  const refreshSuggestions = useCallback(async () => {
    if (suggestionsRefreshing) return;
    setSuggestionsRefreshing(true);
    try {
      const r = await fetchContextualSuggestions(conversationId || undefined);
      if (r.items?.length) setSuggestions(r.items);
    } catch {
      try {
        const r = await fetchSuggestions();
        if (r.items?.length) setSuggestions(r.items);
      } catch {
        /* ignore */
      }
    } finally {
      setSuggestionsRefreshing(false);
    }
  }, [conversationId, suggestionsRefreshing]);

  const openNbaFromConversation = useCallback(async () => {
    setNbaError(null);
    setNbaLoading(true);
    setNbaActions(null);
    setNbaModalOpen(true);
    try {
      const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
      const turns = messages
        .filter((m) => m.content && !m.typing)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.fullContent || m.content }));
      const r = await generateNba(turns, lastAssistant?.fullContent || lastAssistant?.content || "", conversationId);
      setNbaActions(r.actions || []);
    } catch (err) {
      setNbaError(err instanceof Error ? err.message : "Failed to generate actions");
    } finally {
      setNbaLoading(false);
    }
  }, [messages, conversationId]);

  const refreshPriorityActions = useCallback(async () => {
    setPriorityLoading(true);
    try {
      const r = await fetchPriorityActions();
      setPriorityActions(r.actions || []);
      setPrioritySummary(r.summary || {});
      setPriorityRuleCount(r.matched_rule_count || 0);
    } catch {
      /* ignore */
    } finally {
      setPriorityLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "dashboard" && priorityActions.length === 0 && !priorityLoading) {
      void refreshPriorityActions();
    }
  }, [activeTab, priorityActions.length, priorityLoading, refreshPriorityActions]);

  const onNewThread = useCallback(async () => {
    if (sending) return;
    try {
      const r = await startNewConversation();
      setConversationId(r.conversation_id);
    } catch {
      setConversationId(null);
    }
    setMessages([]);
    fetchSuggestions()
      .then((r) => setSuggestions(r.items || []))
      .catch(() => {});
  }, [sending]);

  const starterChips = suggestions.slice(0, 5);
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const followupChips = lastAssistant?.followups?.length ? lastAssistant.followups : [];

  return (
    <div className={`size-full flex flex-col min-h-0 ${darkMode ? "bg-slate-900" : "bg-slate-50"}`}>
      {brandingOpen && (
        <BrandingModal
          darkMode={darkMode}
          onClose={() => setBrandingOpen(false)}
          onSaved={(r) => {
            setAppName(r.app_name || "");
            setAppLogoUrl(r.app_logo_url || "");
            setAppLogoUrlDark(r.app_logo_url_dark || r.app_logo_url || "");
            setLogoBroken(false);
            if (r.app_name) document.title = r.app_name;
          }}
        />
      )}
      <div
        className={`border-b px-6 shrink-0 ${darkMode ? "bg-slate-800 border-slate-700" : "bg-white border-slate-200"}`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            {(() => {
              const url = darkMode ? appLogoUrlDark || appLogoUrl : appLogoUrl;
              if (!url || logoBroken) {
                if (!appName) return null;
                return (
                  <div
                    className={`text-sm font-semibold pr-4 border-r ${darkMode ? "text-white border-slate-700" : "text-slate-900 border-slate-200"}`}
                  >
                    {appName}
                  </div>
                );
              }
              return (
                <div
                  className={`flex items-center gap-2 pr-4 border-r ${darkMode ? "border-slate-700" : "border-slate-200"}`}
                  title={appName || undefined}
                >
                  <img
                    src={url}
                    alt={appName || "App logo"}
                    className="h-8 max-w-[160px] object-contain"
                    onError={() => setLogoBroken(true)}
                  />
                </div>
              );
            })()}
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
          </div>
          <div className="flex items-center gap-2">
            {activeTab === "chat" && (
              <button
                type="button"
                onClick={() => void onNewThread()}
                disabled={sending}
                title="Start a new conversation"
                className={`p-2 rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 ${
                  darkMode ? "bg-slate-700 text-slate-200 hover:bg-slate-600" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                <RotateCcw className="w-4 h-4" />
                <span className="text-xs font-medium">New thread</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setBrandingOpen(true)}
              title="App branding (logo + name)"
              className={`p-2 rounded-lg transition-colors ${
                darkMode ? "bg-slate-700 text-slate-200 hover:bg-slate-600" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              <Settings className="w-5 h-5" />
            </button>
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
      </div>

      {activeTab === "chat" ? (
        <div className="flex-1 flex min-h-0 relative">
          {/* Left panel — greeting + suggestion cards */}
          <aside
            className={`hidden md:flex w-[360px] shrink-0 border-r flex-col ${
              darkMode ? "bg-slate-900 border-slate-700" : "bg-white border-slate-200"
            }`}
          >
            <div className="px-6 pt-6 pb-4 shrink-0">
              <div className={`text-xs mb-1 ${darkMode ? "text-slate-400" : "text-slate-500"}`}>
                {new Date().toLocaleString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </div>
              <h2 className={`text-2xl font-semibold mb-1 ${darkMode ? "text-white" : "text-slate-900"}`}>
                Good morning, {personaName}
              </h2>
              <p className={`text-sm ${darkMode ? "text-slate-400" : "text-slate-600"}`}>
                Your most likely questions based on recent patterns:
              </p>
            </div>

            <div className="flex-1 overflow-auto px-6 pb-4 space-y-3 min-h-0">
              {(starterChips.length
                ? starterChips
                : followupChips.map((q) => ({ question: q, category: lastAssistant?.routed || "Insights" }))
              ).map((chip, i) => {
                const color = categoryColor(chip.category);
                return (
                  <button
                    type="button"
                    key={`${chip.question}-${i}`}
                    onClick={() => void submitMessage(chip.question)}
                    disabled={sending}
                    className={`w-full text-left rounded-xl border p-4 transition-all hover:shadow-md disabled:opacity-50 ${
                      darkMode ? "bg-slate-800 border-slate-700 hover:bg-slate-750" : "bg-white border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span
                        className="text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded text-white"
                        style={{ backgroundColor: color }}
                      >
                        {chip.category || "Insights"}
                      </span>
                      <span
                        className="h-[2px] w-10 rounded"
                        style={{ backgroundColor: `${color}55` }}
                      />
                    </div>
                    <p className={`text-sm leading-snug ${darkMode ? "text-slate-100" : "text-slate-800"}`}>
                      {chip.question}
                    </p>
                  </button>
                );
              })}
              {!starterChips.length && !followupChips.length && (
                <p className={`text-xs ${darkMode ? "text-slate-500" : "text-slate-500"}`}>
                  No suggestions yet — try the refresh button.
                </p>
              )}
            </div>

            <div className={`px-6 py-4 border-t shrink-0 ${darkMode ? "border-slate-700" : "border-slate-200"}`}>
              <button
                type="button"
                onClick={() => void refreshSuggestions()}
                disabled={suggestionsRefreshing}
                className={`w-full flex items-center justify-center gap-2 text-xs font-medium py-2 rounded-lg transition-colors disabled:opacity-50 ${
                  darkMode ? "text-slate-300 hover:bg-slate-800" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <RotateCcw className={`w-3.5 h-3.5 ${suggestionsRefreshing ? "animate-spin" : ""}`} />
                {suggestionsRefreshing ? "Refreshing…" : "Refresh suggestions"}
              </button>
            </div>
          </aside>

          {/* Right panel — chat */}
          <div className="flex-1 flex flex-col min-h-0 relative">
          <div className="flex-1 overflow-auto p-6 space-y-4 min-h-0">
            {messages.length === 0 && (
              <div className="flex justify-start">
                <div
                  className="max-w-3xl rounded-lg p-4 border"
                  style={{
                    backgroundColor: darkMode ? "rgba(0,163,224,0.08)" : "rgba(0,163,224,0.06)",
                    borderColor: darkMode ? "rgba(0,163,224,0.30)" : "rgba(0,163,224,0.25)",
                    color: darkMode ? "#e2e8f0" : "#0f172a",
                  }}
                >
                  <p className="text-sm">
                    Good morning, {personaName}. I'm here to help you track the TfL contract performance.
                    Click any question on the left or ask me anything.
                  </p>
                </div>
              </div>
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
              onClick={() => void openNbaFromConversation()}
              disabled={messages.length === 0 || nbaLoading}
              title={messages.length === 0 ? "Ask a question first to generate actions" : "Generate next best actions from this conversation"}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg transition-colors border disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                backgroundColor: `${CAPITA_COLORS.green}${darkMode ? "33" : "1A"}`,
                color: darkMode ? CAPITA_COLORS.green : "#8B9600",
                borderColor: `${CAPITA_COLORS.green}66`,
              }}
            >
              <Lightbulb className="w-4 h-4" />
              <span className="text-sm font-medium">
                {nbaLoading ? "Generating actions…" : "Suggest next best actions based on this conversation"}
              </span>
            </button>
          </div>
          </div>

          {nbaModalOpen && (
            <NBAModal
              actions={nbaActions}
              loading={nbaLoading}
              error={nbaError}
              darkMode={darkMode}
              onClose={() => setNbaModalOpen(false)}
            />
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-auto p-8">
          <div className="mb-8">
            <h2 className={`text-3xl font-semibold mb-2 ${darkMode ? "text-white" : "text-slate-900"}`}>TfL Contract Overview</h2>
            <p className={`text-sm ${darkMode ? "text-slate-400" : "text-slate-600"}`}>Live KPIs from Unity Catalog</p>
          </div>

          <PriorityActionsWidget
            actions={priorityActions}
            summary={prioritySummary}
            ruleCount={priorityRuleCount}
            loading={priorityLoading}
            darkMode={darkMode}
            onRefresh={() => void refreshPriorityActions()}
          />

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
