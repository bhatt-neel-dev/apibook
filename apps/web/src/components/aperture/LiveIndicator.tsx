"use client";

import { useEffect, useState } from "react";

/**
 * Pulsing "LIVE" pill that doubles as the play/pause control for a live-polling
 * surface, with an "updated Ns ago" caption. Wire it to `useLivePoll` state:
 *
 *   const poll = useLivePoll({ onTick: silentRefetch, deps: [...] });
 *   <LiveIndicator live={poll.live} onToggle={poll.toggle} lastTickAt={poll.lastTickAt} />
 */
export interface LiveIndicatorProps {
  live: boolean;
  onToggle: () => void;
  /** Timestamp (ms) of the last successful update, or null. */
  lastTickAt: number | null;
  className?: string;
}

function agoLabel(lastTickAt: number | null, now: number): string {
  if (lastTickAt == null) return "";
  const secs = Math.max(0, Math.round((now - lastTickAt) / 1000));
  if (secs < 2) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  return `${mins}m ago`;
}

export default function LiveIndicator({
  live,
  onToggle,
  lastTickAt,
  className = "",
}: LiveIndicatorProps) {
  // Re-render once a second so the "Ns ago" caption stays current.
  const [now, setNow] = useState<number>(() => lastTickAt ?? 0);
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live]);
  // Keep `now` fresh right after a tick even between the 1s ticks above.
  useEffect(() => {
    if (lastTickAt != null) setNow(Date.now());
  }, [lastTickAt]);

  const ago = live ? agoLabel(lastTickAt, now) : "Paused";

  return (
    <button
      type="button"
      className={`live-ind${live ? " is-live" : " is-paused"} ${className}`}
      onClick={onToggle}
      aria-pressed={live}
      title={live ? "Live — click to pause" : "Paused — click to go live"}
    >
      <span className="live-dot" aria-hidden />
      <span className="live-label">{live ? "LIVE" : "PAUSED"}</span>
      {ago && <span className="live-ago">{ago}</span>}
    </button>
  );
}
