#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 [--port DEV] [--no-browser] [--help]"; }
port=; no_browser=0
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --no-browser) no_browser=1 ;;
    --port) (($# >= 2)) || { usage >&2; exit 2; }; port=$2; shift ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Ignore an inherited PYTHONPATH (e.g. ROS) so the venv only sees its own packages.
unset PYTHONPATH
if [[ -z $port ]]; then
  byid=${KRAKENLINK_BY_ID:-/dev/serial/by-id}
  matches=()
  shopt -s nullglob
  for dev in "$byid"/*; do [[ $dev == *1a86* || $dev == *Espressif* ]] && matches+=("$dev"); done
  ((${#matches[@]})) || { echo "No GROUND ESP32 port found in $byid (plug it into its COM port or pass --port DEV)" >&2; exit 1; }
  port=${matches[0]}
fi
[[ -x "$HERE/.venv/bin/python" ]] || { echo 'Missing .venv; run ./install.sh first' >&2; exit 1; }
sed "s|@GROUND_PORT@|$port|g" "$HERE/ground.toml.in" > "$HERE/ground.toml"
cd "$HERE"
"$HERE/.venv/bin/python" -m krakenlink.ground --config "$HERE/ground.toml" &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
if (( ! no_browser )); then
  for _ in {1..60}; do
    if python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8050",timeout=.5)' >/dev/null 2>&1; then xdg-open http://127.0.0.1:8050 >/dev/null 2>&1 || true; break; fi
    sleep 1
  done
fi
wait "$pid"
