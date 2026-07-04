"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowDownToLine, ArrowUpFromLine, Check, Copy, Fingerprint, GitBranch, Globe, Link2, Server, Terminal, Timer, X } from "lucide-react";
import {
  formatBytes,
  formatDateTime,
  formatMs,
  highlightJson,
  parseHeaders,
  statusTone,
} from "./detail/sections";

/* ── Types ───────────────────────────────────────────────────────────── */

export interface RequestItem {
  timestamp: string;
  app_id: string;
  environment: string;
  method: string;
  path: string;
  status_code: number;
  response_time_ms: number;
  request_size: number;
  response_size: number;
  ip_address: string;
  user_agent: string;
  consumer_id: string;
  consumer_name: string;
  consumer_group: string;
  trace_id?: string;
  span_id?: string;
}

// Payload/header detail, lazily fetched from endpoint-requests (the flat
// data/requests list doesn't carry bodies/headers).
interface PayloadRow {
  timestamp: string;
  method: string;
  status_code: number;
  request_payload?: string;
  response_payload?: string;
  request_headers?: string;
  response_headers?: string;
  base_url?: string;
  country?: string;
  country_code?: string;
  trace_id?: string;
  span_id?: string;
}

interface SpanItem {
  timestamp: string;
  app_id: string;
  environment: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string;
  name: string;
  kind: string;
  service_name: string;
  duration_ms: number;
  status: string;
  status_code: number;
  attributes: Record<string, string>;
}

interface LogItem {
  timestamp: string;
  app_id: string;
  environment: string;
  level: string;
  message: string;
  logger_name: string;
  endpoint_method: string;
  endpoint_path: string;
  status_code: number;
  consumer_id: string;
  consumer_name: string;
  consumer_group: string;
  trace_id?: string;
  span_id?: string;
  payload: string;
  attributes: Record<string, string>;
}

type TraceState = SpanItem[] | "loading" | "error";
type LogState = LogItem[] | "loading" | "error";

type TabKey = "details" | "headers" | "response" | "related" | "logs" | "trace";

const BASE_TABS: Array<{ key: TabKey; label: string }> = [
  { key: "details", label: "Details" },
  { key: "headers", label: "Headers" },
  { key: "response", label: "Payload" },
  { key: "related", label: "Related" },
];
const LOGS_TAB: { key: TabKey; label: string } = { key: "logs", label: "Logs" };
const TRACE_TAB: { key: TabKey; label: string } = { key: "trace", label: "Trace" };

function methodColor(m: string): string {
  const k = m.toUpperCase();
  if (k === "GET") return "#14b8a6";
  if (k === "POST") return "#5A9CF8";
  if (k === "PUT") return "#f59e0b";
  if (k === "PATCH") return "#a78bfa";
  if (k === "DELETE") return "#f87171";
  return "#94a3b8";
}
function timeShort(ts: string): string {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function formatPayload(raw: string | undefined): string {
  if (!raw || !raw.trim()) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function StatusText(code: number): string {
  const map: Record<number, string> = {
    200: "OK", 201: "Created", 202: "Accepted", 204: "No Content",
    301: "Moved Permanently", 302: "Found", 304: "Not Modified",
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    409: "Conflict", 422: "Unprocessable Entity", 429: "Too Many Requests",
    500: "Internal Server Error", 502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
  };
  return map[code] || "";
}

/* ── Sub-blocks ──────────────────────────────────────────────────────── */

function MetricCard({ label, icon, value }: { label: string; icon: React.ReactNode; value: string }) {
  return (
    <div className="ep-statcard">
      <div className="ep-statcard-label">{label}</div>
      <div className="ep-statcard-main">
        <span className="ep-statcard-icon">{icon}</span>
        <span className="ep-statcard-value">{value}</span>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="ep-info-row">
      <span className="ep-info-key">{label}</span>
      <span className="ep-info-val">{value}</span>
    </div>
  );
}

function HeadersList({ raw, title }: { raw: string | undefined; title: string }) {
  const headers = parseHeaders(raw);
  if (headers.length === 0) {
    return (
      <div className="ep-rl-headblock">
        <h4 className="ep-rl-subhead">{title}</h4>
        <div className="endpoint-detail-empty">No headers captured.</div>
      </div>
    );
  }
  return (
    <div className="ep-rl-headblock">
      <h4 className="ep-rl-subhead">{title}</h4>
      <div className="ep-headers-list">
        {headers.map(([k, v]) => (
          <div key={k} className="ep-header-row">
            <span className="ep-header-key">{k}</span>
            <span className="ep-header-val">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Body({ title, raw }: { title: string; raw: string | undefined }) {
  const [copied, setCopied] = useState(false);
  const body = formatPayload(raw);
  const isJson = !!body && body.length < 60_000 && (() => { try { JSON.parse(body); return true; } catch { return false; } })();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  };
  return (
    <div className="ep-rl-bodyblock">
      <div className="ep-rl-bodyhead">
        <h4 className="ep-rl-subhead">{title}</h4>
        {body ? (
          <button type="button" className="ep-rl-copy" onClick={copy}>
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? "Copied" : "Copy"}
          </button>
        ) : null}
      </div>
      {body ? (
        isJson ? (
          <pre className="request-payload-pre" dangerouslySetInnerHTML={{ __html: highlightJson(body) }} />
        ) : (
          <pre className="request-payload-pre">{body}</pre>
        )
      ) : (
        <div className="endpoint-detail-empty">No body captured.</div>
      )}
    </div>
  );
}

/* ── Related tab ─────────────────────────────────────────────────────── */

const rowKey = (r: RequestItem) => `${r.timestamp}|${r.method}|${r.path}|${r.status_code}`;

function RelatedRow({
  r,
  current,
  onOpen,
  scrollRef,
}: {
  r: RequestItem;
  current: boolean;
  onOpen: (r: RequestItem) => void;
  scrollRef?: React.Ref<HTMLButtonElement>;
}) {
  return (
    <button
      type="button"
      ref={scrollRef}
      className={`ep-rel-row${current ? " is-current" : ""}`}
      onClick={() => { if (!current) onOpen(r); }}
      aria-current={current ? "true" : undefined}
    >
      <span className="ep-rel-time">{timeShort(r.timestamp)}</span>
      <span className={`endpoint-status-pill ${statusTone(r.status_code)}`}>{r.status_code}</span>
      <span className="ep-rel-method" style={{ color: methodColor(r.method) }}>{r.method}</span>
      <span className="ep-rel-path">{r.path}</span>
      {current && <span className="ep-rel-here">this request</span>}
      <span className="ep-rel-dur">{formatMs(r.response_time_ms)}</span>
    </button>
  );
}

function RelatedSection({
  title,
  rows,
  currentKey,
  onOpen,
  emptyMessage,
}: {
  title: string;
  rows: RequestItem[] | null;
  currentKey: string;
  onOpen: (r: RequestItem) => void;
  emptyMessage: string;
}) {
  const currentRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // Centre the highlighted (current) request within the list — scroll only the
  // list, not the whole modal.
  useEffect(() => {
    const el = currentRef.current;
    const list = listRef.current;
    if (el && list) {
      list.scrollTop = Math.max(0, el.offsetTop - list.clientHeight / 2 + el.clientHeight / 2);
    }
  }, [rows]);
  const count = rows ? rows.filter((r) => rowKey(r) !== currentKey).length : 0;
  return (
    <div className="ep-rl-headblock">
      <h4 className="ep-rl-subhead">
        {title}
        {count ? <span className="ep-rl-count">{count}</span> : null}
      </h4>
      {rows === null ? (
        <div className="endpoint-skeleton" style={{ height: 96 }} aria-hidden />
      ) : rows.length === 0 ? (
        <div className="endpoint-detail-empty">{emptyMessage}</div>
      ) : (
        <div className="ep-rel-list" ref={listRef}>
          {rows.map((r, i) => {
            const current = rowKey(r) === currentKey;
            return (
              <RelatedRow
                key={`${r.timestamp}-${i}`}
                r={r}
                current={current}
                onOpen={onOpen}
                scrollRef={current ? currentRef : undefined}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function RelatedTab({
  projectSlug,
  row,
  appSlugs,
  environment,
  since,
  until,
  onOpen,
}: {
  projectSlug: string;
  row: RequestItem;
  appSlugs: string[];
  environment?: string;
  since: string;
  until?: string;
  onOpen: (r: RequestItem) => void;
}) {
  const [sameEndpoint, setSameEndpoint] = useState<RequestItem[] | null>(null);
  const [sameConsumer, setSameConsumer] = useState<RequestItem[] | null>(null);
  const consumerKey = row.consumer_id || row.consumer_name || "";
  const currentKey = rowKey(row);

  // Keep the opened request in the list and show its chronological neighbours
  // (later requests above, earlier below — the list is newest-first).
  const windowAround = (items: RequestItem[]): RequestItem[] => {
    const list = items.slice();
    let ci = list.findIndex((r) => rowKey(r) === currentKey);
    if (ci < 0) {
      // The current request wasn't in the fetched window — inject it so it can
      // still be shown highlighted, placed by timestamp.
      list.push(row);
      list.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      ci = list.findIndex((r) => rowKey(r) === currentKey);
    }
    const start = Math.max(0, ci - 10);
    return list.slice(start, ci + 11);
  };

  useEffect(() => {
    let cancelled = false;
    const base = () => {
      const p = new URLSearchParams();
      p.set("since", since);
      if (until) p.set("until", until);
      if (environment) p.set("environment", environment);
      if (appSlugs.length) p.set("app_slugs", appSlugs.join(","));
      return p;
    };
    // Same endpoint (server-filtered by method + exact path).
    (async () => {
      const p = base();
      p.set("methods", row.method);
      p.set("path_filter", row.path);
      p.set("page_size", "200");
      try {
        const res = await fetch(`/api/projects/${projectSlug}/data/requests?${p.toString()}`);
        const data = res.ok ? await res.json() : { items: [] };
        if (cancelled) return;
        setSameEndpoint(windowAround(data.items || []));
      } catch { if (!cancelled) setSameEndpoint([]); }
    })();
    // Same consumer (no server-side consumer filter — match client-side over a
    // wider recent window).
    (async () => {
      if (!consumerKey) { setSameConsumer([]); return; }
      const p = base();
      p.set("page_size", "200");
      try {
        const res = await fetch(`/api/projects/${projectSlug}/data/requests?${p.toString()}`);
        const data = res.ok ? await res.json() : { items: [] };
        if (cancelled) return;
        const matches = (data.items || []).filter(
          (r: RequestItem) => (r.consumer_id || r.consumer_name) === consumerKey,
        );
        setSameConsumer(windowAround(matches));
      } catch { if (!cancelled) setSameConsumer([]); }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectSlug, row, appSlugs, environment, since, until, consumerKey]);

  return (
    <>
      <RelatedSection
        title="Same endpoint"
        rows={sameEndpoint}
        currentKey={currentKey}
        onOpen={onOpen}
        emptyMessage="No other requests to this endpoint in this period."
      />
      <RelatedSection
        title={consumerKey ? `From this consumer (${consumerKey})` : "From this consumer"}
        rows={sameConsumer}
        currentKey={currentKey}
        onOpen={onOpen}
        emptyMessage={consumerKey ? "No other requests from this consumer in this period." : "This request has no identified consumer."}
      />
    </>
  );
}

/* ── Trace tab ───────────────────────────────────────────────────────── */

function levelTone(level: string): string {
  const l = (level || "").toUpperCase();
  if (l === "ERROR" || l === "CRITICAL") return "endpoint-status-5xx";
  if (l === "WARNING") return "endpoint-status-4xx";
  if (l === "DEBUG") return "endpoint-status-3xx";
  return "endpoint-status-2xx";
}

function spanColor(kind: string, status: string): string {
  if (status === "error") return "#f87171";
  const k = (kind || "").toLowerCase();
  if (k === "server") return "#14b8a6";
  if (k === "http" || k === "client") return "#5A9CF8";
  if (k === "db") return "#f59e0b";
  return "#94a3b8";
}

// Depth of each span in the tree (root = 0); tolerates missing parents
// (e.g. the caller's span in another project) and cycles.
function spanDepths(spans: SpanItem[]): Map<string, number> {
  const byId = new Map(spans.map((s) => [s.span_id, s]));
  const depths = new Map<string, number>();
  for (const s of spans) {
    let depth = 0;
    let cur: SpanItem | undefined = s;
    const seen = new Set<string>();
    while (cur && cur.parent_span_id && byId.has(cur.parent_span_id) && !seen.has(cur.span_id) && depth < 8) {
      seen.add(cur.span_id);
      cur = byId.get(cur.parent_span_id);
      depth += 1;
    }
    depths.set(s.span_id, depth);
  }
  return depths;
}

function Waterfall({ spans }: { spans: SpanItem[] }) {
  const depths = spanDepths(spans);
  const starts = spans.map((s) => new Date(s.timestamp).getTime());
  const traceStart = Math.min(...starts);
  const traceEnd = Math.max(...spans.map((s, i) => starts[i] + Math.max(s.duration_ms, 0)));
  const total = Math.max(traceEnd - traceStart, 1);

  return (
    <div className="ep-rel-list">
      {spans.map((s, i) => {
        const left = Math.min(((starts[i] - traceStart) / total) * 100, 99);
        const width = Math.max(Math.min((Math.max(s.duration_ms, 0) / total) * 100, 100 - left), 0.75);
        const color = spanColor(s.kind, s.status);
        return (
          <div key={`${s.span_id}-${i}`} className="ep-trace-row">
            <span
              className="ep-trace-name"
              style={{ paddingLeft: (depths.get(s.span_id) || 0) * 14 }}
              title={`${s.name}${s.service_name ? ` · ${s.service_name}` : ""}`}
            >
              <span className="ep-trace-kind" style={{ color }}>{s.kind || "internal"}</span>
              {s.name}
            </span>
            <span className="ep-trace-track">
              <span className="ep-trace-bar" style={{ left: `${left}%`, width: `${width}%`, background: color }} />
            </span>
            <span className="ep-rel-dur">{formatMs(s.duration_ms)}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ── Modal ───────────────────────────────────────────────────────────── */

function LogsTab({
  projectSlug,
  row,
  appSlugs,
  environment,
  since,
  until,
}: {
  projectSlug: string;
  row: RequestItem;
  appSlugs: string[];
  environment?: string;
  since: string;
  until?: string;
}) {
  const [logs, setLogs] = useState<LogState>("loading");

  useEffect(() => {
    let cancelled = false;
    if (!row.trace_id) {
      setLogs([]);
      return () => { cancelled = true; };
    }
    setLogs("loading");
    (async () => {
      const p = new URLSearchParams();
      p.set("trace_id", row.trace_id || "");
      p.set("since", since);
      if (until) p.set("until", until);
      if (environment) p.set("environment", environment);
      if (appSlugs.length) p.set("app_slugs", appSlugs.join(","));
      p.set("page_size", "100");
      try {
        const res = await fetch(`/api/projects/${projectSlug}/data/logs?${p.toString()}`);
        if (!res.ok) {
          if (!cancelled) setLogs("error");
          return;
        }
        const data = await res.json();
        if (!cancelled) setLogs(data.items || []);
      } catch {
        if (!cancelled) setLogs("error");
      }
    })();
    return () => { cancelled = true; };
  }, [projectSlug, row.trace_id, appSlugs, environment, since, until]);

  if (logs === "loading") {
    return <div className="endpoint-skeleton" style={{ height: 160 }} aria-hidden />;
  }
  if (logs === "error") {
    return <div className="endpoint-detail-empty">Logs could not be loaded.</div>;
  }
  if (logs.length === 0) {
    return <div className="endpoint-detail-empty">No logs captured for this trace.</div>;
  }

  return (
    <div className="ep-rl-headblock">
      <h4 className="ep-rl-subhead">
        Trace logs
        <span className="ep-rl-count">{logs.length}</span>
      </h4>
      <div className="ep-log-list">
        {logs.map((log, index) => (
          <div key={`${log.timestamp}-${index}`} className={`ep-log-row level-${log.level.toLowerCase()}`}>
            <div className="ep-log-main">
              <span className="ep-log-level">{log.level}</span>
              <span className="ep-log-message">{log.message || "Log event"}</span>
            </div>
            <div className="ep-log-meta">
              <span>{formatDateTime(log.timestamp)}</span>
              {log.logger_name ? <span>{log.logger_name}</span> : null}
              {log.endpoint_method || log.endpoint_path ? <span>{`${log.endpoint_method} ${log.endpoint_path}`.trim()}</span> : null}
              {log.status_code ? <span>{log.status_code}</span> : null}
            </div>
            {log.payload ? <pre className="ep-log-payload">{formatPayload(log.payload)}</pre> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function TraceTab({
  projectSlug,
  row,
  appSlugs,
  environment,
  since,
  until,
}: {
  projectSlug: string;
  row: RequestItem;
  appSlugs: string[];
  environment?: string;
  since: string;
  until?: string;
}) {
  const [spans, setSpans] = useState<TraceState>("loading");

  useEffect(() => {
    let cancelled = false;
    if (!row.trace_id) {
      setSpans([]);
      return () => { cancelled = true; };
    }
    setSpans("loading");
    (async () => {
      const p = new URLSearchParams();
      p.set("trace_id", row.trace_id || "");
      p.set("since", since);
      if (until) p.set("until", until);
      if (environment) p.set("environment", environment);
      if (appSlugs.length) p.set("app_slugs", appSlugs.join(","));
      p.set("page_size", "200");
      try {
        const res = await fetch(`/api/projects/${projectSlug}/data/spans?${p.toString()}`);
        if (!res.ok) {
          if (!cancelled) setSpans("error");
          return;
        }
        const data = await res.json();
        if (!cancelled) setSpans(data.items || []);
      } catch {
        if (!cancelled) setSpans("error");
      }
    })();
    return () => { cancelled = true; };
  }, [projectSlug, row.trace_id, appSlugs, environment, since, until]);

  if (spans === "loading") {
    return <div className="endpoint-skeleton" style={{ height: 160 }} aria-hidden />;
  }
  if (spans === "error") {
    return <div className="endpoint-detail-empty">Trace spans could not be loaded.</div>;
  }
  if (spans.length === 0) {
    return <div className="endpoint-detail-empty">No spans captured for this trace.</div>;
  }

  return (
    <div className="ep-rl-headblock">
      <h4 className="ep-rl-subhead">
        Trace spans
        <span className="ep-rl-count">{spans.length}</span>
      </h4>
      <div className="ep-trace-list">
        {spans.map((span, index) => {
          const isCurrent = !!row.span_id && span.span_id === row.span_id;
          return (
            <div key={`${span.span_id}-${index}`} className={`ep-trace-row${isCurrent ? " is-current" : ""}`}>
              <div className="ep-trace-main">
                <span className={`endpoint-status-pill ${statusTone(span.status_code || 200)}`}>
                  {span.status || span.status_code || "OK"}
                </span>
                <span className="ep-trace-name">{span.name || "Unnamed span"}</span>
                {isCurrent ? <span className="ep-trace-current">request span</span> : null}
              </div>
              <div className="ep-trace-meta">
                <span><Server size={12} /> {span.service_name || "unknown service"}</span>
                <span><GitBranch size={12} /> {span.kind || "span"}</span>
                <span>{formatMs(span.duration_ms)}</span>
                <span>{formatDateTime(span.timestamp)}</span>
              </div>
              <div className="ep-trace-ids">
                <span>span {span.span_id}</span>
                {span.parent_span_id ? <span>parent {span.parent_span_id}</span> : <span>root span</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface Props {
  projectSlug: string;
  row: RequestItem;
  appSlugs?: string[];
  environment?: string;
  since: string;
  until?: string;
  onClose: () => void;
  onFilterConsumer?: (consumer: string) => void;
}

export default function RequestLogDetailModal({
  projectSlug,
  row,
  appSlugs = [],
  environment,
  since,
  until,
  onClose,
  onFilterConsumer,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>("details");
  const [payload, setPayload] = useState<PayloadRow | null | "loading">("loading");
  // A related request opened on top of this one (stacked modal).
  const [relatedOpen, setRelatedOpen] = useState<RequestItem | null>(null);
  const tabs = useMemo(() => (row.trace_id ? [...BASE_TABS, LOGS_TAB, TRACE_TAB] : BASE_TABS), [row.trace_id]);

  useEffect(() => {
    if ((activeTab === "logs" || activeTab === "trace") && !row.trace_id) {
      setActiveTab("details");
    }
  }, [activeTab, row.trace_id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // When a stacked child modal is open, let it handle Escape.
      if (e.key === "Escape" && !relatedOpen) {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose, relatedOpen]);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // Lazy-fetch the body/headers for this request via endpoint-requests
  // (the flat list query doesn't carry them). Match by closest timestamp.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const p = new URLSearchParams();
        p.set("method", row.method);
        p.set("path", row.path);
        if (appSlugs.length) p.set("app_slugs", appSlugs.join(","));
        if (environment) p.set("environment", environment);
        p.set("since", since);
        if (until) p.set("until", until);
        p.set("limit", "100");
        const res = await fetch(`/api/projects/${projectSlug}/analytics/endpoint-requests?${p.toString()}`);
        if (!res.ok) { if (!cancelled) setPayload(null); return; }
        const rows: PayloadRow[] = await res.json();
        const target = new Date(row.timestamp).getTime();
        let best: PayloadRow | null = null;
        let bestDiff = Infinity;
        for (const r of rows) {
          if (r.status_code !== row.status_code) continue;
          const diff = Math.abs(new Date(r.timestamp).getTime() - target);
          if (diff < bestDiff) { bestDiff = diff; best = r; }
        }
        if (!cancelled) setPayload(bestDiff <= 2000 ? best : null);
      } catch {
        if (!cancelled) setPayload(null);
      }
    })();
    return () => { cancelled = true; };
  }, [projectSlug, row, appSlugs, environment, since, until]);

  const consumer = row.consumer_name || row.consumer_id || "";
  // Filter on the stable identifier, not the display name.
  const consumerFilter = row.consumer_id || row.consumer_name || "";
  const stext = StatusText(row.status_code);
  const loadingPayload = payload === "loading";
  const pr = payload && payload !== "loading" ? payload : null;
  // The list row carries trace_id for fresh data; fall back to the lazily
  // fetched detail row (older list responses don't include it).
  const traceId = (row.trace_id || pr?.trace_id || "").trim();
  const [copiedTrace, setCopiedTrace] = useState(false);
  const copyTrace = async () => {
    try {
      await navigator.clipboard.writeText(traceId);
      setCopiedTrace(true);
      setTimeout(() => setCopiedTrace(false), 1500);
    } catch { /* clipboard unavailable */ }
  };

  const curl = useMemo(() => {
    const base = (pr?.base_url || "").replace(/\/$/, "") || "YOUR_BASE_URL";
    const body = formatPayload(pr?.request_payload);
    const lines = [`curl -X ${row.method} "${base}${row.path}"`];
    if (body) {
      lines.push(`  -H "Content-Type: application/json"`);
      lines.push(`  -d '${body.replace(/'/g, "'\\''")}'`);
    }
    return lines.join(" \\\n");
  }, [pr, row]);
  const [copiedCurl, setCopiedCurl] = useState(false);
  const copyCurl = async () => {
    try {
      await navigator.clipboard.writeText(curl);
      setCopiedCurl(true);
      setTimeout(() => setCopiedCurl(false), 1500);
    } catch { /* clipboard unavailable */ }
  };

  const content = (
    <div className="ep-emodal-overlay" onClick={onClose}>
      <div className="ep-emodal ep-emodal--narrow" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="ep-emodal-head">
          <div className="ep-emodal-id">
            <span className="ep-emodal-crumb">Request details</span>
            <span className={`endpoint-status-pill ${statusTone(row.status_code)}`}>{row.status_code}</span>
            <span className={`method-badge method-badge-${row.method.toLowerCase()}`}>{row.method}</span>
            <span className="ep-emodal-path">{row.path}</span>
          </div>
          <div className="ep-emodal-headactions">
            <button type="button" className="ep-rl-curl" onClick={copyCurl} title="Copy as cURL">
              {copiedCurl ? <Check size={13} /> : <Terminal size={13} />}
              <span>{copiedCurl ? "Copied" : "cURL"}</span>
            </button>
            <button type="button" className="ep-emodal-close" onClick={onClose} aria-label="Close">
              <X size={18} />
            </button>
          </div>
        </div>

        <nav className="ep-emodal-tabs" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={activeTab === t.key}
              className={`ep-emodal-tab${activeTab === t.key ? " is-active" : ""}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ep-emodal-body">
          {activeTab === "details" && (
            <>
              <div className="ep-rl-when">{formatDateTime(row.timestamp)}</div>
              <div className="ep-statcards ep-rl-metrics">
                <MetricCard label="Request size" icon={<ArrowUpFromLine size={16} />} value={formatBytes(row.request_size)} />
                <MetricCard label="Response size" icon={<ArrowDownToLine size={16} />} value={formatBytes(row.response_size)} />
                <MetricCard label="Response time" icon={<Timer size={16} />} value={formatMs(row.response_time_ms)} />
              </div>
              <div className="ep-rl-details">
                <DetailRow label="Status" value={`${row.status_code}${stext ? ` ${stext}` : ""}`} />
                {pr?.base_url ? <DetailRow label="Host" value={<span className="ep-rl-mono"><Server size={12} /> {pr.base_url}</span>} /> : null}
                <DetailRow label="Client" value={<span className="ep-rl-mono"><Globe size={12} /> {row.ip_address || "—"}{pr?.country ? ` (${pr.country})` : ""}</span>} />
                <DetailRow
                  label="Consumer"
                  value={
                    consumer ? (
                      onFilterConsumer ? (
                        <button
                          type="button"
                          className="ep-rl-mono ep-rl-consumer-link"
                          title={`Show all requests from ${consumer}`}
                          onClick={() => onFilterConsumer(consumerFilter)}
                        >
                          <Fingerprint size={12} /> {consumer}{row.consumer_group ? ` · ${row.consumer_group}` : ""}
                        </button>
                      ) : (
                        <span className="ep-rl-mono"><Fingerprint size={12} /> {consumer}{row.consumer_group ? ` · ${row.consumer_group}` : ""}</span>
                      )
                    ) : "—"
                  }
                />
                <DetailRow label="Environment" value={row.environment || "—"} />
                {traceId ? (
                  <DetailRow
                    label="Trace"
                    value={
                      <button
                        type="button"
                        className="ep-rl-mono ep-rl-consumer-link"
                        title="Copy trace id"
                        onClick={copyTrace}
                      >
                        <Link2 size={12} /> {traceId} {copiedTrace ? <Check size={12} /> : <Copy size={12} />}
                      </button>
                    }
                  />
                ) : null}
                {row.span_id ? <DetailRow label="Span ID" value={<span className="ep-rl-mono">{row.span_id}</span>} /> : null}
                {row.user_agent ? <DetailRow label="User agent" value={<span className="ep-rl-ua">{row.user_agent}</span>} /> : null}
              </div>
            </>
          )}

          {activeTab === "headers" && (
            loadingPayload ? (
              <div className="endpoint-skeleton" style={{ height: 160 }} aria-hidden />
            ) : (
              <>
                <HeadersList title="Request headers" raw={pr?.request_headers} />
                <HeadersList title="Response headers" raw={pr?.response_headers} />
              </>
            )
          )}

          {activeTab === "response" && (
            loadingPayload ? (
              <div className="endpoint-skeleton" style={{ height: 220 }} aria-hidden />
            ) : (
              <>
                <Body title="Request payload" raw={pr?.request_payload} />
                <Body title="Response payload" raw={pr?.response_payload} />
              </>
            )
          )}

          {activeTab === "related" && (
            <RelatedTab
              projectSlug={projectSlug}
              row={row}
              appSlugs={appSlugs}
              environment={environment}
              since={since}
              until={until}
              onOpen={setRelatedOpen}
            />
          )}

          {activeTab === "logs" && (
            <LogsTab
              projectSlug={projectSlug}
              row={row}
              appSlugs={appSlugs}
              environment={environment}
              since={since}
              until={until}
            />
          )}

          {activeTab === "trace" && (
            <TraceTab
              projectSlug={projectSlug}
              row={row}
              appSlugs={appSlugs}
              environment={environment}
              since={since}
              until={until}
            />
          )}
        </div>
      </div>

      {/* Stacked modal for a clicked related request */}
      {relatedOpen && (
        <RequestLogDetailModal
          projectSlug={projectSlug}
          row={relatedOpen}
          appSlugs={appSlugs}
          environment={environment}
          since={since}
          until={until}
          onClose={() => setRelatedOpen(null)}
        />
      )}
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(content, document.body);
}
