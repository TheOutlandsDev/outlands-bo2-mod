#!/usr/bin/env python3
"""Interactive Linux client setup for The Outlands BO2 Mod; never copies BO2 files.

Run setup-client-linux.sh to download/open the official updater and collect
private join details in this terminal. --dry-run validates install inputs with
no writes/downloads/launches. --check validates an already configured client.
Tailscale must be installed and signed in separately; no service is changed.
Close the game before applying setup. Requires Python 3.8 or newer.
"""

import argparse
import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import warnings
from urllib.parse import urlparse
from urllib.request import urlopen

sys.dont_write_bytecode = True
from client_settings import (load_invite, load_settings, read_name, validate_address,
                             validate_join_file, validate_name,
                             validate_password, validate_port)

UPDATER_URL = "https://cdn.plutonium.pw/updater/plutonium.exe"
GAME_FILES = ("t6mp.exe", "zone/all/code_pre_gfx_mp.ff", "zone/all/common_mp.ff")
CLIENT_SHELL_HELPERS = ("setup-client-linux.sh", "play-lan-linux.sh",
                        "play-outlands-linux.sh", "launch-linux.sh")


class ClientArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        # A mistaken --password/--server option must not echo its value.
        self.print_usage(sys.stderr)
        self.exit(2, "Outlands client: Invalid setup arguments. Run --help; connection details belong in hidden prompts or a private invite.\n")


def path_value(value):
    if not value or any(c in str(value) for c in '\0\r\n"'):
        raise ValueError("Choose a valid directory path without quotes or newlines.")
    return Path(value).expanduser().resolve()


def atomic_write(path, contents, mode=0o600):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("A setup destination is not a regular file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def prepare_shell_helpers(project):
    # Browser uploads and ZIP downloads can discard executable bits. Only these
    # fixed, regular source files may be chmodded, and only on the apply path.
    paths = [project / name for name in CLIENT_SHELL_HELPERS]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError("A required client shell helper is missing or is not a regular file.")
    for path in paths:
        path.chmod(0o755)


def ask_value(prompt, default, validator, hidden=False):
    while True:
        suffix = " [Enter to keep saved value]" if default is not None else ""
        if hidden:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                try:
                    value = getpass.getpass(prompt + suffix + ": ")
                except getpass.GetPassWarning:
                    raise ValueError("Private input requires a terminal that can disable echo.") from None
        else:
            value = input(prompt + suffix + ": ")
        if value == "" and default is not None:
            value = default
        try:
            return validator(value)
        except ValueError as error:
            print(error, file=sys.stderr)


def yes(prompt, default=True):
    while True:
        value = input(prompt + (" [Y/n]: " if default else " [y/N]: ")).lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter yes or no.")


def download_updater(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="plutonium-", suffix=".exe", dir=destination.parent)
    try:
        total = 0
        with os.fdopen(descriptor, "wb") as output, urlopen(UPDATER_URL, timeout=60) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in {"cdn.plutonium.pw", "plutonium.pw"}:
                raise ValueError("Updater download redirected outside the official HTTPS hosts.")
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 128 * 1024 * 1024:
                    raise ValueError("Updater download exceeds the expected size limit.")
                output.write(block)
        with Path(temporary).open("rb") as handle:
            if total < 1024 or handle.read(2) != b"MZ":
                raise ValueError("The official updater download is not a Windows executable.")
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            raise ValueError("Updater destination is not a regular file.")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def check_game(path):
    path = path_value(path)
    if not all((path / name).is_file() for name in GAME_FILES):
        raise ValueError("Owned BO2 directory must contain t6mp.exe and the multiplayer core fastfiles.")
    return path


def check_proton(path):
    path = path_value(path)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Choose an installed, executable Proton script (for example Proton Experimental/proton).")
    return path


def check_directory(path):
    path = path_value(path)
    if not path.is_dir():
        raise ValueError("The selected directory does not exist.")
    return path


def check_runtime(plutonium, prefix):
    if not (prefix / "system.reg").is_file():
        raise ValueError("The isolated Proton prefix is missing. Run setup with the official updater.")
    if not (prefix / "dosdevices/z:").is_symlink() or (prefix / "dosdevices/z:").resolve() != Path("/"):
        raise ValueError("The isolated Proton prefix must map Z: to /.")
    for name in ("bin/plutonium-bootstrapper-win32.exe", "games/t6mp.exe"):
        if not (plutonium / name).is_file():
            raise ValueError("The official Plutonium runtime is incomplete. Open the updater and let it finish.")


def desktop_shortcut(project):
    # Desktop Entry Exec quoting is separate from shell quoting. Escape reserved
    # characters inside its double-quoted executable argument, including %%.
    executable = str(project / "play-outlands-linux.sh")
    if any(c in executable for c in "\0\r\n"):
        raise ValueError("The checkout path cannot contain newlines for a desktop shortcut.")
    for before, after in (("\\", "\\\\\\\\"), ('"', '\\"'), ("`", "\\`"), ("$", "\\$"), ("%", "%%")):
        executable = executable.replace(before, after)
    applications = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "applications"
    contents = ("[Desktop Entry]\nType=Application\nName=The Outlands BO2 Mod\n"
                f'Exec="{executable}"\nTerminal=true\nCategories=Game;\n')
    atomic_write(applications / "outlands-bo2-mod.desktop", contents.encode(), 0o755)


def main(argv=None):
    parser = ClientArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Check an installed client without writing, downloading or launching.")
    mode.add_argument("--dry-run", action="store_true", help="Validate install inputs and show the plan without prompts or changes.")
    parser.add_argument("--game-dir", help="Owned BO2 game directory, anywhere outside this source clone.")
    parser.add_argument("--name", help="Stable unique LAN player name; changing it selects a different LAN profile.")
    parser.add_argument("--steam-dir", help="Steam installation directory.")
    parser.add_argument("--proton", help="Installed Proton script.")
    parser.add_argument("--plutonium-dir", help="Active Plutonium root; default is this project's isolated prefix.")
    parser.add_argument("--port", help="Client UDP port, default 4976.")
    parser.add_argument("--invite", type=Path, help="Private schema_version 1 invite JSON; contents are never printed.")
    parser.add_argument("--skip-updater", action="store_true", help="Use an already installed runtime without downloading/opening its updater.")
    parser.add_argument("--desktop-shortcut", action="store_true", help="Install a per-user application launcher on the apply path.")
    args = parser.parse_args(argv)
    project = Path(__file__).resolve().parents[1]
    config_file = project / "runtime/client.json"
    prefix = project / "runtime/compatdata/pfx"
    try:
        saved = load_settings(config_file)
        invite = load_invite(args.invite) if args.invite else None
        candidates = [Path.home() / ".local/share/Steam", Path.home() / ".steam/steam",
                      Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
        default_steam = next((p for p in candidates if p.is_dir()), candidates[0])
        steam_raw = args.steam_dir or os.environ.get("OUTLANDS_STEAM_DIR") or saved.get("steam_dir") or str(default_steam)
        proton_raw = args.proton or os.environ.get("OUTLANDS_PROTON") or saved.get("proton_path") or str(Path(steam_raw) / "steamapps/common/Proton - Experimental/proton")
        game_raw = args.game_dir or os.environ.get("OUTLANDS_GAME_DIR") or saved.get("game_dir")
        if not game_raw:
            game_raw = str(project.parent if all((project.parent / p).is_file() for p in GAME_FILES)
                           else Path(steam_raw) / "steamapps/common/Call of Duty Black Ops II")
        plutonium = path_value(args.plutonium_dir or os.environ.get("OUTLANDS_PLUTONIUM_DIR")
                               or saved.get("plutonium_dir") or str(prefix / "drive_c/users/steamuser/AppData/Local/Plutonium"))
        port = validate_port(args.port or os.environ.get("OUTLANDS_CLIENT_PORT") or saved.get("client_port", 4976))
        storage = plutonium / "storage/t6"
        name_file = storage / "outlands_player_name.txt"
        name = args.name if args.name is not None else (os.environ.get("OUTLANDS_PLAYER_NAME") or None)
        if name is None and name_file.exists():
            name = read_name(name_file)

        if args.check or args.dry_run:
            steam = check_directory(steam_raw)
            proton = check_proton(proton_raw)
            game = check_game(game_raw)
            if name is None:
                raise ValueError("Provide --name NAME for a first-install dry run, or save a stable name through setup.")
            validate_name(name)
            if args.check:
                check_runtime(plutonium, prefix)
                validate_join_file(storage / "outlands_join.cfg")
                if shutil.which("tailscale") is None:
                    raise ValueError("Tailscale is missing from PATH. Install it and sign in before joining.")
                print("Client files, saved identity and private join CFG passed checks. Network reachability and gameplay were not tested.")
            else:
                if args.skip_updater:
                    check_runtime(plutonium, prefix)
                print("Install inputs passed. Apply would download/open the official updater unless --skip-updater is set, then collect private join details in this terminal.")
                print("Only local client settings, the name file, join CFG and optional shortcut are written. BO2 files and existing stats are preserved.")
                if shutil.which("tailscale") is None:
                    print("Tailscale must be installed and signed in separately: https://tailscale.com/download/linux")
            return 0

        if not sys.stdin.isatty():
            raise ValueError("Interactive setup requires a terminal. Use --dry-run or --check for unattended validation.")
        print("The Outlands BO2 Mod client setup. No BO2 files or existing stats will be copied or replaced.")
        steam = ask_value("Steam directory", steam_raw, check_directory)
        proton = ask_value("Installed Proton script", proton_raw, check_proton)
        game = ask_value("Owned BO2 game directory", game_raw, check_game)
        name = ask_value("Stable unique LAN player name (keep this for progression)", name, validate_name)

        if not args.skip_updater:
            updater = project / "runtime/downloads/plutonium.exe"
            print("Download source: " + UPDATER_URL)
            download_updater(updater)
            if yes("Open the official updater now? Let downloads finish, then close the launcher to continue"):
                (project / "runtime/compatdata").mkdir(parents=True, exist_ok=True)
                (project / "runtime/logs").mkdir(parents=True, exist_ok=True)
                environment = os.environ.copy()
                environment.update(STEAM_COMPAT_DATA_PATH=str(project / "runtime/compatdata"),
                                   STEAM_COMPAT_CLIENT_INSTALL_PATH=str(steam), SteamAppId="202990",
                                   SteamGameId="202990", PROTON_LOG="0")
                subprocess.run([str(proton), "run", str(updater)], cwd=project,
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        check_runtime(plutonium, prefix)
        join_file = storage / "outlands_join.cfg"
        replace_join = invite is not None or not join_file.exists() or yes("Replace the existing private connection settings?", False)
        private_join = None
        if replace_join:
            if invite is not None:
                address, password = invite
            else:
                address = ask_value("Private hosting IPv4 or DNS name, optionally :port (hidden)", None, validate_address, True)
                password = ask_value("Private server join password (hidden)", None, validate_password, True)
            private_join = f'password "{password}"\nconnect {address}\n'.encode("ascii")
        else:
            validate_join_file(join_file)
        settings = {"steam_dir": str(steam), "proton_path": str(proton), "game_dir": str(game),
                    "plutonium_dir": str(plutonium), "client_port": port}
        destinations = [name_file, config_file] + ([join_file] if private_join is not None else [])
        if any(path.is_symlink() or (path.exists() and not path.is_file()) for path in destinations):
            raise ValueError("A setup destination is not a regular file; no client settings were saved.")
        prepare_shell_helpers(project)
        atomic_write(name_file, (name + "\n").encode("ascii"))
        if private_join is not None:
            atomic_write(join_file, private_join)
        atomic_write(config_file, (json.dumps(settings, indent=2) + "\n").encode())
        if args.desktop_shortcut or yes("Add a per-user application launcher?", False):
            desktop_shortcut(project)
        print("Client setup saved. Start ./play-outlands-linux.sh to join, or run ./setup-client-linux.sh --check first.")
        print("Keep runtime/client.json and the active runtime private. Changing your LAN name selects a different profile.")
        if shutil.which("tailscale") is None:
            print("Install and sign in to Tailscale before joining: https://tailscale.com/download/linux")
        return 0
    except (OSError, ValueError, EOFError, KeyboardInterrupt):
        # Input values, join details and subprocess argument lists are deliberately
        # excluded from errors. Validation functions provide only fixed messages.
        error = sys.exc_info()[1]
        print("Outlands client: " + (str(error) if isinstance(error, ValueError) else "Setup could not finish; check selected paths, terminal input and internet access."), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
