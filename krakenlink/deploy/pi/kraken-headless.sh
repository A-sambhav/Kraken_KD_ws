#!/usr/bin/env bash
set -euo pipefail
KRAKEN_ROOT=${KRAKEN_ROOT:?KRAKEN_ROOT must be set by krakensdr.service}
CONDA_SH=${CONDA_SH:?CONDA_SH must be set by krakensdr.service}
set +u
# shellcheck source=/dev/null
source "$CONDA_SH"
conda activate kraken
set -u
cd "$KRAKEN_ROOT"
STOP_SCRIPT="$KRAKEN_ROOT/kraken-stop.sh"
[[ -x "$STOP_SCRIPT" ]] || STOP_SCRIPT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../common" && pwd)/kraken-stop.sh"
KRAKEN_ROOT="$KRAKEN_ROOT" "$STOP_SCRIPT" || true
(
  cd heimdall_daq_fw/Firmware
  ./daq_start_sm.sh
)
mkdir -p krakensdr_doa/_share/logs/krakensdr_doa krakensdr_doa/_share/logs/heimdall_daq_fw
cd krakensdr_doa
exec python3 _ui/_web_interface/app.py
