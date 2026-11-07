#!/usr/bin/env bash
# Run on the laptop: copy the bridge to ~/krakenlink on the Pi (KrakenSDR image) and restart it.
# Usage: deploy/krakenimage/push.sh [user@host]   (default krakenrf@192.168.50.5)
set -euo pipefail
PI=${1:-krakenrf@192.168.50.5}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PKG=$(cd -- "$HERE/../.." && pwd)/krakenlink
rsync -a --delete --exclude='__pycache__/' "$PKG" "$PI:krakenlink/"
rsync -a "$HERE/run_bridge.sh" "$HERE/bridge.toml.in" "$HERE/krakenlink-bridge.service.in" "$PI:krakenlink/"
ssh "$PI" 'cd ~/krakenlink && if systemctl cat krakenlink-bridge.service >/dev/null 2>&1; then sudo systemctl restart krakenlink-bridge.service && ./run_bridge.sh status; else ./run_bridge.sh stop; ./run_bridge.sh start; fi'
