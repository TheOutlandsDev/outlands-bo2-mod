#!/usr/bin/env python3
"""Start the private T6 dedicated server inside its Linux container.

The image supplies Wine and an X display (normally through xvfb-run). Game and
vendor inputs remain immutable; /data holds the fresh Wine prefix and server
state. Importing this module and --check never launch Wine or create files.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile


GAME = Path("/opt/t6/game")
VENDOR = Path("/opt/t6/plutonium")
MOD = Path("/opt/t6/mod/storage/t6")
DATA = Path("/data")
PREFIX = DATA / "prefix"
PLUTONIUM = DATA / "plutonium"
KEY_FILE = Path("/run/secrets/plutonium_server_key")
CFG_NAME = "outlands_t6.cfg"
PASSWORD_PLACEHOLDER = "REPLACE_WITH_A_PRIVATE_JOIN_PASSWORD"
MOD_PAYLOADS = (
    Path(CFG_NAME),
    Path("gamesettings/outlands_tdm.cfg"),
    Path("scripts/mp/outlands_status.gsc"),
    Path("scripts/mp/outlands_native_bots.gsc"),
    Path("scripts/mp/outlands_chat.gsc"),
    Path("bots.txt"),
    Path("gamesettings/outlands_dm.cfg"),
    Path("gamesettings/outlands_ctf.cfg"),
    Path("gamesettings/outlands_dem.cfg"),
    Path("gamesettings/outlands_dom.cfg"),
    Path("gamesettings/outlands_koth.cfg"),
    Path("gamesettings/outlands_hq.cfg"),
    Path("gamesettings/outlands_conf.cfg"),
    Path("scripts/mp/outlands_bot_identity.gsc"),
    Path("scripts/mp/outlands_bot_profiles.gsc"),
    Path("scripts/mp/outlands_bot_careers.gsc"),
    Path("scripts/mp/outlands_squads.gsc"),
    Path("scripts/mp/outlands_contracts.gsc"),
)


class StartupError(Exception):
    """A failure safe to describe without printing command-line secrets."""


def regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def check_prerequisites() -> None:
    """Check immutable inputs and commands without modifying anything."""
    for command in ("wine", "wineboot", "winepath"):
        if shutil.which(command) is None:
            raise StartupError(f"Missing container command: {command}")
    required = (
        GAME / "t6mp.exe",
        GAME / "zone/all/code_pre_gfx_mp.ff",
        GAME / "zone/all/code_post_gfx_mp.ff",
        GAME / "zone/all/common_mp.ff",
        GAME / "zone/all/patch_mp.ff",
        GAME / "zone/all/ui_mp.ff",
        GAME / "zone/all/mp_raid.ff",
        GAME / "zone/all/mp_hijacked.ff",
        GAME / "zone/all/mp_village.ff",
        VENDOR / "bin/plutonium-bootstrapper-win32.exe",
        VENDOR / "games/t6mp.exe",
        VENDOR / "info.json",
        *(MOD / relative for relative in MOD_PAYLOADS),
    )
    for path in required:
        if not regular_file(path):
            raise StartupError(f"Missing regular input file: {path}")
    package_revision(VENDOR / "info.json")
    cfg_source = (MOD / CFG_NAME).read_text(encoding="utf-8")
    cfg_commands = re.sub(r"^[ \t]*//[^\r\n]*$", "", cfg_source, flags=re.MULTILINE)
    if ";" in cfg_commands:
        raise StartupError("Source CFG contains semicolons, which can split console commands")
    if len(list(assignment_pattern("g_password").finditer(cfg_source))) != 1:
        raise StartupError("Source CFG must have exactly one g_password assignment")
    if not re.search(r"\binit\s*\(\s*\)", (MOD / MOD_PAYLOADS[2]).read_text(encoding="utf-8")):
        raise StartupError("Source diagnostic GSC is missing its init entry point")
    for directory in (VENDOR / "bin", VENDOR / "games", VENDOR / "storage"):
        if not directory.is_dir() or directory.is_symlink():
            raise StartupError(f"Missing regular vendor directory: {directory}")
        for path in directory.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise StartupError(f"Vendor package contains an unsupported link or file: {path}")
    if not DATA.is_dir() or DATA.is_symlink():
        raise StartupError("/data must be a writable persistent volume directory")
    if not os.access(DATA, os.W_OK | os.X_OK):
        raise StartupError("The t6 user cannot write to /data")


def read_settings() -> tuple[str, str, int, str | None]:
    mode = os.environ.get("T6_MODE", "lan").strip().lower()
    if mode not in ("online", "lan"):
        raise StartupError("T6_MODE must be online or lan")
    for flag in ("T6_CHAT_ENABLED", "T6_CAREERS_ENABLED"):
        if os.environ.get(flag, "0") not in ("0", "1"):
            raise StartupError(flag + " must be 0 or 1")
    bind_ip = os.environ.get("T6_BIND_IP", "0.0.0.0").strip()
    try:
        bind_ip = str(ipaddress.IPv4Address(bind_ip))
        port = int(os.environ.get("T6_PORT", "4977"))
    except ValueError:
        raise StartupError("T6_BIND_IP must be an IPv4 address and T6_PORT must be an integer") from None
    if not 1 <= port <= 65535:
        raise StartupError("T6_PORT must be between 1 and 65535")
    name = os.environ.get("T6_NAME")
    if name is not None:
        name = name.strip()
        if not name or len(name) > 128 or any(ord(c) < 32 or c in '";\\' for c in name):
            raise StartupError("T6_NAME must be 1-128 characters without control characters, quotes, semicolons or backslashes")
    return mode, bind_ip, port, name


def read_server_key(mode: str) -> str:
    if mode == "lan":
        return ""
    key_file = Path(os.environ.get("T6_SERVER_KEY_FILE", str(KEY_FILE)))
    if not key_file.is_absolute():
        raise StartupError("T6_SERVER_KEY_FILE must be an absolute container path")
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        raise StartupError("Online mode requires /run/secrets/plutonium_server_key") from None
    if not key or any(c.isspace() or ord(c) < 32 or c in '";\\' for c in key):
        raise StartupError("The mounted Plutonium server key is empty or invalid")
    return key


def ensure_directory(path: Path) -> None:
    if path.is_symlink():
        raise StartupError(f"Refusing a symlink in persistent server state: {path}")
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise StartupError(f"Expected a persistent directory: {path}")


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    ensure_directory(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise StartupError(f"Refusing to replace a nonregular state file: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".outlands-", delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def copy_missing(source: Path, target: Path) -> None:
    """Seed files atomically while retaining every existing persistent file."""
    if source.is_symlink():
        raise StartupError(f"Refusing a vendor symlink: {source}")
    if source.is_dir():
        ensure_directory(target)
        for child in sorted(source.iterdir()):
            copy_missing(child, target / child.name)
        return
    if not regular_file(source):
        raise StartupError(f"Unsupported vendor file: {source}")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise StartupError(f"Unexpected persistent vendor target: {target}")
    if target.exists():
        return
    # Individual vendor files are small enough to stage without copying the
    # entire package to memory. Rename only after the copy has completed.
    ensure_directory(target.parent)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".vendor-", delete=False) as stream:
            temporary = Path(stream.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def package_revision(info: Path) -> int:
    try:
        metadata = json.loads(info.read_text(encoding="utf-8"))
        revision = metadata.get("revision") if isinstance(metadata, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise StartupError(f"Cannot read Plutonium revision metadata: {info}") from None
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise StartupError(f"Invalid Plutonium revision metadata: {info}")
    return revision


def seed_vendor() -> None:
    ensure_directory(PLUTONIUM)
    image_revision = package_revision(VENDOR / "info.json")
    installed_info = PLUTONIUM / "info.json"
    if installed_info.exists() or installed_info.is_symlink():
        if not regular_file(installed_info):
            raise StartupError("Persistent Plutonium info.json must be a regular file")
        installed_revision = package_revision(installed_info)
        if installed_revision != image_revision:
            raise StartupError(
                f"Persistent Plutonium revision r{installed_revision} differs from image r{image_revision}. "
                "Use a matching image or explicitly migrate the vendor package while preserving server state."
            )
    # Deliberately exclude top-level config.json, tokens and launcher profiles.
    # Seed the revision first so an interrupted initial copy cannot later be
    # mixed with a different image revision without detection.
    for relative in ("info.json", "bin", "games", "storage"):
        copy_missing(VENDOR / relative, PLUTONIUM / relative)


def assignment_pattern(command: str) -> re.Pattern[str]:
    return re.compile(
        r"^[ \t]*(?:set(?:a|s)?[ \t]+)?" + re.escape(command)
        + r'[ \t]+(?:"([^"\r\n]*)"|([^ \t\r\n;]+))[ \t]*(?://[^\r\n]*)?$',
        re.MULTILINE | re.IGNORECASE,
    )


def configure_mod(name: str | None) -> tuple[str, str]:
    target = PLUTONIUM / "storage/t6"
    ensure_directory(target)
    cfg = target / CFG_NAME
    copy_missing(MOD / CFG_NAME, cfg)
    for relative in MOD_PAYLOADS[1:]:
        atomic_write(target / relative, (MOD / relative).read_bytes(), 0o644)
    content = cfg.read_text(encoding="utf-8")
    # Introduce new nonsecret options without replacing operator choices or
    # regenerating the private CFG. Only this small reviewed list is migrated.
    source_cfg = (MOD / CFG_NAME).read_text(encoding="utf-8")
    for setting in ("sv_randomizeBotNames", "outlands_bot_levels", "outlands_bot_level_min",
                    "outlands_bot_level_max", "outlands_bot_prestige_min", "outlands_bot_prestige_max",
                    "outlands_bot_profiles", "outlands_bot_marksman_limit", "outlands_bot_patrol_profiles",
                    "outlands_bot_career_snapshot_seconds", "outlands_bot_career_restore_seconds",
                    "outlands_squads", "outlands_squad_reassess_seconds", "outlands_squad_attackers",
                    "outlands_squad_defenders", "outlands_squad_goal_seconds", "outlands_contracts",
                    "outlands_contract_seconds", "outlands_contract_seed", "outlands_contract_goal_scale",
                    "outlands_chat_cooldown", "outlands_chat_interval", "outlands_chat_timeout",
                    "outlands_chat_dialogue", "outlands_chat_dialogue_delay", "outlands_chat_bot_cooldown",
                    "outlands_chat_max_per_minute"):
        if not list(assignment_pattern(setting).finditer(content)):
            source_matches = list(assignment_pattern(setting).finditer(source_cfg))
            if len(source_matches) == 1:
                content += "\n" + source_matches[0].group(0).strip() + "\n"
    passwords = list(assignment_pattern("g_password").finditer(content))
    if len(passwords) != 1:
        raise StartupError("Persistent server CFG must have exactly one g_password assignment")
    password = passwords[0].group(1) if passwords[0].group(1) is not None else passwords[0].group(2)
    if password == PASSWORD_PLACEHOLDER:
        password = secrets.token_urlsafe(24)
        replacement = 'g_password "' + password + '"'
        content = content[:passwords[0].start()] + replacement + content[passwords[0].end():]
    elif not password:
        raise StartupError("The persistent server CFG needs a nonempty private join password")
    if name is not None:
        hostnames = list(assignment_pattern("sv_hostname").finditer(content))
        if len(hostnames) > 1:
            raise StartupError("Persistent server CFG contains duplicate sv_hostname assignments")
        replacement = 'sv_hostname "' + name + '"'
        if hostnames:
            content = content[:hostnames[0].start()] + replacement + content[hostnames[0].end():]
        else:
            content += "\n" + replacement + "\n"
    enabled = os.environ.get("T6_CHAT_ENABLED", "0")
    if enabled not in ("0", "1"):
        raise StartupError("T6_CHAT_ENABLED must be 0 or 1")
    careers_enabled = os.environ.get("T6_CAREERS_ENABLED", "0")
    if careers_enabled not in ("0", "1"):
        raise StartupError("T6_CAREERS_ENABLED must be 0 or 1")
    control_enabled = enabled == "1" or careers_enabled == "1"
    control_secret = ""
    if control_enabled:
        secret_path = DATA / "private/outlands_rcon_password"
        if not secret_path.exists() and not secret_path.is_symlink():
            atomic_write(secret_path, secrets.token_urlsafe(32).encode("ascii"))
        if not regular_file(secret_path):
            raise StartupError("Local chat control secret must be a regular file")
        if secret_path.stat().st_mode & 0o077:
            raise StartupError("Local chat control secret must have private mode 600")
        control_secret = secret_path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", control_secret):
            raise StartupError("Local chat control secret is invalid")
    # RCON serves only the optional local worker's fixed chat/career mailboxes.
    # The model never supplies a console command or controls human progression.
    for command, value in (("outlands_chat_enabled", enabled), ("outlands_bot_careers", careers_enabled),
                           ("rcon_password", control_secret)):
        content = assignment_pattern(command).sub("", content)
        content += f'\nset {command} "{value}"\n'
    content = re.sub(r"^[ \t]*rconWhitelistAdd[^\r\n]*$", "", content, flags=re.MULTILINE | re.IGNORECASE)
    if control_enabled:
        content += "rconWhitelistAdd 127.0.0.1\n"
    atomic_write(cfg, content.encode("utf-8"))
    return password, control_secret


def archive_console_log() -> None:
    current = PLUTONIUM / "console.log"
    if not current.exists() and not current.is_symlink():
        return
    if not regular_file(current):
        raise StartupError("Persistent console.log must be a regular file")
    logs = PLUTONIUM / "logs"
    ensure_directory(logs)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    # Reserve a unique destination, then move without reading old log content.
    with tempfile.NamedTemporaryFile(dir=logs, prefix=f"console-{stamp}-", suffix=".log", delete=False) as reserved:
        archived = Path(reserved.name)
    try:
        current.replace(archived)
    except OSError:
        archived.unlink(missing_ok=True)
        raise


class ProcessRunner:
    def __init__(self, server_key: str, join_password: str = "", control_secret: str = "") -> None:
        self.server_key = server_key
        self.sensitive_values = sorted({value for value in (server_key, join_password, control_secret) if value}, key=len, reverse=True)
        self.child: subprocess.Popen[str] | None = None
        self.stop_signal: int | None = None

    def redact(self, text: str) -> str:
        for value in self.sensitive_values:
            text = text.replace(value, "[REDACTED]")
        return text

    def handle_signal(self, signum: int, _frame: object) -> None:
        self.stop_signal = signum
        if self.child is not None:
            try:
                os.killpg(self.child.pid, signum)
            except ProcessLookupError:
                pass

    def run(self, args: list[str], label: str, *, capture: bool = False) -> tuple[int, str]:
        if self.stop_signal is not None:
            return 128 + self.stop_signal, ""
        try:
            self.child = subprocess.Popen(
                args, cwd=PLUTONIUM, env=os.environ.copy(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", bufsize=1, start_new_session=True,
            )
        except OSError:
            raise StartupError(f"Could not start {label}") from None
        if self.stop_signal is not None:
            self.handle_signal(self.stop_signal, None)
        output: list[str] = []
        try:
            assert self.child.stdout is not None
            for line in self.child.stdout:
                safe_line = self.redact(line)
                if capture:
                    output.append(safe_line)
                else:
                    print(safe_line, end="", flush=True)
            return_code = self.child.wait()
        finally:
            self.child.stdout.close()
            self.child = None
        if self.stop_signal is not None:
            return 128 + self.stop_signal, "".join(output)
        return (128 - return_code if return_code < 0 else return_code), "".join(output)

    def capture(self, args: list[str], label: str) -> str:
        return_code, output = self.run(args, label, capture=True)
        if return_code:
            if self.stop_signal is not None:
                raise StartupError("Server startup interrupted")
            # Helpers run before the secret is passed to Wine, but redact all
            # captured diagnostics as well. Never stringify a command object.
            detail = output.strip()[-1200:]
            raise StartupError(f"{label} failed (exit {return_code})" + (f": {detail}" if detail else ""))
        return output.strip()


def initialize_prefix(runner: ProcessRunner) -> None:
    ensure_directory(PREFIX)
    os.environ["WINEPREFIX"] = str(PREFIX)
    os.environ.setdefault("WINEDEBUG", "-all")
    if not regular_file(PREFIX / "system.reg"):
        runner.capture(["wineboot", "-u"], "Wine prefix initialization")
    if not regular_file(PREFIX / "system.reg"):
        raise StartupError("Wine did not create a usable /data/prefix")
    appdata_windows = runner.capture(
        ["wine", "cmd", "/d", "/c", "echo", "%LOCALAPPDATA%"],
        "Wine local-app-data discovery",
    )
    if "\n" in appdata_windows or not re.match(r"^[Cc]:\\users\\.+\\AppData\\Local\\?$", appdata_windows, re.IGNORECASE):
        raise StartupError("Wine returned an unexpected local-app-data path")
    appdata = Path(runner.capture(["winepath", "-u", appdata_windows], "Wine profile path translation"))
    users_root = (PREFIX / "drive_c/users").resolve()
    if not appdata.is_absolute() or not appdata.resolve().is_relative_to(users_root):
        raise StartupError("Wine local-app-data path escapes the persistent prefix")
    ensure_directory(appdata)
    link = appdata / "Plutonium"
    if link.is_symlink():
        if link.resolve() != PLUTONIUM.resolve():
            raise StartupError("Existing Wine Plutonium link points to a different location")
    elif link.exists():
        if not link.is_dir() or any(link.iterdir()):
            raise StartupError("Existing Wine Plutonium directory must be migrated before startup")
        link.rmdir()
        link.symlink_to(PLUTONIUM, target_is_directory=True)
    else:
        link.symlink_to(PLUTONIUM, target_is_directory=True)


def windows_path(runner: ProcessRunner, path: Path) -> str:
    if not path.exists():
        raise StartupError(f"Missing runtime path: {path}")
    translated = runner.capture(["winepath", "-w", str(path)], "Windows path translation")
    if "\n" in translated or not re.match(r"^[A-Za-z]:\\", translated):
        raise StartupError("Wine returned an invalid Windows path")
    round_trip = Path(runner.capture(["winepath", "-u", translated], "Windows path verification"))
    if not round_trip.is_absolute() or round_trip.resolve() != path.resolve():
        raise StartupError("Wine Windows path did not round-trip to the expected container path")
    return translated


def server_command(bootstrapper: str, game: str, mode: str, bind_ip: str, port: int, key: str) -> list[str]:
    command = ["wine", bootstrapper, "t6mp", game, "-dedicated"]
    if mode == "lan":
        command.append("-lan")
    else:
        command.extend(["+set", "key", key])
    command.extend([
        "+set", "fs_game", "", "+set", "net_ip", bind_ip,
        "+set", "net_port", str(port), "+set", "logfile", "2",
        "+exec", CFG_NAME, "+map_rotate",
    ])
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check image inputs and settings without writes or Wine execution")
    options = parser.parse_args(argv)
    runner: ProcessRunner | None = None
    lock = None
    try:
        mode, bind_ip, port, name = read_settings()
        check_prerequisites()
        if options.check:
            print("Container prerequisites passed. No state written and no Wine process launched.", flush=True)
            if mode == "online":
                print("Online startup additionally requires the mounted Plutonium server-key secret.", flush=True)
            return 0
        key = read_server_key(mode)
        os.umask(0o077)
        lock_path = DATA / ".outlands-server.lock"
        if lock_path.is_symlink():
            raise StartupError("Refusing a symlink for the persistent server lock")
        lock = lock_path.open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise StartupError("This persistent volume is already running another server") from None
        seed_vendor()
        join_password, control_secret = configure_mod(name)
        runner = ProcessRunner(key, join_password, control_secret)
        signal.signal(signal.SIGTERM, runner.handle_signal)
        signal.signal(signal.SIGINT, runner.handle_signal)
        initialize_prefix(runner)
        bootstrapper = windows_path(runner, PLUTONIUM / "bin/plutonium-bootstrapper-win32.exe")
        game = windows_path(runner, GAME)
        print(f"Starting Outlands BO2 in {mode} mode on {bind_ip}:{port}.", flush=True)
        print("Private join password is stored in the persistent server CFG.", flush=True)
        archive_console_log()
        result, _ = runner.run(server_command(bootstrapper, game, mode, bind_ip, port, key), "T6 dedicated server")
        return result
    except (StartupError, OSError, UnicodeError) as error:
        message = str(error)
        if runner is not None:
            message = runner.redact(message)
        print(f"Outlands T6 startup failed: {message}", file=sys.stderr, flush=True)
        return 128 + runner.stop_signal if runner is not None and runner.stop_signal is not None else 1
    finally:
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
