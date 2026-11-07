#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 [--port DEV] [--help]"; }
port=
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --port) (($# >= 2)) || { usage >&2; exit 2; }; port=$2; shift ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
role=$(basename "$HERE")
[[ $role == air || $role == ground ]] || { echo "flash.sh must be in a folder named air or ground (got: $role)" >&2; exit 2; }
if [[ -z $port ]]; then
  byid=${KRAKENLINK_BY_ID:-/dev/serial/by-id}
  matches=()
  shopt -s nullglob
  for dev in "$byid"/*1a86*; do matches+=("$dev"); done
  if ((${#matches[@]} != 1)); then
    echo "Expected exactly one CH343 (1a86) device in $byid; found ${#matches[@]}:" >&2
    for dev in "${matches[@]}"; do echo "  $dev" >&2; done
    echo 'Pass the ESP32-S3 COM port with --port DEV.' >&2
    exit 1
  fi
  port=${matches[0]}
fi
[[ -f "$HERE/firmware.bin" ]] || { echo 'Missing firmware.bin; run make_dist.sh --firmware' >&2; exit 1; }
[[ -f "$HERE/firmware.sha256" ]] || { echo 'Missing firmware.sha256; run make_dist.sh --firmware' >&2; exit 1; }
(cd "$HERE" && sha256sum -c firmware.sha256)
if python3 -c 'import esptool' >/dev/null 2>&1; then
  python3 -m esptool --chip esp32s3 --port "$port" --baud 460800 write_flash 0x0 "$HERE/firmware.bin" || { echo 'Flash failed; hold BOOT, tap RESET, then retry.' >&2; exit 1; }
else
  python3 -m venv "$HERE/.venv"
  "$HERE/.venv/bin/python" -m pip install esptool==4.8.1
  "$HERE/.venv/bin/python" -m esptool --chip esp32s3 --port "$port" --baud 460800 write_flash 0x0 "$HERE/firmware.bin" || { echo 'Flash failed; hold BOOT, tap RESET, then retry.' >&2; exit 1; }
fi
