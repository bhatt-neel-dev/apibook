"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check, Loader2, Users, X } from "lucide-react";

interface PendingInvitation {
  id: string;
  project_name: string;
  project_slug: string;
  role: string;
  inviter: string;
  created_at: string;
  expires_at: string;
}

export default function NotificationsPageContent() {
  const router = useRouter();
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");

  const fetchPending = useCallback(async () => {
    setError("");
    try {
      const res = await fetch("/api/projects/invitations/pending");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Failed to load notifications");
      setInvitations(Array.isArray(data.invitations) ? data.invitations : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notifications");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPending();
  }, [fetchPending]);

  const acceptInvitation = async (invitation: PendingInvitation) => {
    setBusyId(invitation.id);
    setError("");
    try {
      const res = await fetch(`/api/projects/invitations/${invitation.id}/accept`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Failed to accept invitation");
      router.push(`/projects/${data.project_slug || invitation.project_slug}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to accept invitation");
      setBusyId(null);
    }
  };

  const declineInvitation = async (invitation: PendingInvitation) => {
    setBusyId(invitation.id);
    setError("");
    try {
      const res = await fetch(`/api/projects/invitations/${invitation.id}/decline`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Failed to decline invitation");
      setInvitations((prev) => prev.filter((item) => item.id !== invitation.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to decline invitation");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="apps-page">
      <div className="apps-page-header">
        <h1 className="apps-page-title">Notifications</h1>
        <button
          type="button"
          className="settings-btn settings-btn-secondary"
          onClick={() => void fetchPending()}
          disabled={isLoading}
        >
          {isLoading ? <Loader2 size={14} className="animate-spin" /> : null}
          Refresh
        </button>
      </div>

      {error ? <div className="create-app-error">{error}</div> : null}

      {isLoading ? (
        <div className="apps-page-loading">
          <Loader2 size={24} className="animate-spin" />
          <span>Loading notifications...</span>
        </div>
      ) : invitations.length === 0 ? (
        <div className="apps-empty">
          <div className="apps-empty-icon">
            <Bell size={32} />
          </div>
          <h2 className="apps-empty-title">No notifications</h2>
          <p className="apps-empty-text">You are all caught up.</p>
        </div>
      ) : (
        <div className="apps-grid">
          {invitations.map((invitation) => (
            <div className="app-card" key={invitation.id}>
              <div className="app-card-header">
                <h3 className="app-card-name">{invitation.project_name}</h3>
              </div>
              <p className="app-card-description">
                {invitation.inviter || "Someone"} invited you as {invitation.role}.
              </p>
              <div className="create-app-actions">
                <button
                  type="button"
                  className="settings-btn settings-btn-primary"
                  onClick={() => void acceptInvitation(invitation)}
                  disabled={busyId === invitation.id}
                >
                  {busyId === invitation.id ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                  Accept
                </button>
                <button
                  type="button"
                  className="settings-btn settings-btn-secondary"
                  onClick={() => void declineInvitation(invitation)}
                  disabled={busyId === invitation.id}
                >
                  <X size={14} />
                  Decline
                </button>
              </div>
              <div className="app-card-meta-row">
                <span className="app-card-meta">
                  <Users size={12} />
                  {invitation.project_slug}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
