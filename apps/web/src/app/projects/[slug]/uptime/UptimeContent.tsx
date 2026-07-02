"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Clock3, RefreshCw, RadioTower, WifiOff } from "lucide-react";
import StatStrip, { type Stat } from "@/components/aperture/StatStrip";
import StatusPill from "@/components/aperture/StatusPill";

type UptimeStatus = "live" | "stale" | "down" | "no_data";

interface EnvironmentStatus {
  environment: string;
  status: UptimeStatus;
  age_seconds: number | null;
  last_seen_at: string | null;
  requests_24h: number;
}

interface AppStatus {
  id: string;
  name: string;
  slug: string;
  framework: string;
  status: UptimeStatus;
  age_seconds: number | null;
  last_seen_at: string | null;
  requests_24h: number;
  environments: EnvironmentStatus[];
}

interface UptimeResponse {
  generated_at: string;
  heartbeat_grace_minutes: number;
  down_after_minutes: number;
  lookback_days: number;
  latest_seen_at: string | null;
  total_apps: number;
  summary: Record<UptimeStatus, number>;
  apps: AppStatus[];
}

interface Props {
  projectSlug: string;
}

const EMPTY_SUMMARY: Record<UptimeStatus, number> = {
  live: 0,
  stale: 0,
  down: 0,
  no_data: 0,
};

const STATUS_LABEL: Record<UptimeStatus, string> = {
  live: "Live",
  stale: "Stale",
  down: "Down",
  no_data: "No data",
};

const STATUS_TONE: Record<UptimeStatus, "healthy" | "warn" | "critical" | "neutral"> = {
  live: "healthy",
  stale: "warn",
  down: "critical",
  no_data: "neutral",
};

function formatAge(ageSeconds: number | null): string {
  if (ageSeconds === null) return "-";
  if (ageSeconds < 60) return `${ageSeconds}s`;
  const minutes = Math.floor(ageSeconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusSort(status: UptimeStatus): number {
  if (status === "down") return 0;
  if (status === "stale") return 1;
  if (status === "no_data") return 2;
  return 3;
}

function StatusBadge({ status }: { status: UptimeStatus }) {
  return (
    <StatusPill tone={STATUS_TONE[status]}>
      {STATUS_LABEL[status]}
    </StatusPill>
  );
}

export default function UptimeContent({ projectSlug }: Props) {
  const [data, setData] = useState<UptimeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const fetchUptime = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        heartbeat_grace_minutes: "2",
        down_after_minutes: "15",
        lookback_days: "30",
      });
      const res = await fetch(`/api/projects/${projectSlug}/analytics/uptime?${params.toString()}`);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(body.error || "Failed to load uptime");
      }
      setData(body as UptimeResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load uptime");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [projectSlug]);

  useEffect(() => {
    void fetchUptime();
  }, [fetchUptime, refreshKey]);

  const apps = useMemo(
    () => [...(data?.apps || [])].sort((a, b) => statusSort(a.status) - statusSort(b.status) || a.name.localeCompare(b.name)),
    [data],
  );

  const summary = data?.summary || EMPTY_SUMMARY;
  const stats: Stat[] = [
    { label: "Live", value: String(summary.live), sub: "fresh heartbeat", tone: "good" },
    { label: "Stale", value: String(summary.stale), sub: "late signal", tone: summary.stale ? "warn" : undefined },
    { label: "Down", value: String(summary.down), sub: `>${data?.down_after_minutes || 15} min`, tone: summary.down ? "bad" : undefined },
    { label: "No data", value: String(summary.no_data), sub: `${data?.lookback_days || 30}d window` },
  ];

  const generatedLabel = data?.generated_at ? formatDateTime(data.generated_at) : "-";

  return (
    <div className="uptime-page" data-testid="uptime-page">
      <div className="ep-rl-toolbar">
        <h1 className="ep-rl-title">Uptime</h1>
        <div className="ep-rl-spacer" />
        <span className="uptime-generated">
          <Clock3 size={13} />
          {generatedLabel}
        </span>
        <button
          type="button"
          className="tf-refresh"
          onClick={() => setRefreshKey((key) => key + 1)}
          title="Refresh"
          aria-label="Refresh"
        >
          <RefreshCw size={14} className={loading ? "tf-spin" : ""} />
        </button>
      </div>

      <StatStrip stats={stats} className="uptime-stats" />

      <section className="uptime-panel">
        {loading && !data ? (
          <div className="ep-rl-message">Loading uptime...</div>
        ) : error ? (
          <div className="uptime-empty uptime-empty-error">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        ) : apps.length === 0 ? (
          <div className="uptime-empty">
            <RadioTower size={20} />
            <span>No apps in this project.</span>
          </div>
        ) : (
          <div className="uptime-table-wrap">
            <table className="uptime-table">
              <thead>
                <tr>
                  <th>App</th>
                  <th>Status</th>
                  <th>Environments</th>
                  <th className="ep-th-num">Last signal</th>
                  <th className="ep-th-num">Age</th>
                  <th className="ep-th-num">24h requests</th>
                </tr>
              </thead>
              <tbody>
                {apps.map((app) => (
                  <tr key={app.id} data-testid={`uptime-app-${app.slug}`}>
                    <td>
                      <div className="uptime-app-cell">
                        <span className="uptime-app-avatar">{app.name.charAt(0).toUpperCase()}</span>
                        <span>
                          <span className="uptime-app-name">{app.name}</span>
                          <span className="uptime-app-meta">{app.slug} / {app.framework}</span>
                        </span>
                      </div>
                    </td>
                    <td><StatusBadge status={app.status} /></td>
                    <td>
                      {app.environments.length > 0 ? (
                        <div className="uptime-env-list">
                          {app.environments.map((env) => (
                            <span key={`${app.id}-${env.environment}`} className="uptime-env-chip">
                              <span className={`uptime-dot status-${env.status}`} />
                              {env.environment}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="uptime-muted"><WifiOff size={13} /> none</span>
                      )}
                    </td>
                    <td className="ep-td-num">{formatDateTime(app.last_seen_at)}</td>
                    <td className="ep-td-num">{formatAge(app.age_seconds)}</td>
                    <td className="ep-td-num">{app.requests_24h.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
