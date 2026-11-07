#!/usr/bin/env bash
set -euo pipefail
ARCH=$(uname -m)
case "$ARCH" in
  aarch64|x86_64) ;;
  *) echo "install_kraken.sh supports aarch64 and x86_64; found $ARCH" >&2; exit 1 ;;
esac
if [[ ${1:-} == --check-architecture ]]; then
  echo "Supported architecture: $ARCH"
  exit 0
fi
KRAKEN_ROOT=${KRAKEN_ROOT:-"$HOME/krakensdr"}
LIBRTLSDR_REF=${LIBRTLSDR_REF:-}
KFR_REF=${KFR_REF:-}
NE10_REF=${NE10_REF:-}
HEIMDALL_REF=${HEIMDALL_REF:-}
LOG="$HOME/krakensdr-install.log"
mkdir -p "$KRAKEN_ROOT"
exec > >(tee -a "$LOG") 2>&1
step() { echo "[$(date -Is)] $*"; }
clone_build() { local url=$1 dir=$2 ref=$3; if [[ ! -d "$dir/.git" ]]; then git clone --depth 1 "$url" "$dir"; if [[ -n "$ref" ]]; then git -C "$dir" fetch --depth 1 origin "$ref"; git -C "$dir" checkout FETCH_HEAD; fi; else step "Already cloned: $dir"; fi; }
step 'Installing OS packages'
sudo apt-get update
sudo apt-get install -y build-essential git cmake libusb-1.0-0-dev lsof libzmq3-dev clang php-cli nodejs jq rsync
clone_build https://github.com/krakenrf/librtlsdr.git "$KRAKEN_ROOT/librtlsdr" "$LIBRTLSDR_REF"
if [[ ! -f /usr/local/lib/librtlsdr.so ]]; then cmake -S "$KRAKEN_ROOT/librtlsdr" -B "$KRAKEN_ROOT/librtlsdr/build" -DINSTALL_UDEV_RULES=ON; cmake --build "$KRAKEN_ROOT/librtlsdr/build" -j2; sudo cmake --install "$KRAKEN_ROOT/librtlsdr/build"; fi
sudo ln -sf /usr/local/bin/rtl_test /usr/local/bin/kraken_test
printf 'blacklist dvb_usb_rtl28xxu\nblacklist rtl2832\nblacklist rtl2830\n' | sudo tee /etc/modprobe.d/krakensdr-rtl.conf >/dev/null
clone_build https://github.com/krakenrf/kfr.git "$KRAKEN_ROOT/kfr" "$KFR_REF"
if [[ ! -f /usr/local/lib/libkfr.so ]]; then cmake -S "$KRAKEN_ROOT/kfr" -B "$KRAKEN_ROOT/kfr/build" -DENABLE_CAPI_BUILD=ON -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_BUILD_TYPE=Release; cmake --build "$KRAKEN_ROOT/kfr/build" -j2; sudo cp -a "$KRAKEN_ROOT"/kfr/build/lib/* /usr/local/lib/; sudo mkdir -p /usr/include/kfr; sudo cp "$KRAKEN_ROOT/kfr/include/kfr/capi.h" /usr/include/kfr/; sudo ldconfig; fi
if [[ "$ARCH" == aarch64 ]]; then
  clone_build https://github.com/krakenrf/Ne10.git "$KRAKEN_ROOT/Ne10" "$NE10_REF"
  if [[ ! -f /usr/lib/libNE10.a ]]; then cmake -S "$KRAKEN_ROOT/Ne10" -B "$KRAKEN_ROOT/Ne10/build" -DNE10_LINUX_TARGET_ARCH=aarch64 -DGNULINUX_PLATFORM=ON -DCMAKE_C_FLAGS='-mcpu=native -Ofast -funsafe-math-optimizations'; cmake --build "$KRAKEN_ROOT/Ne10/build" -j2; sudo find "$KRAKEN_ROOT/Ne10/build" -name libNE10.a -exec cp {} /usr/lib/libNE10.a \;; fi
fi
if [[ ! -x "$HOME/miniforge3/bin/conda" ]]; then curl -L "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-$ARCH.sh" -o /tmp/miniforge.sh; bash /tmp/miniforge.sh -b -p "$HOME/miniforge3"; fi
set +u
# shellcheck source=/dev/null
source "$HOME/miniforge3/etc/profile.d/conda.sh"
set -u
conda config --set auto_activate_base false
if ! conda env list | awk '{print $1}' | grep -qx kraken; then conda create -y -n kraken python=3.9.7; fi
conda install -y -n kraken -c conda-forge scipy==1.9.3 numba==0.56.4 configparser pyzmq scikit-rf sympy pandas orjson matplotlib requests
conda run -n kraken python -m pip install pyzmq dash_bootstrap_components==1.1.0 quart_compress==0.2.1 quart==0.17.0 dash_devices==0.1.3 pyargus
conda install -y -n kraken dash==1.20.0 werkzeug==2.0.2 plotly==5.23.0
# The pip step above pulls Dash 4 / Flask 3 / Werkzeug 3 / Plotly 7 as pip packages; conda then sees its pins
# "already installed" or writes old files over new ones, leaving mixed trees (e.g. ImportError '_plain_int').
# Remove every copy and pin with pip. Dash must be 2.x despite upstream's dash==1.20.0: dash_bootstrap_components
# 1.1.0 does 'from dash import html', while dash_devices (a Dash 1 fork) still works on Dash 2.3.1.
PINNED=(dash==2.3.1 flask==2.1.3 werkzeug==2.0.2 plotly==5.23.0)
for _ in 1 2 3; do conda run -n kraken python -m pip uninstall -y dash flask werkzeug plotly >/dev/null 2>&1 || true; done
conda run -n kraken python -m pip install --no-deps "${PINNED[@]}"
conda run -n kraken python -c "import dash_bootstrap_components, dash, flask, werkzeug, plotly, werkzeug.exceptions, quart, dash_devices
v = (dash.__version__, flask.__version__, werkzeug.__version__, plotly.__version__)
assert v == ('2.3.1', '2.1.3', '2.0.2', '5.23.0'), v"
clone_build https://github.com/krakenrf/heimdall_daq_fw.git "$KRAKEN_ROOT/heimdall_daq_fw" "$HEIMDALL_REF"
FW="$KRAKEN_ROOT/heimdall_daq_fw/Firmware"
if [[ ! -f "$FW/_daq_core/.krakenlink_built" ]]; then
  cp "$KRAKEN_ROOT/librtlsdr/build/src/librtlsdr.a" "$FW/_daq_core/"; cp "$KRAKEN_ROOT/librtlsdr/include/rtl-sdr.h" "$KRAKEN_ROOT/librtlsdr/include/rtl-sdr_export.h" "$FW/_daq_core/"
  make -C "$FW/_daq_core"
  touch "$FW/_daq_core/.krakenlink_built"
fi
CONFIG_SOURCE="$KRAKEN_ROOT/heimdall_daq_fw/config_files/kraken_default"
[[ -d "$CONFIG_SOURCE" ]] || { echo "Missing Kraken default preconfig directory: $CONFIG_SOURCE" >&2; exit 1; }
cp -a "$CONFIG_SOURCE"/. "$FW/"
[[ -f "$FW/daq_chain_config.ini" ]] || { echo 'Kraken default preconfig did not provide daq_chain_config.ini' >&2; exit 1; }
REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
rsync -a --delete --exclude='_share/' --exclude='__pycache__/' "$REPO/krakensdr_doa/" "$KRAKEN_ROOT/krakensdr_doa/"
cp "$KRAKEN_ROOT/krakensdr_doa/util/kraken_doa_start.sh" "$KRAKEN_ROOT/"
install -m 755 "$(dirname -- "${BASH_SOURCE[0]}")/kraken-stop.sh" "$KRAKEN_ROOT/kraken-stop.sh"
if [[ "$ARCH" == aarch64 ]]; then
  BOOT=/boot/firmware/config.txt
  if ! grep -qx 'usb_max_current_enable=1' "$BOOT"; then echo 'usb_max_current_enable=1' | sudo tee -a "$BOOT" >/dev/null; fi
fi
echo 'Power reminder: KrakenSDR needs its own 5 V supply.'
step "Kraken stack installed under $KRAKEN_ROOT"
