#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then echo "Usage: $0 [--help]"; exit 0; fi
if (($#)); then echo "Usage: $0 [--help]" >&2; exit 2; fi
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
"$HERE/run_bridge.sh" remove-service
