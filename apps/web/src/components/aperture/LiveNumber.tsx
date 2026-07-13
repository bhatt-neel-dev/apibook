"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A number that rolls to its new value like an odometer, flashes green/red on
 * change, and pops a floating delta chip (▲ +44 / ▼ -0.2).
 *
 * The caller passes the raw numeric `value` plus a `format` fn (reuse the shared
 * helpers in lib/format.ts). Formatting stays external so the odometer and the
 * rest of the page always agree on how a value reads.
 *
 * Motion respects `prefers-reduced-motion`: reduced users get an instant,
 * flash-free swap that still updates `aria-live` for screen readers.
 */
export interface LiveNumberProps {
  value: number;
  format: (n: number) => string;
  /**
   * Flip the up/down color semantics. Default: increase = good (green).
   * Set true for metrics where lower is better (error rate, latency) so a
   * decrease reads green.
   */
  invertTone?: boolean;
  /** Hide the floating delta chip (keep roll + flash only). */
  hideDelta?: boolean;
  className?: string;
}

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** One odometer column: a vertical 0–9 strip translated to show `digit`. */
function OdometerDigit({ digit }: { digit: number }) {
  return (
    <span className="ln-digit" aria-hidden>
      <span
        className="ln-digit-strip"
        style={{ transform: `translateY(-${digit}em)` }}
      >
        {DIGITS.map((d) => (
          <span key={d} className="ln-digit-cell">
            {d}
          </span>
        ))}
      </span>
    </span>
  );
}

export default function LiveNumber({
  value,
  format,
  invertTone = false,
  hideDelta = false,
  className = "",
}: LiveNumberProps) {
  const reduced = usePrefersReducedMotion();
  const prevRef = useRef<number | null>(null);

  // Pulse state drives the flash + floating chip; `id` re-triggers the CSS
  // animation each change even when direction repeats.
  const [pulse, setPulse] = useState<{
    id: number;
    dir: "up" | "down";
    delta: number;
  } | null>(null);
  const pulseId = useRef(0);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;
    if (prev == null || prev === value || reduced) return;
    const delta = value - prev;
    pulseId.current += 1;
    setPulse({ id: pulseId.current, dir: delta > 0 ? "up" : "down", delta });
    const t = setTimeout(() => {
      setPulse((p) => (p && p.id === pulseId.current ? null : p));
    }, 1000);
    return () => clearTimeout(t);
  }, [value, reduced]);

  const text = format(value);

  // Reduced motion: plain, instant, still announced.
  if (reduced) {
    return (
      <span className={`ln ${className}`} aria-live="polite">
        {text}
      </span>
    );
  }

  // Semantic tone: for invertTone metrics, "down" is the good direction.
  const goodDir = invertTone ? "down" : "up";
  const toneClass = pulse
    ? pulse.dir === goodDir
      ? "ln-flash-good"
      : "ln-flash-bad"
    : "";

  // Render the formatted string char-by-char. Digits roll; separators/units are
  // static. Keys are distance-from-right so stable low-order digits keep their
  // odometer column (and its transition) when the number grows a digit.
  const chars = text.split("");
  const n = chars.length;

  const deltaChip =
    pulse && !hideDelta ? (
      <span
        key={pulse.id}
        className={`ln-chip ${pulse.dir === goodDir ? "ln-chip-good" : "ln-chip-bad"}`}
        aria-hidden
      >
        {pulse.dir === "up" ? "▲" : "▼"} {format(Math.abs(pulse.delta))}
      </span>
    ) : null;

  return (
    <span className={`ln ${toneClass} ${className}`} aria-live="polite">
      <span className="ln-track" aria-hidden>
        {chars.map((ch, i) => {
          const keyFromRight = n - 1 - i;
          if (ch >= "0" && ch <= "9") {
            return (
              <OdometerDigit key={`d${keyFromRight}`} digit={Number(ch)} />
            );
          }
          return (
            <span key={`s${keyFromRight}-${ch}`} className="ln-sep">
              {ch === " " ? " " : ch}
            </span>
          );
        })}
      </span>
      {/* Accessible plain value for screen readers (the odometer is aria-hidden). */}
      <span className="ln-sr">{text}</span>
      {deltaChip}
    </span>
  );
}
