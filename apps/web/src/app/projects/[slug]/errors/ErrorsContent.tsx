"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChevronRight, MoreVertical, RefreshCw, Search } from "lucide-react";
import LiveIndicator from "@/components/aperture/LiveIndicator";
import LiveNumber from "@/components/aperture/LiveNumber";
import { useLivePoll } from "@/lib/useLivePoll";
import { fmtNum, fmtCompact } from "@/lib/format";
import {
  type RangeValue,
  parseRange,
  resolveRange,
  TimeRangePicker,
} from "../_shared/timeRange";
import {
  AXIS_TICK,
  ChartTooltip,
  EmptyBlock,
  GRID,
  Skeleton,
  formatBucketFull,
  formatBucketTime,
  statusTone,
} from "../endpoints/detail/sections";
import ErrorGroupInspector from "./ErrorGroupInspector";
import { type ErrorGroup, reasonPhrase } from "./util";

/* ── Types ───────────────────────────────────────────────────────────── */

interface ErrorSummary {
  total_requests: number;
  client_errors: number;
  server_errors: number;
  error_rate: number;
  unique_issues: number;
  affected_consumers: number;
  last_seen: string | null;
}

interface TSPoint {
  bucket: string;
  client_error_count?: number;
  server_error_count?: number;
  client_error_rate?: number;
  server_error_rate?: number;
}

interface InitialFilters {
  range?: string;
  since?: string;
  until?: string;
  env?: string;
}

interface Props {
  projectSlug: string;
  initialFilters?: InitialFilters;
}

type MetricKey = "total" | "client" | "server" | "rate";
type SortKey = "occurrences" | "consumers";

const EMPTY_SUMMARY: ErrorSummary = {
  total_requests: 0, client_errors: 0, server_errors: 0, error_rate: 0,
  unique_issues: 0, affected_consumers: 0, last_seen: null,
};

// Error-bar palette — the dusty rose from the reference: client (4xx) a muted
// rose, server (5xx) a deeper red.
const CLIENT_ROSE = "#d99a9a";
const SERVER_ROSE = "#c04b4b";

const groupKey = (g: ErrorGroup) => `${g.status_code}|${g.method}|${g.path}`;

/* ── Self-measuring chart frame (recharts width(-1) guard) ───────────── */
function Chart({ height, render }: { height: number; render: (w: number) => React.ReactElement }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div ref={ref} className="tf-chart-stage" style={{ height, width: "100%", minWidth: 0 }}>
      {width > 0 ? render(width) : null}
    </div>
  );
}

/* ── Component ───────────────────────────────────────────────────────── */

export default function ErrorsContent({ projectSlug, initialFilters }: Props) {
  const [rangeValue, setRangeValue] = useState<RangeValue>(() => parseRange(initialFilters));
  const [environment, setEnvironment] = useState<string>(initialFilters?.env || "");
  const [envOptions, setEnvOptions] = useState<string[]>([]);
  const [activeMetric, setActiveMetric] = useState<MetricKey>("total");
  const [refreshKey, setRefreshKey] = useState(0);

  const [summary, setSummary] = useState<ErrorSummary | null>(null);
  const [series, setSeries] = useState<TSPoint[] | null>(null);
  const [groups, setGroups] = useState<ErrorGroup[] | null>(null);
  const [openGroup, setOpenGroup] = useState<ErrorGroup | null>(null);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("occurrences");
  const [kebab, setKebab] = useState<string | null>(null);

  const resolved = useMemo(() => resolveRange(rangeValue), [rangeValue, refreshKey]);

  useEffect(() => {
    const p = new URLSearchParams();
    if (rangeValue.type === "custom") {
      p.set("since", rangeValue.since);
      p.set("until", rangeValue.until);
    } else {
      p.set("range", rangeValue.id);
    }
    if (environment) p.set("env", environment);
    const qs = p.toString();
    window.history.replaceState(null, "", qs ? `${window.location.pathname}?${qs}` : window.location.pathname);
  }, [rangeValue, environment]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/projects/${projectSlug}/analytics/environments`);
        if (res.ok) setEnvOptions((await res.json()).environments || []);
      } catch { /* ignore */ }
    })();
  }, [projectSlug]);

  const reqId = useRef(0);
  const loadData = useCallback(
    async (silent: boolean) => {
      const { since, until } = resolveRange(rangeValue);
      const qs = () => {
        const p = new URLSearchParams();
        p.set("since", since);
        p.set("until", until);
        if (environment) p.set("environment", environment);
        return p.toString();
      };
      const get = async <T,>(path: string, extra: string, fallback: T): Promise<T> => {
        try {
          const res = await fetch(`/api/projects/${projectSlug}/analytics/${path}?${qs()}${extra}`);
          return res.ok ? ((await res.json()) as T) : fallback;
        } catch {
          return fallback;
        }
      };
      const myId = ++reqId.current;
      if (!silent) setLoading(true);
      const [sum, ts, grp] = await Promise.all([
        get<ErrorSummary>("error-summary", "", EMPTY_SUMMARY),
        get<TSPoint[]>("timeseries", "", []),
        get<ErrorGroup[]>("error-status-groups", "&limit=200", []),
      ]);
      if (myId !== reqId.current) return;
      setSummary(sum);
      setSeries(Array.isArray(ts) ? ts : []);
      setGroups(Array.isArray(grp) ? grp : []);
      if (!silent) setLoading(false);
    },
    [projectSlug, rangeValue, environment],
  );

  useEffect(() => {
    loadData(false);
  }, [loadData, refreshKey]);

  const poll = useLivePoll({
    intervalMs: 5000,
    onTick: () => loadData(true),
    deps: [loadData],
  });

  useEffect(() => {
    if (!kebab) return;
    const onClick = () => setKebab(null);
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [kebab]);

  const cur = summary || EMPTY_SUMMARY;
  const totalErrors = cur.client_errors + cur.server_errors;
  const toneFor = (r: number): "warn" | "bad" | undefined => (r >= 5 ? "bad" : r >= 1 ? "warn" : undefined);

  // Metric tabs — attached to the chart (a click reconfigures the chart below),
  // exactly like the Traffic page.
  const METRICS: Record<MetricKey, { label: string; num: number; fmt: (v: number) => string; tone?: "warn" | "bad" }> = {
    total: { label: "Total errors", num: totalErrors, fmt: fmtNum },
    client: { label: "Client errors", num: cur.client_errors, fmt: fmtNum, tone: cur.client_errors > 0 ? "warn" : undefined },
    server: { label: "Server errors", num: cur.server_errors, fmt: fmtNum, tone: cur.server_errors > 0 ? "bad" : undefined },
    rate: { label: "Error rate", num: cur.error_rate, fmt: (v) => `${v.toFixed(1)} %`, tone: toneFor(cur.error_rate) },
  };
  const metricOrder: MetricKey[] = ["total", "client", "server", "rate"];

  const chartData = useMemo(
    () =>
      (series || []).map((p) => ({
        label: formatBucketTime(p.bucket),
        full: formatBucketFull(p.bucket),
        client: p.client_error_count || 0,
        server: p.server_error_count || 0,
        rate: (p.client_error_rate || 0) + (p.server_error_rate || 0),
      })),
    [series],
  );
  const hasChart = chartData.some((d) => d.client || d.server || d.rate);

  // Client-side search + sort over the loaded status groups.
  const rows = useMemo(() => {
    let list = groups || [];
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (g) =>
          g.path.toLowerCase().includes(q) ||
          g.method.toLowerCase().includes(q) ||
          String(g.status_code).includes(q) ||
          reasonPhrase(g.status_code).toLowerCase().includes(q),
      );
    }
    return [...list].sort((a, b) =>
      sortKey === "consumers" ? b.consumers - a.consumers : b.occurrences - a.occurrences,
    );
  }, [groups, search, sortKey]);

  const maxOcc = Math.max(1, ...rows.map((r) => r.occurrences));

  const copyEndpoint = async (g: ErrorGroup) => {
    try { await navigator.clipboard.writeText(`${g.method} ${g.path}`); } catch { /* ignore */ }
    setKebab(null);
  };

  const pctY = (v: number) => `${v}%`;

  return (
    <div className="err-page">
      {/* ── Toolbar ── */}
      <div className="tf-toolbar">
        <h1 className="tf-title">Errors</h1>
        <div className="tf-toolbar-spacer" />

        <select
          className="err-env-select"
          value={environment}
          onChange={(e) => setEnvironment(e.target.value)}
          aria-label="Environment"
        >
          <option value="">All environments</option>
          {envOptions.map((env) => (
            <option key={env} value={env}>{env}</option>
          ))}
        </select>

        <TimeRangePicker value={rangeValue} resolved={resolved} onChange={setRangeValue} />
        <LiveIndicator live={poll.live} onToggle={poll.toggle} lastTickAt={poll.lastTickAt} />

        <button
          type="button"
          className="tf-refresh"
          onClick={() => setRefreshKey((k) => k + 1)}
          title="Refresh now"
          aria-label="Refresh now"
        >
          <RefreshCw size={14} className={loading ? "tf-spin" : ""} />
        </button>
      </div>

      {/* ── Metrics + chart (tabs attached to the visualization) ── */}
      <section className="tf-panel">
        <div className="tf-metrics" role="tablist" aria-label="Error metric">
          {metricOrder.map((key) => {
            const m = METRICS[key];
            const isActive = key === activeMetric;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`tf-metric${isActive ? " active" : ""}${m.tone ? ` tf-metric-${m.tone}` : ""}`}
                onClick={() => setActiveMetric(key)}
              >
                <span className="tf-metric-label">{m.label}</span>
                <span className="tf-metric-value">
                  {loading ? "—" : <LiveNumber value={m.num} format={m.fmt} />}
                </span>
              </button>
            );
          })}
        </div>

        <div className="tf-panel-chart">
          {activeMetric === "total" && !loading && hasChart ? (
            <div className="tf-legend">
              <span className="tf-legend-item"><span className="tf-legend-dot" style={{ background: SERVER_ROSE }} />Server (5xx)</span>
              <span className="tf-legend-item"><span className="tf-legend-dot" style={{ background: CLIENT_ROSE }} />Client (4xx)</span>
            </div>
          ) : null}
          {series === null || loading ? (
            <Skeleton height={220} />
          ) : !hasChart ? (
            <EmptyBlock message="No errors in the selected period." />
          ) : (
            <Chart
              height={220}
              render={(w) =>
                activeMetric === "rate" ? (
                  <AreaChart key="rate" width={w} height={220} data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
                    <defs>
                      <linearGradient id="errRateFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={SERVER_ROSE} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={SERVER_ROSE} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke={GRID} vertical={false} />
                    <XAxis dataKey="label" tick={AXIS_TICK} minTickGap={28} tickLine={false} axisLine={{ stroke: GRID }} />
                    <YAxis tick={AXIS_TICK} tickFormatter={pctY} width={44} tickLine={false} axisLine={false} />
                    <Tooltip content={<ChartTooltip valueFormatter={(v: number) => `${v.toFixed(1)} %`} />} cursor={{ stroke: SERVER_ROSE, strokeDasharray: "3 3" }} />
                    <Area type="monotone" dataKey="rate" name="Error rate" stroke={SERVER_ROSE} fill="url(#errRateFill)" strokeWidth={2} />
                  </AreaChart>
                ) : (
                  <BarChart key={activeMetric} width={w} height={220} data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -16 }} barCategoryGap="22%">
                    <CartesianGrid stroke={GRID} vertical={false} />
                    <XAxis dataKey="label" tick={AXIS_TICK} minTickGap={28} tickLine={false} axisLine={{ stroke: GRID }} />
                    <YAxis tick={AXIS_TICK} allowDecimals={false} tickFormatter={fmtCompact} tickLine={false} axisLine={false} width={40} />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(192,75,75,0.10)" }} />
                    {(activeMetric === "total" || activeMetric === "server") && (
                      <Bar dataKey="server" name="Server (5xx)" stackId="e" fill={SERVER_ROSE} maxBarSize={34} radius={activeMetric === "server" ? [3, 3, 0, 0] : undefined} />
                    )}
                    {(activeMetric === "total" || activeMetric === "client") && (
                      <Bar dataKey="client" name="Client (4xx)" stackId="e" fill={CLIENT_ROSE} maxBarSize={34} radius={[3, 3, 0, 0]} />
                    )}
                  </BarChart>
                )
              }
            />
          )}
        </div>
      </section>

      {/* ── Errors table ── */}
      <section className="err-panel err-panel-flush">
        <div className="err-search">
          <Search size={15} className="err-search-icon" />
          <input
            className="err-search-input"
            placeholder="Search errors"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {groups === null ? (
          <Skeleton height={320} />
        ) : rows.length === 0 ? (
          <EmptyBlock message={search ? "No errors match your search." : "No errors in this period. 🎉"} />
        ) : (
          <table className="err-table">
            <thead>
              <tr>
                <th aria-hidden className="err-th-caret" />
                <th>Response status</th>
                <th>Endpoint</th>
                <th
                  className={`err-th-num err-th-sort${sortKey === "occurrences" ? " is-active" : ""}`}
                  onClick={() => setSortKey("occurrences")}
                  aria-sort={sortKey === "occurrences" ? "descending" : "none"}
                >
                  Occurrences{sortKey === "occurrences" ? " ▾" : ""}
                </th>
                <th
                  className={`err-th-num err-th-sort${sortKey === "consumers" ? " is-active" : ""}`}
                  onClick={() => setSortKey("consumers")}
                  aria-sort={sortKey === "consumers" ? "descending" : "none"}
                >
                  Consumers{sortKey === "consumers" ? " ▾" : ""}
                </th>
                <th aria-hidden className="err-th-kebab" />
              </tr>
            </thead>
            <tbody>
              {rows.map((g) => (
                <tr key={groupKey(g)} className="err-row" onClick={() => setOpenGroup(g)}>
                  <td className="err-td-caret"><ChevronRight size={15} /></td>
                  <td>
                    <span className="err-status">
                      <span className={`endpoint-status-pill ${statusTone(g.status_code)}`}>{g.status_code}</span>
                      <span className="err-status-reason">{reasonPhrase(g.status_code)}</span>
                    </span>
                  </td>
                  <td>
                    <span className="err-endpoint">
                      <span className={`method-badge method-badge-${g.method.toLowerCase()}`}>{g.method}</span>
                      <span className="err-endpoint-path">{g.path}</span>
                    </span>
                  </td>
                  <td className="err-td-num">
                    <span className="err-occ-cell">
                      <span className="err-occ-bar" style={{ width: `${(g.occurrences / maxOcc) * 100}%` }} />
                      <span className="err-occ-val">{fmtNum(g.occurrences)}</span>
                    </span>
                  </td>
                  <td className="err-td-num err-td-consumers">{fmtNum(g.consumers)}</td>
                  <td className="err-td-kebab">
                    <button
                      type="button"
                      className="err-kebab-btn"
                      aria-label="Row actions"
                      onClick={(e) => { e.stopPropagation(); setKebab(kebab === groupKey(g) ? null : groupKey(g)); }}
                    >
                      <MoreVertical size={15} />
                    </button>
                    {kebab === groupKey(g) ? (
                      <div className="err-kebab-menu" onClick={(e) => e.stopPropagation()}>
                        <button type="button" onClick={() => { setOpenGroup(g); setKebab(null); }}>View details</button>
                        <button type="button" onClick={() => copyEndpoint(g)}>Copy endpoint</button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {openGroup ? (
        <ErrorGroupInspector
          projectSlug={projectSlug}
          group={openGroup}
          since={resolved.since}
          until={resolved.until}
          environment={environment}
          onClose={() => setOpenGroup(null)}
        />
      ) : null}
    </div>
  );
}
