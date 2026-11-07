#!/usr/bin/env bash
# KrakenLink bridge on the official KrakenSDR image. Everything lives in this folder (~/krakenlink on the Pi);
# no existing file on the image is changed. The AIR ESP32 port is detected at every start.
# Usage: ./run_bridge.sh run|start|stop|status|log|install-service|remove-service
set -euo pipefail
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
UNIT=krakenlink-bridge.service
mkdir -p "$HERE/logs"
MATCH="krakenlink.bridge --config $HERE/bridge.toml"
running() { pgrep -f "$MATCH" >/dev/null; }
service_active() { systemctl is-active --quiet "$UNIT" 2>/dev/null; }
render() {
  local air
  air=$(cd "$HERE" && python3 -c 'from krakenlink.tools.ports import detect_ports; print(detect_ports()[0])')
  [[ -n "$air" ]] || { echo "No ESP32 found in /dev/serial/by-id (plug it into its COM port)" >&2; return 1; }
  sed "s|@AIR_PORT@|$air|" "$HERE/bridge.toml.in" >"$HERE/bridge.toml"
  # Running as root (systemd): keep files owned by the folder's owner so by-hand use still works.
  if (( EUID == 0 )); then chown --reference="$HERE" "$HERE/bridge.toml" "$HERE/logs"; fi
  echo "AIR port $air"
}
case "${1:-status}" in
  run)  # foreground; used by the systemd unit
    render
    cd "$HERE"
    exec python3 -m krakenlink.bridge --config "$HERE/bridge.toml" ;;
  start)
    if service_active; then echo "managed by systemd: sudo systemctl restart $UNIT"; exit 0; fi
    if running; then echo "already running (pid $(pgrep -f "$MATCH"))"; exit 0; fi
    render
    cd "$HERE"
    # Root: ground commands rewrite Kraken's root-owned settings.json. The log file stays krakenrf's.
    # shellcheck disable=SC2024
    sudo setsid nohup python3 -m krakenlink.bridge --config "$HERE/bridge.toml" </dev/null >>"$HERE/logs/bridge.out" 2>&1 &
    sleep 2
    if running; then echo "bridge started (pid $(pgrep -f "$MATCH"))"; else echo "bridge exited; see $HERE/logs/bridge.out" >&2; exit 1; fi ;;
  stop)
    if service_active; then echo "managed by systemd: sudo systemctl stop $UNIT"; exit 0; fi
    if running; then sudo pkill -f "$MATCH"; echo stopped; else echo "not running"; fi ;;
  status)
    if service_active; then systemctl --no-pager --lines=0 status "$UNIT"
    elif running; then echo "running by hand (pid $(pgrep -f "$MATCH"))"
    else echo "not running"; fi ;;
  log)
    if systemctl cat "$UNIT" >/dev/null 2>&1; then journalctl -u "$UNIT" -n 40 --no-pager; else tail -n 40 "$HERE/logs/bridge.out"; fi ;;
  install-service)
    if running && ! service_active; then sudo pkill -f "$MATCH"; fi
    sed -e "s|@HERE@|$HERE|g" "$HERE/krakenlink-bridge.service.in" | sudo tee "/etc/systemd/system/$UNIT" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$UNIT"
    echo "installed and started $UNIT (starts on boot)" ;;
  remove-service)
    sudo systemctl disable --now "$UNIT" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/$UNIT"
    sudo systemctl daemon-reload
    echo "removed $UNIT" ;;
  *) echo "usage: $0 run|start|stop|status|log|install-service|remove-service" >&2; exit 2 ;;
esac
