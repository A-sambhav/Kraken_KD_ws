#!/usr/bin/env bash
set -euo pipefail

KRAKEN_ROOT=${KRAKEN_ROOT:?KRAKEN_ROOT must be set}

if [[ -d "$KRAKEN_ROOT/heimdall_daq_fw/Firmware" ]]; then
  (cd "$KRAKEN_ROOT/heimdall_daq_fw/Firmware" && ./daq_stop.sh) || true
fi

APP_PATTERN='_ui/_web_interface/app\.py'
APP_PIDS=$(pgrep -f "$APP_PATTERN" || true)
if [[ -n "$APP_PIDS" ]]; then
  while IFS= read -r pid; do
    [[ -n "$pid" ]] && kill -TERM "$pid" 2>/dev/null || true
  done <<< "$APP_PIDS"
  sleep 3
  APP_PIDS=$(pgrep -f "$APP_PATTERN" || true)
  if [[ -n "$APP_PIDS" ]]; then
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && kill -KILL "$pid" 2>/dev/null || true
    done <<< "$APP_PIDS"
  fi
fi
