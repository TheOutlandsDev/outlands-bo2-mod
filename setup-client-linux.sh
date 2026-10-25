#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
command -v python3 >/dev/null || { printf '%s\n' 'The Outlands BO2 Mod requires Python 3 for client setup.' >&2; exit 1; }
exec python3 -B "$project_dir/tools/setup_client.py" "$@"
