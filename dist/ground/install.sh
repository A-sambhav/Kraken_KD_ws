#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then echo "Usage: $0 [--help]"; exit 0; fi
if (($#)); then echo "Usage: $0 [--help]" >&2; exit 2; fi
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Ignore an inherited PYTHONPATH (e.g. ROS) so the venv only sees its own packages.
unset PYTHONPATH
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)'; then echo 'Python 3.9 or newer is required' >&2; exit 1; fi
if ! python3 -m venv "$HERE/.venv"; then echo 'Could not create virtual environment; run: sudo apt install python3-venv' >&2; exit 1; fi
"$HERE/.venv/bin/python" -m pip install -r "$HERE/requirements.txt"
if ! id -nG "${USER:-$(id -un)}" | tr ' ' '\n' | grep -qx dialout; then
  echo "Add your user to dialout: sudo usermod -aG dialout $(id -un)"
  echo 'Log out and in for the group change to take effect.'
fi
PYTHONPATH="$HERE" "$HERE/.venv/bin/python" -c 'import krakenlink.ground.app'
echo 'Ground app installed.'
