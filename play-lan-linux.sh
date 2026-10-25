#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: play-lan-linux.sh [--join] [--check] [options]

  --join                 Execute the existing private outlands_join.cfg.
  --check                Validate inputs without starting Proton or the game.
  --name NAME            Stable, unique LAN name (required on first launch).
  --game-dir DIRECTORY   BO2 game directory (default: parent of this script).
  --plutonium-dir DIR    Installed Plutonium root in the isolated prefix.
  --port PORT            Client UDP port (default: 4976).
  --help                 Show this help.

Defaults can also be set with OUTLANDS_PLAYER_NAME, OUTLANDS_GAME_DIR,
OUTLANDS_PLUTONIUM_DIR, OUTLANDS_CLIENT_PORT, OUTLANDS_STEAM_DIR and
OUTLANDS_PROTON. The client always uses this starter's runtime/compatdata.
setup-client-linux.sh saves non-secret paths/port in runtime/client.json;
these are reused unless overridden by an environment variable or CLI option.
Name priority: --name, OUTLANDS_PLAYER_NAME, then the saved client name in
storage/t6/outlands_player_name.txt. LAN identity/progression depends on this
name, so reuse it across launches and choose a different name for each player.
The validated name is saved only when launching; --check never writes it.
--join expects storage/t6/outlands_join.cfg inside the active Plutonium root.
Keep the server address and password in that private CFG, outside launch args.
USAGE
}

fail() { printf 'Outlands LAN: %s\n' "$*" >&2; exit 1; }
validate_name() {
    local LC_ALL=C
    [[ "$player_name" =~ ^[A-Za-z0-9\ _.~-]{1,24}$ ]] ||
        fail 'Name must be 1-24 ASCII letters, numbers, spaces, dots, underscores, tildes or hyphens.'
    [[ "$player_name" != ' '* && "$player_name" != *' ' ]] ||
        fail 'Name cannot begin or end with a space.'
}

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
saved_settings=("" "" "" "" "")
settings_file="$project_dir/runtime/client.json"
if [[ -e "$settings_file" || -L "$settings_file" ]]; then
    command -v python3 >/dev/null || fail 'Python 3 is required to read saved client settings.'
    mapfile -d '' -t saved_settings < <(python3 "$project_dir/tools/client_settings.py" --emit "$settings_file")
    (( ${#saved_settings[@]} == 5 )) || fail 'Saved client settings could not be read. Run setup-client-linux.sh.'
fi
steam_dir="${OUTLANDS_STEAM_DIR:-${saved_settings[0]:-$HOME/.local/share/Steam}}"
proton_path="${OUTLANDS_PROTON:-${saved_settings[1]:-$steam_dir/steamapps/common/Proton - Experimental/proton}}"
compat_dir="$project_dir/runtime/compatdata"
plutonium_dir="${OUTLANDS_PLUTONIUM_DIR:-${saved_settings[3]:-$compat_dir/pfx/drive_c/users/steamuser/AppData/Local/Plutonium}}"
game_dir="${OUTLANDS_GAME_DIR:-${saved_settings[2]:-$project_dir/..}}"
player_name="${OUTLANDS_PLAYER_NAME:-}"
client_port="${OUTLANDS_CLIENT_PORT:-${saved_settings[4]:-4976}}"
join=0
check=0

while (( $# )); do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --join) join=1; shift ;;
        --check) check=1; shift ;;
        --name|--game-dir|--plutonium-dir|--port)
            (( $# >= 2 )) || fail "Missing value after $1."
            [[ -n "$2" ]] || fail "Empty value after $1."
            case "$1" in
                --name) player_name="$2" ;;
                --game-dir) game_dir="$2" ;;
                --plutonium-dir) plutonium_dir="$2" ;;
                --port) client_port="$2" ;;
            esac
            shift 2
            ;;
        *) fail "Unknown option. Run with --help for usage." ;;
    esac
done

[[ "$client_port" =~ ^[0-9]{1,5}$ ]] || fail 'Client port must be an integer from 1 to 65535.'
client_port="$((10#$client_port))"
(( client_port >= 1 && client_port <= 65535 )) || fail 'Client port must be an integer from 1 to 65535.'
[[ -x "$proton_path" ]] || fail 'Proton was not found. Set OUTLANDS_PROTON or install Proton Experimental.'
[[ -d "$steam_dir" ]] || fail 'Steam directory was not found. Set OUTLANDS_STEAM_DIR.'
[[ -f "$compat_dir/pfx/system.reg" ]] || fail 'The isolated prefix is missing. Run launch-linux.sh to install the official launcher first.'
[[ -d "$game_dir" ]] || fail 'BO2 game directory was not found.'
[[ -d "$plutonium_dir" ]] || fail 'Plutonium directory was not found. Run launch-linux.sh first.'
game_dir="$(cd -- "$game_dir" && pwd -P)"
plutonium_dir="$(cd -- "$plutonium_dir" && pwd -P)"
name_file="$plutonium_dir/storage/t6/outlands_player_name.txt"
if [[ -z "$player_name" ]]; then
    [[ -f "$name_file" && ! -L "$name_file" ]] ||
        fail 'Choose a stable, unique name with --name NAME or OUTLANDS_PLAYER_NAME on first launch.'
    command -v python3 >/dev/null || fail 'Python 3 is required to validate the saved player name.'
    if ! player_name="$(python3 - "$name_file" <<'PY'
from pathlib import Path
import re
import sys

try:
    data = Path(sys.argv[1]).read_bytes()
except OSError:
    raise SystemExit(1)
if data.endswith(b"\r\n"):
    data = data[:-2]
elif data.endswith(b"\n"):
    data = data[:-1]
if not re.fullmatch(rb"[A-Za-z0-9 _.~-]{1,24}", data) or data.startswith(b" ") or data.endswith(b" "):
    raise SystemExit(1)
print(data.decode("ascii"))
PY
    )"; then
        fail 'Saved player name must be one valid ASCII name, without outer spaces or extra lines. Set --name NAME to replace it on launch.'
    fi
fi
validate_name
[[ "$game_dir" != *'"'* && "$game_dir" != *$'\n'* && "$game_dir" != *$'\r'* ]] ||
    fail 'The game path contains unsupported characters.'
for relative in t6mp.exe zone/all/code_pre_gfx_mp.ff zone/all/common_mp.ff; do
    [[ -f "$game_dir/$relative" ]] || fail "Required game file is missing: $relative"
done
bootstrapper="$plutonium_dir/bin/plutonium-bootstrapper-win32.exe"
[[ -f "$bootstrapper" && -f "$plutonium_dir/games/t6mp.exe" ]] ||
    fail 'Official Plutonium runtime files are missing. Run launch-linux.sh to update them.'
[[ "$(readlink -f -- "$compat_dir/pfx/dosdevices/z:" 2>/dev/null || true)" == / ]] ||
    fail 'This isolated prefix must map Z: to / so the validated game path can be translated.'
if (( join )); then
    [[ -f "$plutonium_dir/storage/t6/outlands_join.cfg" ]] ||
        fail 'Private storage/t6/outlands_join.cfg is missing. Prepare it before using --join.'
fi

if (( check )); then
    printf '%s\n' 'LAN client prerequisites passed. No Proton or game process was started.'
    exit 0
fi

# Saving the validated name happens only on the actual launch path. A temporary
# sibling keeps an interrupted write from replacing the previous LAN identity.
[[ ! -L "$name_file" && ( ! -e "$name_file" || -f "$name_file" ) ]] ||
    fail 'Saved player-name path must be a regular file.'
mkdir -p -- "$(dirname -- "$name_file")"
name_temp="$(umask 077; mktemp "$name_file.XXXXXX")" || fail 'Cannot prepare the saved player name.'
trap 'rm -f -- "$name_temp"' EXIT
printf '%s\n' "$player_name" > "$name_temp" || fail 'Cannot write the saved player name.'
mv -f -- "$name_temp" "$name_file" || fail 'Cannot save the player name.'
trap - EXIT

# Z: is validated above. This avoids depending on a separate Wine installation
# or launching a path-discovery process against a different prefix.
game_windows_path="Z:${game_dir//\//\\}"
launch_args=(t6mp "$game_windows_path" +name "$player_name" -lan +set net_port "$client_port")
if (( join )); then
    launch_args+=(+exec outlands_join.cfg)
fi
mkdir -p -- "$project_dir/runtime/logs"
export STEAM_COMPAT_DATA_PATH="$compat_dir"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$steam_dir"
export SteamAppId=202990 SteamGameId=202990
export PROTON_LOG="${PROTON_LOG:-0}"
export PROTON_LOG_DIR="$project_dir/runtime/logs"
cd -- "$plutonium_dir"
exec "$proton_path" runinprefix "$bootstrapper" "${launch_args[@]}"
