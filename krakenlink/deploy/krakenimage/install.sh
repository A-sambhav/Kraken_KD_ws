#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 [--no-service] [--help]"; }
no_service=0
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --no-service) no_service=1 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)'; then
  echo 'Python 3.9 or newer is required' >&2; exit 1
fi
if ! python3 -c 'import serial' >/dev/null 2>&1; then
  echo 'Installing python3-serial'
  sudo apt-get install -y python3-serial
fi
if ! python3 -c 'import tomllib' >/dev/null 2>&1 && ! python3 -c 'import tomli' >/dev/null 2>&1; then
  sudo apt-get install -y python3-tomli
fi
if [[ ! -d /home/krakenrf/krakensdr_doa/krakensdr_doa/_share ]]; then
  echo 'Warning: Kraken share directory is missing; bridge will wait for Kraken.' >&2
fi
if ! compgen -G '/dev/serial/by-id/*' >/dev/null; then
  echo 'Warning: no ESP32 found in /dev/serial/by-id; plug the AIR ESP32 into its COM port.' >&2
fi
if (( ! no_service )); then "$HERE/run_bridge.sh" install-service; fi
echo "Installation complete."
"$HERE/run_bridge.sh" status || true
