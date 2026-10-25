#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
saved_settings=("" "" "" "" "")
if [[ -e "$project_dir/runtime/client.json" || -L "$project_dir/runtime/client.json" ]]; then
    mapfile -d '' -t saved_settings < <(python3 "$project_dir/tools/client_settings.py" --emit "$project_dir/runtime/client.json")
    if (( ${#saved_settings[@]} != 5 )); then
        printf '%s\n' 'Saved client settings could not be read. Run setup-client-linux.sh.' >&2
        exit 1
    fi
fi
steam_dir="${OUTLANDS_STEAM_DIR:-${saved_settings[0]:-$HOME/.local/share/Steam}}"
proton_path="${OUTLANDS_PROTON:-${saved_settings[1]:-$steam_dir/steamapps/common/Proton - Experimental/proton}}"
launcher_path="$project_dir/runtime/downloads/plutonium.exe"

if [[ ! -x "$proton_path" || ! -f "$launcher_path" ]]; then
    printf '%s\n' 'Missing Proton or the official Plutonium updater. See README.md.' >&2
    exit 1
fi

mkdir -p "$project_dir/runtime/compatdata" "$project_dir/runtime/logs"
export STEAM_COMPAT_DATA_PATH="$project_dir/runtime/compatdata"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$steam_dir"
export SteamAppId=202990 SteamGameId=202990
export PROTON_LOG="${PROTON_LOG:-0}"
export PROTON_LOG_DIR="$project_dir/runtime/logs"
exec "$proton_path" run "$launcher_path" "$@"
