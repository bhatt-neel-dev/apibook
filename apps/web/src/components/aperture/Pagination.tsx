"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

/**
 * Windowed page list: always shows the first + last page and the current
 * page's immediate neighbours, collapsing the rest into "gap" markers. So a
 * 100-page set on page 6 renders  1 … 5 6 7 … 100 — the last page (and a jump
 * box) are always one click away instead of 99 Next presses.
 */
function getPages(current: number, total: number): Array<number | "gap"> {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: Array<number | "gap"> = [1];
  const left = Math.max(2, current - 1);
  const right = Math.min(total - 1, current + 1);
  if (left > 2) pages.push("gap");
  for (let p = left; p <= right; p++) pages.push(p);
  if (right < total - 1) pages.push("gap");
  pages.push(total);
  return pages;
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  className?: string;
}

export default function Pagination({ page, totalPages, onChange, className }: PaginationProps) {
  const [jump, setJump] = useState("");
  if (totalPages <= 1) return null;

  const go = (p: number) => {
    const clamped = Math.max(1, Math.min(totalPages, Math.round(p)));
    if (clamped !== page) onChange(clamped);
  };

  const submitJump = () => {
    const n = parseInt(jump, 10);
    if (!Number.isNaN(n)) go(n);
    setJump("");
  };

  return (
    <div className={`ap-pager${className ? ` ${className}` : ""}`}>
      <button
        type="button"
        className="ap-pager-arrow"
        disabled={page <= 1}
        onClick={() => go(page - 1)}
        aria-label="Previous page"
      >
        <ChevronLeft size={15} />
      </button>

      <div className="ap-pager-pages">
        {getPages(page, totalPages).map((p, i) =>
          p === "gap" ? (
            <span key={`gap-${i}`} className="ap-pager-gap" aria-hidden>
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              className={`ap-pager-num${p === page ? " is-active" : ""}`}
              aria-current={p === page ? "page" : undefined}
              aria-label={`Page ${p}`}
              onClick={() => go(p)}
            >
              {p}
            </button>
          ),
        )}
      </div>

      <button
        type="button"
        className="ap-pager-arrow"
        disabled={page >= totalPages}
        onClick={() => go(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight size={15} />
      </button>

      {totalPages > 7 && (
        <div className="ap-pager-jump">
          <span>Go to</span>
          <input
            type="number"
            min={1}
            max={totalPages}
            value={jump}
            placeholder="#"
            onChange={(e) => setJump(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submitJump();
              }
            }}
            onBlur={submitJump}
            aria-label="Jump to page"
          />
        </div>
      )}
    </div>
  );
}
