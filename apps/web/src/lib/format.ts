// Shared number/byte formatters used across the dashboard.
// Lifted out of the Traffic page so the live-number primitives and the pages
// that render metrics format identically.

/** Rounded integer with thousands separators, e.g. 1247 → "1,247". */
export function fmtNum(n: number): string {
  return Math.round(n || 0).toLocaleString();
}

/** Compact magnitude for axis ticks, e.g. 1_200 → "1.2k", 3_400_000 → "3.4M". */
export function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k`;
  return `${Math.round(n)}`;
}

/** Human byte size, e.g. 2048 → "2.0 KB". */
export function fmtBytes(b: number): string {
  if (!b) return "0 B";
  if (b < 1024) return `${Math.round(b)} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / (1024 * 1024)).toFixed(1)} MB`;
  return `${(b / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** Total bytes transferred (request + response) for a stat row. */
export function dataBytes(s: {
  total_request_bytes?: number;
  total_response_bytes?: number;
}): number {
  return (s.total_request_bytes || 0) + (s.total_response_bytes || 0);
}
