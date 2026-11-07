#!/usr/bin/env bash
exec "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/../common/install_kraken.sh" "$@"
