#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd)
KRAKEN_ROOT=${KRAKEN_ROOT:-"$HOME/krakensdr"}
[[ -d "$KRAKEN_ROOT/krakensdr_doa" ]] || { echo "KrakenSDR installation missing at $KRAKEN_ROOT/krakensdr_doa; run install_kraken.sh first" >&2; exit 1; }
VENV="$HOME/krakenlink/.venv"
CONFIG="$HOME/krakenlink/bridge.toml"
LOG_DIR="$HOME/krakenlink/logs"
START=0
[[ ${1:-} == --start ]] && START=1
mkdir -p "$HOME/krakenlink" "$LOG_DIR"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install "$REPO_ROOT" pymavlink pyserial
sudo usermod -aG dialout "$USER"
install -m 755 "$SCRIPT_DIR/kraken-headless.sh" "$KRAKEN_ROOT/kraken-headless.sh"
read -r AIR FC < <(PYTHONPATH="$REPO_ROOT" "$VENV/bin/python" -c 'from krakenlink.tools.ports import detect_ports; print(*detect_ports())')
[[ -n "$AIR" ]] || { AIR=/dev/serial/by-id/REPLACE_AIR_ESP32; echo "WARN: air ESP32 not found; edit $CONFIG after connecting it" >&2; }
[[ -n "$FC" ]] || { FC=/dev/serial/by-id/REPLACE_CUBE_ORANGE; echo "WARN: Cube Orange not found; edit $CONFIG after connecting it" >&2; }
python3 - "$SCRIPT_DIR/bridge.pi.toml.in" "$CONFIG" "$KRAKEN_ROOT" "$AIR" "$FC" "$LOG_DIR" <<'PY'
from pathlib import Path
import sys
source, target, root, air, fc, logs = sys.argv[1:]
text = Path(source).read_text()
for key, value in {'@KRAKEN_ROOT@':root,'@AIR_PORT@':air,'@FC_PORT@':fc,'@LOG_DIR@':logs}.items():
    text = text.replace(key, value)
Path(target).write_text(text)
PY
CONDA_SH="$HOME/miniforge3/etc/profile.d/conda.sh"
sed -e "s|@KRAKEN_ROOT@|$KRAKEN_ROOT|g" -e "s|@CONDA_SH@|$CONDA_SH|g" "$SCRIPT_DIR/krakensdr.service" | sudo tee /etc/systemd/system/krakensdr.service >/dev/null
sed -e "s|@WORKDIR@|$HOME/krakenlink|g" -e "s|@CONFIG@|$CONFIG|g" -e "s|@VENV@|$VENV|g" "$SCRIPT_DIR/krakenlink-bridge.service.in" | sudo tee /etc/systemd/system/krakenlink-bridge.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable krakensdr.service krakenlink-bridge.service
if (( START )); then sudo systemctl start krakensdr.service krakenlink-bridge.service; fi
echo "Installed config at $CONFIG; log out and back in for dialout group membership."
