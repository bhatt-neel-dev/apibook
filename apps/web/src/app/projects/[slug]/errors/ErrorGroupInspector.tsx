"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Clock, Copy, Fingerprint } from "lucide-react";
import Inspector from "@/components/aperture/Inspector";
import { fmtNum } from "@/lib/format";
import { formatDateTime, statusTone, timeAgo } from "../endpoints/detail/sections";
import { type ErrorEvent, type ErrorGroup, type OccurrenceRow, reasonPhrase, splitException } from "./util";

function MetaItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="err-meta-item">
      <span className="err-meta-label">{label}</span>
      <span className="err-meta-value">{value}</span>
    </div>
  );
}

export default function ErrorGroupInspector({
  projectSlug,
  group,
  since,
  until,
  environment,
  onClose,
}: {
  projectSlug: string;
  group: ErrorGroup;
  since: string;
  until: string;
  environment?: string;
  onClose: () => void;
}) {
  const [occurrences, setOccurrences] = useState<OccurrenceRow[] | null>(null);
  const [stackEvent, setStackEvent] = useState<ErrorEvent | null>(null);
  const [copied, setCopied] = useState(false);
  const reqId = useRef(0);

  const isServer = group.status_code >= 500;

  useEffect(() => {
    const myId = ++reqId.current;
    const base = () => {
      const p = new URLSearchParams();
      p.set("since", since);
      p.set("until", until);
      if (environment) p.set("environment", environment);
      p.set("method", group.method);
      p.set("path", group.path);
      return p;
    };
    // Occurrences from the request log (works for 4xx and 5xx), filtered to this status.
    (async () => {
      const p = base();
      p.set("errors_only", "true");
      p.set("limit", "80");
      try {
        const res = await fetch(`/api/projects/${projectSlug}/analytics/endpoint-requests?${p.toString()}`);
        const data = res.ok ? ((await res.json()) as OccurrenceRow[]) : [];
        const rows = (Array.isArray(data) ? data : []).filter((r) => r.status_code === group.status_code);
        if (myId === reqId.current) setOccurrences(rows);
      } catch {
        if (myId === reqId.current) setOccurrences([]);
      }
    })();
    // Stack trace (5xx only) from the exception logs.
    if (isServer) {
      (async () => {
        const p = base();
        p.set("limit", "20");
        try {
          const res = await fetch(`/api/projects/${projectSlug}/analytics/error-events?${p.toString()}`);
          const data = res.ok ? ((await res.json()) as ErrorEvent[]) : [];
          const withTrace = (Array.isArray(data) ? data : []).find(
            (e) => e.status_code === group.status_code && e.payload && e.payload.trim(),
          );
          if (myId === reqId.current) setStackEvent(withTrace || null);
        } catch {
          if (myId === reqId.current) setStackEvent(null);
        }
      })();
    } else {
      setStackEvent(null);
    }
  }, [projectSlug, group.method, group.path, group.status_code, since, until, environment, isServer]);

  const consumers = useMemo(() => {
    const seen = new Set<string>();
    for (const o of occurrences || []) {
      const name = o.consumer || o.consumer_id || "";
      if (name && name !== "unknown") seen.add(name);
    }
    return Array.from(seen);
  }, [occurrences]);

  const stack = stackEvent?.payload || "";
  const { type } = splitException(stackEvent?.message || "");

  const copyStack = async () => {
    try {
      await navigator.clipboard.writeText(stack);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  };

  return (
    <Inspector
      width={680}
      onClose={onClose}
      title={
        <div className="err-insp-title">
          <span className={`endpoint-status-pill ${statusTone(group.status_code)}`}>{group.status_code}</span>
          <span className="err-insp-msg">{reasonPhrase(group.status_code)}</span>
        </div>
      }
    >
      <div className="err-insp-endpoint">
        <span className={`method-badge method-badge-${group.method.toLowerCase()}`}>{group.method}</span>
        <span className="err-insp-path">{group.path}</span>
      </div>

      <div className="err-meta-grid">
        <MetaItem label="Occurrences" value={fmtNum(group.occurrences)} />
        <MetaItem label="Consumers" value={fmtNum(group.consumers)} />
        <MetaItem label="Last seen" value={timeAgo(group.last_seen)} />
        <MetaItem label="Status" value={`${group.status_code} · ${reasonPhrase(group.status_code)}`} />
      </div>

      {/* Stack trace — the hero for server errors */}
      <div className="err-insp-section">
        <div className="err-insp-section-head">
          <h3>{type ? `Exception · ${type}` : "Stack trace"}</h3>
          {stack ? (
            <button type="button" className="ep-rl-copy" onClick={copyStack}>
              {copied ? <Check size={12} /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy"}
            </button>
          ) : null}
        </div>
        {stack ? (
          <pre className="request-payload-pre ep-log-trace">{stack}</pre>
        ) : (
          <p className="err-insp-note">
            {isServer
              ? "No captured exception traceback for this server error."
              : "Client error — no exception or stack trace is captured for 4xx responses."}
          </p>
        )}
      </div>

      {/* Affected consumers */}
      {consumers.length > 0 ? (
        <div className="err-insp-section">
          <div className="err-insp-section-head"><h3>Consumers affected</h3></div>
          <div className="err-consumer-chips">
            {consumers.map((c) => (
              <span key={c} className="err-consumer-chip"><Fingerprint size={12} />{c}</span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Recent occurrences */}
      <div className="err-insp-section">
        <div className="err-insp-section-head"><h3>Recent occurrences</h3></div>
        {occurrences === null ? (
          <p className="err-insp-note">Loading…</p>
        ) : occurrences.length === 0 ? (
          <p className="err-insp-note">No occurrences in this period.</p>
        ) : (
          <ul className="err-occ-list">
            {occurrences.map((o, i) => (
              <li key={`${o.trace_id}-${o.timestamp}-${i}`} className="err-occ">
                <span className="err-occ-time"><Clock size={12} />{formatDateTime(o.timestamp)}</span>
                <span className="err-occ-consumer">{o.consumer && o.consumer !== "unknown" ? o.consumer : "—"}</span>
                {o.trace_id ? <code className="err-occ-trace" title="Trace ID">{o.trace_id.slice(0, 12)}</code> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Inspector>
  );
}
