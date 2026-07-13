#!/usr/bin/env bash
# Launch all six mock microservices, each on its own port, instrumented with
# APILens. Reads the project API key from .env.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env missing. It should define APILENS_API_KEY (see .env.example)." >&2
  exit 1
fi
set -a; . ./.env; set +a

PY=.venv/bin/python
[ -x "$PY" ] || { echo "ERROR: .venv not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

# Choose the APILens SDK source on every boot. Non-interactive callers can set
# SDK_MODE=published|local, or pass "--sdk <mode>" as the first args.
SDK_MODE="${SDK_MODE:-}"
case "${1:-}" in --sdk) SDK_MODE="${2:-}";; esac
if [ -z "$SDK_MODE" ]; then
  if [ -t 0 ]; then
    printf "Which APILens SDK? [P]ublished (PyPI) / [l]ocal (../packages/sdk-python): "
    read -r _ans || _ans=""
    case "$_ans" in l|L|local|dev) SDK_MODE=local;; *) SDK_MODE=published;; esac
  else
    SDK_MODE=published   # default when there's no terminal to prompt on
  fi
fi
./sdk.sh "$SDK_MODE"
echo

mkdir -p .run logs
services="catalog:9101 users:9102 cart:9103 orders:9104 payments:9105 inventory:9106"
for pair in $services; do
  name=${pair%%:*}; port=${pair##*:}
  nohup "$PY" -m uvicorn "store.${name}:app" --host 0.0.0.0 --port "$port" > "logs/${name}.log" 2>&1 &
  echo $! > ".run/${name}.pid"
  echo "started ${name}-service on :${port} (pid $!)"
done
echo
echo "All services up. Generate traffic with:  .venv/bin/python generate_traffic.py"
echo "Stop everything with:                    ./stop.sh"
