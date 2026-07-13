#!/usr/bin/env bash
# Manage which APILens SDK the mock store's venv uses.
#
#   ./sdk.sh published   # use the released package from PyPI (installs if not already)
#   ./sdk.sh local       # use the in-repo SDK at ../packages/sdk-python (editable)
#   ./sdk.sh upgrade      # upgrade the published package to the latest on PyPI
#   ./sdk.sh status       # show what's currently installed
#
# "published"/"local" only reinstall when the mode actually changes, so they're
# cheap to call on every boot. Use "upgrade" to pull a newer PyPI release.
set -euo pipefail
cd "$(dirname "$0")"

export PIP_DISABLE_PIP_VERSION_CHECK=1
PIP=".venv/bin/pip"
LOCAL_SDK="../packages/sdk-python"
EXTRA="[fastapi]"
[ -x "$PIP" ] || { echo "ERROR: .venv missing. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2; exit 1; }

current_mode() {
  local out
  out="$("$PIP" show apilenss 2>/dev/null)" || { echo none; return; }
  if printf '%s\n' "$out" | grep -qi "Editable project location"; then echo local; else echo published; fi
}

version() { "$PIP" show apilenss 2>/dev/null | awk -F': ' '/^Version/{print $2}'; }

# Uninstall first: pip treats an existing editable install as "already
# satisfied" and won't replace it with a PyPI wheel (or vice-versa) otherwise.
install_published() { "$PIP" uninstall -y apilenss >/dev/null 2>&1 || true; "$PIP" install -q -U "apilenss${EXTRA}"; }
install_local()     { "$PIP" uninstall -y apilenss >/dev/null 2>&1 || true; "$PIP" install -q -e "${LOCAL_SDK}${EXTRA}"; }

case "${1:-status}" in
  published|pypi|p)
    if [ "$(current_mode)" = published ]; then
      echo "SDK: already on published apilenss $(version). Run './sdk.sh upgrade' to update."
    else
      echo "SDK: switching to published (PyPI)..."; install_published; echo "SDK: now on published apilenss $(version)."
    fi
    ;;
  local|dev|l)
    if [ "$(current_mode)" = local ]; then
      echo "SDK: already on local editable SDK ($LOCAL_SDK), version $(version)."
    else
      echo "SDK: switching to local editable SDK ($LOCAL_SDK)..."; install_local; echo "SDK: now on local editable apilenss $(version)."
    fi
    ;;
  upgrade|up|u)
    echo "SDK: upgrading to the latest published apilenss on PyPI..."; install_published; echo "SDK: now on published apilenss $(version)."
    ;;
  status|"")
    echo "SDK mode: $(current_mode)  (apilenss $(version))"
    ;;
  *)
    echo "usage: ./sdk.sh {published|local|upgrade|status}" >&2
    exit 1
    ;;
esac
