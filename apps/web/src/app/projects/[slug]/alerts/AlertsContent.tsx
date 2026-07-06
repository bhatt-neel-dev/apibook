"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Activity, AlertTriangle, BellOff, Loader2, X } from "lucide-react";

interface AlertsContentProps {
  projectSlug: string;
}

interface AlertEvent {
  id: string;
  project_slug: string;
  app_slug: string;
  kind: "error_rate" | "latency";
  method: string;
  path: string;
  observed_value: number;
  baseline_value: number;
  threshold_value: number;
  status: "active" | "dismissed";
  window_start: string;
  window_end: string;
  created_at: string;
}

type StatusFilter = "active" | "dismissed" | "all";

const FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "active", label: "Active" },
  { id: "dismissed", label: "Dismissed" },
  { id: "all", label: "All" },
];

function formatValues(alert: AlertEvent): string {
  if (alert.kind === "error_rate") {
    return `${alert.observed_value.toFixed(1)}% errors (baseline ${alert.baseline_value.toFixed(1)}%, threshold ${alert.threshold_value.toFixed(1)}%)`;
  }
  return `p95 ${Math.round(alert.observed_value)}ms (baseline ${Math.round(alert.baseline_value)}ms, threshold ${Math.round(alert.threshold_value)}ms)`;
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function AlertsContent({ projectSlug }: AlertsContentProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active");
  const [alerts, setAlerts] = useState<AlertEvent[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    setAlerts(null);
    try {
      const res = await fetch(
        `/api/projects/${projectSlug}/alerts?status=${statusFilter}`,
      );
      if (!res.ok) {
        setAlerts([]);
        return;
      }
      const data = await res.json();
      setAlerts(Array.isArray(data.alerts) ? data.alerts : []);
    } catch {
      setAlerts([]);
    }
  }, [projectSlug, statusFilter]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const handleDismiss = async (alert: AlertEvent) => {
    setBusyId(alert.id);
    try {
      const res = await fetch(
        `/api/projects/${projectSlug}/alerts/${alert.id}/dismiss`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error();
      if (statusFilter === "active") {
        setAlerts((prev) => (prev ? prev.filter((a) => a.id !== alert.id) : prev));
      } else {
        setAlerts((prev) =>
          prev
            ? prev.map((a) => (a.id === alert.id ? { ...a, status: "dismissed" as const } : a))
            : prev,
        );
      }
    } catch {
      // leave the row so the user can retry
    } finally {
      setBusyId(null);
    }
  };

  const handleInvestigate = (alert: AlertEvent) => {
    // Same fire-and-forget view tracking as the bell — feeds the FP metric.
    fetch(`/api/projects/${projectSlug}/alerts/${alert.id}/seen`, { method: "POST" }).catch(() => {});
  };

  return (
    <div className="apps-page">
      <div className="apps-page-header">
        <h1 className="apps-page-title">Alerts</h1>
        <div className="alerts-filter-tabs">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              className={`settings-btn ${statusFilter === f.id ? "settings-btn-primary" : ""}`}
              onClick={() => setStatusFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {alerts === null ? (
        <div className="apps-page-loading">
          <Loader2 size={24} strokeWidth={2} className="animate-spin" />
        </div>
      ) : alerts.length === 0 ? (
        <div className="apps-empty">
          <div className="apps-empty-icon">
            <BellOff size={28} />
          </div>
          <h2 className="apps-empty-title">
            {statusFilter === "active" ? "No active alerts" : "No alerts"}
          </h2>
          <p className="apps-empty-text">
            Anomalies are detected automatically when an endpoint&apos;s error rate or
            latency deviates from its own rolling baseline — no thresholds to configure.
          </p>
        </div>
      ) : (
        <div className="apps-table-wrapper">
          <table className="apps-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Endpoint</th>
                <th>Deviation</th>
                <th>Detected</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id} className="apps-table-row">
                  <td>
                    <span className="alerts-kind">
                      {alert.kind === "error_rate" ? (
                        <AlertTriangle size={14} />
                      ) : (
                        <Activity size={14} />
                      )}
                      {alert.kind === "error_rate" ? "Error rate" : "Latency"}
                    </span>
                  </td>
                  <td>
                    <Link
                      href={`/projects/${projectSlug}/traffic`}
                      onClick={() => handleInvestigate(alert)}
                    >
                      <strong>{alert.method}</strong> {alert.path}
                    </Link>
                  </td>
                  <td>{formatValues(alert)}</td>
                  <td>{formatWhen(alert.created_at)}</td>
                  <td>
                    <span className={`alerts-status alerts-status-${alert.status}`}>
                      {alert.status}
                    </span>
                  </td>
                  <td>
                    {alert.status === "active" && (
                      <button
                        className="settings-btn"
                        onClick={() => handleDismiss(alert)}
                        disabled={busyId === alert.id}
                      >
                        {busyId === alert.id ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <X size={12} />
                        )}
                        Dismiss
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
