#!/usr/bin/env bash
set -euo pipefail
usage() { echo "Usage: $0 [user@host] [--help]"; }
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (($# > 1)); then usage >&2; exit 2; fi
PI=${1:-krakenrf@192.168.50.5}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ssh "$PI" 'mkdir -p ~/krakenlink'
rsync -a --delete --exclude='/logs/' --exclude='/bridge.toml' "$HERE/" "$PI:krakenlink/"
ssh -t "$PI" 'bash ~/krakenlink/install.sh'
