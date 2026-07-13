#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ -d .run ]; then
  for pidfile in .run/*.pid; do
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile")
    if kill "$pid" 2>/dev/null; then echo "stopped $(basename "$pidfile" .pid) (pid $pid)"; fi
    rm -f "$pidfile"
  done
fi
