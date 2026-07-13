"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Drives a "live" refetch loop for dashboard surfaces.
 *
 * This hook owns *timing*, not data — it calls `onTick` on an interval and the
 * caller re-fetches with its own logic (usually a silent refetch that does NOT
 * flip a loading skeleton). That keeps the numbers ticking without the page
 * flashing on every poll.
 *
 * Behaviour:
 *  - Ticks every `intervalMs` while `live` is true and the tab is visible.
 *  - Auto-pauses when the tab is hidden (no wasted ClickHouse queries in the
 *    background) and fires one immediate catch-up tick when it becomes visible
 *    again, so you never stare at stale numbers on return.
 *  - Restarts cleanly when `deps` change (e.g. a new time range / filter) so the
 *    next tick reflects the new query.
 */
export interface UseLivePollOptions {
  /** Whether polling is initially on. Default true. */
  initialLive?: boolean;
  /** Poll cadence in ms. Default 5000. */
  intervalMs?: number;
  /** Called on every tick — do the (silent) refetch here. */
  onTick: () => void;
  /** Changing any dep restarts the loop (does not itself trigger a tick). */
  deps?: readonly unknown[];
}

export interface LivePollState {
  live: boolean;
  setLive: (v: boolean) => void;
  toggle: () => void;
  /** Timestamp (ms) of the last tick that fired, or null before the first. */
  lastTickAt: number | null;
  /** Force an immediate tick and reset the interval. */
  pokeNow: () => void;
}

export function useLivePoll({
  initialLive = true,
  intervalMs = 5000,
  onTick,
  deps = [],
}: UseLivePollOptions): LivePollState {
  const [live, setLive] = useState(initialLive);
  const [lastTickAt, setLastTickAt] = useState<number | null>(null);

  // Keep the latest onTick without re-arming the interval every render.
  const onTickRef = useRef(onTick);
  useEffect(() => {
    onTickRef.current = onTick;
  }, [onTick]);

  const fire = useCallback(() => {
    onTickRef.current();
    setLastTickAt(Date.now());
  }, []);

  const pokeNow = useCallback(() => {
    fire();
  }, [fire]);

  useEffect(() => {
    if (!live) return;

    let id: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (id != null) return;
      id = setInterval(() => {
        // Guard again in case visibility flipped between ticks.
        if (typeof document !== "undefined" && document.hidden) return;
        fire();
      }, intervalMs);
    };
    const stop = () => {
      if (id != null) {
        clearInterval(id);
        id = null;
      }
    };

    const onVisibility = () => {
      if (typeof document !== "undefined" && document.hidden) {
        stop();
      } else {
        fire(); // immediate catch-up
        start();
      }
    };

    if (typeof document !== "undefined" && !document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // `fire` is stable; deps restart the loop for a new query. intervalMs/live
    // re-arm as needed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, intervalMs, fire, ...deps]);

  const toggle = useCallback(() => setLive((v) => !v), []);

  return { live, setLive, toggle, lastTickAt, pokeNow };
}
