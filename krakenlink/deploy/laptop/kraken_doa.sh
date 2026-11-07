#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: kraken_doa.sh [--with-ground] [--no-browser] [--help]
Run the Kraken DOA stack on this laptop. --with-ground also starts the local bridge and ground app.
EOF
}

WITH_GROUND=0
NO_BROWSER=0
for arg in "$@"; do
  case "$arg" in
    --with-ground) WITH_GROUND=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd -- "$SCRIPT_DIR/../.." && pwd)
KRAKEN_ROOT=${KRAKEN_ROOT:-"$HOME/krakensdr"}
CONDA_SH=$HOME/miniforge3/etc/profile.d/conda.sh
BRIDGE_PID=
GROUND_PID=
KRAKEN_STARTED=0
cleanup() {
  trap - INT TERM EXIT
  [[ -z "$BRIDGE_PID" ]] || sudo kill "$BRIDGE_PID" 2>/dev/null || true
  [[ -z "$GROUND_PID" ]] || kill "$GROUND_PID" 2>/dev/null || true
  [[ -z "$BRIDGE_PID" ]] || wait "$BRIDGE_PID" 2>/dev/null || true
  [[ -z "$GROUND_PID" ]] || wait "$GROUND_PID" 2>/dev/null || true
  if (( KRAKEN_STARTED )); then sudo env KRAKEN_ROOT="$KRAKEN_ROOT" "$KRAKEN_ROOT/kraken-stop.sh" || true; fi
}
trap cleanup INT TERM EXIT

CONFLICTS=$(pgrep -af 'krakenlink\.tools\.kraken_view|[r]tl_test' || true)
if [[ -n "$CONFLICTS" ]]; then
  echo "Raw viewer / rtl_test is running; close the raw viewer first. PIDs:" >&2
  awk '{print $1}' <<<"$CONFLICTS" >&2
  exit 1
fi
if [[ ! -d "$KRAKEN_ROOT/krakensdr_doa" ]]; then
  echo "Kraken stack missing; run deploy/common/install_kraken.sh first" >&2
  exit 1
fi
rsync -a --delete --exclude='_share/' --exclude='__pycache__/' "$REPO_DIR/../krakensdr_doa/" "$KRAKEN_ROOT/krakensdr_doa/"
sudo -v
sudo env KRAKEN_ROOT="$KRAKEN_ROOT" CONDA_SH="$CONDA_SH" bash -c 'exec "$1" >>"$2" 2>&1' _ "$SCRIPT_DIR/../pi/kraken-headless.sh" "$KRAKEN_ROOT/kraken_doa.log" &
KRAKEN_STARTED=1

if (( WITH_GROUND )); then
  LOCAL_DIR="$KRAKEN_ROOT/../krakenlink-local"
  LOG_DIR="$KRAKEN_ROOT/logs"
  mkdir -p "$LOCAL_DIR" "$LOG_DIR"
  sed -e "s|@KRAKEN_ROOT@|$KRAKEN_ROOT|g" -e "s|@LOG_DIR@|$LOG_DIR|g" "$SCRIPT_DIR/bridge.local.toml.in" >"$LOCAL_DIR/bridge.toml"
  USER_SITE=$(python3 -c 'import site; print(site.getusersitepackages())')
  export PYTHONPATH="$REPO_DIR:$USER_SITE${PYTHONPATH:+:$PYTHONPATH}"
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' && ! python3 -c 'import tomli' 2>/dev/null; then
    echo "Bridge dependency missing: Python module tomli is required for Python versions below 3.11." >&2
    exit 1
  fi
  if ! python3 -c 'import dash' 2>/dev/null; then
    echo "Ground app dependency missing: Python module dash." >&2
    exit 1
  fi
  sudo env PYTHONPATH="$PYTHONPATH" bash -c 'exec python3 -m krakenlink.bridge --config "$1" >>"$2" 2>&1' _ "$LOCAL_DIR/bridge.toml" "$LOG_DIR/bridge.log" &
  BRIDGE_PID=$!
  python3 -m krakenlink.ground --config "$SCRIPT_DIR/ground.local.toml" >"$LOG_DIR/ground.log" 2>&1 &
  GROUND_PID=$!
fi

printf 'Waiting for Kraken UI at http://127.0.0.1:8080'
READY=0
for ((i=0; i<120; i++)); do
  if curl --silent --fail --max-time 1 http://127.0.0.1:8080 >/dev/null; then READY=1; break; fi
  printf '.'
  sleep 1
done
printf '\n'
(( READY )) || { echo "Kraken UI did not answer within 120 seconds; see $KRAKEN_ROOT/kraken_doa.log" >&2; exit 1; }
if (( ! NO_BROWSER )); then xdg-open http://127.0.0.1:8080 >/dev/null 2>&1 || true; fi
if (( WITH_GROUND )); then
  if (( ! NO_BROWSER )); then xdg-open http://127.0.0.1:8050 >/dev/null 2>&1 || true; fi
  echo "Logs: $KRAKEN_ROOT/kraken_doa.log, $KRAKEN_ROOT/logs/bridge.log, $KRAKEN_ROOT/logs/ground.log"
else
  echo "Log: $KRAKEN_ROOT/kraken_doa.log"
fi
while :; do sleep 1; done
