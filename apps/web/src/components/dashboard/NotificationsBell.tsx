"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check, X, Loader2, Users, AlertTriangle, Activity } from "lucide-react";

interface PendingInvitation {
  id: string;
  project_name: string;
  project_slug: string;
  role: string;
  inviter: string;
  created_at: string;
  expires_at: string;
}

interface AlertEvent {
  id: string;
  project_slug: string;
  project_name: string;
  app_slug: string;
  kind: "error_rate" | "latency";
  method: string;
  path: string;
  observed_value: number;
  baseline_value: number;
  threshold_value: number;
  status: string;
  created_at: string;
}

function formatAlertValues(alert: AlertEvent): string {
  if (alert.kind === "error_rate") {
    return `${alert.observed_value.toFixed(1)}% errors vs ${alert.baseline_value.toFixed(1)}% baseline`;
  }
  return `p95 ${Math.round(alert.observed_value)}ms vs ${Math.round(alert.baseline_value)}ms baseline`;
}

export default function NotificationsBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const fetchPending = useCallback(async () => {
    const [invRes, alertRes] = await Promise.allSettled([
      fetch("/api/projects/invitations/pending"),
      fetch("/api/projects/alerts/recent"),
    ]);
    try {
      if (invRes.status === "fulfilled" && invRes.value.ok) {
        const data = await invRes.value.json();
        setInvitations(Array.isArray(data.invitations) ? data.invitations : []);
      }
      if (alertRes.status === "fulfilled" && alertRes.value.ok) {
        const data = await alertRes.value.json();
        setAlerts(Array.isArray(data.alerts) ? data.alerts : []);
      }
    } catch {
      // silent — the bell is non-critical chrome
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    fetchPending();
    const onFocus = () => fetchPending();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetchPending]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleAccept = async (inv: PendingInvitation) => {
    setBusyId(inv.id);
    try {
      const res = await fetch(`/api/projects/invitations/${inv.id}/accept`, { method: "POST" });
      if (!res.ok) throw new Error();
      setInvitations((prev) => prev.filter((i) => i.id !== inv.id));
      setOpen(false);
      router.push(`/projects/${inv.project_slug}`);
      router.refresh();
    } catch {
      setBusyId(null);
    }
  };

  const handleDecline = async (inv: PendingInvitation) => {
    setBusyId(inv.id);
    try {
      const res = await fetch(`/api/projects/invitations/${inv.id}/decline`, { method: "POST" });
      if (!res.ok) throw new Error();
      setInvitations((prev) => prev.filter((i) => i.id !== inv.id));
    } catch {
      // leave it in the list so the user can retry
    } finally {
      setBusyId(null);
    }
  };

  const handleViewAlert = (alert: AlertEvent) => {
    setOpen(false);
    router.push(`/projects/${alert.project_slug}/traffic`);
  };

  const handleDismissAlert = async (alert: AlertEvent) => {
    setBusyId(alert.id);
    try {
      const res = await fetch(
        `/api/projects/${alert.project_slug}/alerts/${alert.id}/dismiss`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error();
      setAlerts((prev) => prev.filter((a) => a.id !== alert.id));
    } catch {
      // leave it in the list so the user can retry
    } finally {
      setBusyId(null);
    }
  };

  const count = invitations.length + alerts.length;

  return (
    <div className="notif-bell" ref={ref}>
      <button
        className="navbar-icon-btn"
        onClick={() => setOpen((v) => !v)}
        aria-label={count > 0 ? `${count} notifications` : "Notifications"}
      >
        <Bell size={18} />
        {count > 0 && <span className="notif-badge">{count > 9 ? "9+" : count}</span>}
      </button>

      {open && (
        <div className="dropdown-menu notif-dropdown">
          <div className="dropdown-header notif-header">
            <p className="dropdown-user-name">Notifications</p>
            {count > 0 && <span className="notif-header-count">{count} pending</span>}
          </div>

          {!loaded ? (
            <div className="notif-empty">
              <Loader2 size={16} className="animate-spin" />
              <span>Loading…</span>
            </div>
          ) : count === 0 ? (
            <div className="notif-empty">
              <Bell size={18} />
              <span>You&apos;re all caught up.</span>
            </div>
          ) : (
            <div className="notif-list">
              {alerts.map((alert) => (
                <div key={alert.id} className="notif-item">
                  <div className="notif-item-icon">
                    {alert.kind === "error_rate" ? <AlertTriangle size={15} /> : <Activity size={15} />}
                  </div>
                  <div className="notif-item-body">
                    <p className="notif-item-title">
                      {alert.kind === "error_rate" ? "Error rate anomaly" : "Latency anomaly"} on{" "}
                      <strong>{alert.method} {alert.path}</strong>
                    </p>
                    <p className="notif-item-sub">
                      {alert.project_name} · {formatAlertValues(alert)}
                    </p>
                    <div className="notif-item-actions">
                      <button
                        className="notif-btn notif-btn-accept"
                        onClick={() => handleViewAlert(alert)}
                        disabled={busyId === alert.id}
                      >
                        <Check size={12} />
                        View
                      </button>
                      <button
                        className="notif-btn notif-btn-decline"
                        onClick={() => handleDismissAlert(alert)}
                        disabled={busyId === alert.id}
                      >
                        {busyId === alert.id ? <Loader2 size={12} className="animate-spin" /> : <X size={12} />}
                        Dismiss
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {invitations.map((inv) => (
                <div key={inv.id} className="notif-item">
                  <div className="notif-item-icon">
                    <Users size={15} />
                  </div>
                  <div className="notif-item-body">
                    <p className="notif-item-title">
                      {inv.inviter ? <strong>{inv.inviter}</strong> : "Someone"} invited you to{" "}
                      <strong>{inv.project_name}</strong>
                    </p>
                    <p className="notif-item-sub">Role: {inv.role}</p>
                    <div className="notif-item-actions">
                      <button
                        className="notif-btn notif-btn-accept"
                        onClick={() => handleAccept(inv)}
                        disabled={busyId === inv.id}
                      >
                        {busyId === inv.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                        Accept
                      </button>
                      <button
                        className="notif-btn notif-btn-decline"
                        onClick={() => handleDecline(inv)}
                        disabled={busyId === inv.id}
                      >
                        <X size={12} />
                        Decline
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
