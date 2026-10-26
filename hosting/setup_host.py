#!/usr/bin/env python3
"""Prepare a private host build from owned BO2 files and an official runtime.

Content preflight covers the public source rotation only. A persistent private
host CFG may differ and is never inspected or replaced by this preflight.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen

HOSTING = Path(__file__).resolve().parent
PROJECT = HOSTING.parent
# Import only the fixed public helper, without creating a cache on read-only runs.
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / "tools"))
import content_inventory

MANIFEST_URL = "https://cdn.plutoniummod.com/updater/prod/info.json"
REQUIRED_GAME = (
    "t6mp.exe", "t6sp.exe", "binkw32.dll", "steam_api.dll", "localization.txt",
    "localization_mp.txt", "codlogo.bmp", "installscript.vdf",
    "zone/all/code_pre_gfx_mp.ff", "zone/all/code_post_gfx_mp.ff",
    "zone/all/common_mp.ff", "zone/all/patch_mp.ff", "zone/all/ui_mp.ff",
    "zone/all/mp_raid.ff", "zone/all/mp_hijacked.ff", "zone/all/mp_village.ff",
)


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Output must be a regular file")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            handle.write((json.dumps(value, indent=2) + "\n").encode())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_host_settings(path: Path) -> dict[str, str]:
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("Host settings must be a small regular JSON file")
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        raise ValueError("Host settings are not readable JSON") from None
    if not isinstance(value, dict) or set(value) - {"plutonium_dir", "manifest"}:
        raise ValueError("Host settings contain unsupported fields")
    if any(not isinstance(item, str) or not item or any(c in item for c in "\0\r\n")
           for item in value.values()):
        raise ValueError("Host settings contain an invalid path")
    return value


def validate_game(path: Path) -> Path:
    path = path.expanduser().resolve(strict=True)
    for relative in REQUIRED_GAME:
        entry = path / relative
        if not entry.is_file() or entry.is_symlink():
            raise ValueError(f"Missing owned game file: {relative}")
    for relative in ("zone", "sound", "video", "redist", "Soundtrack"):
        directory = path / relative
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"Missing regular game directory: {relative}")
        if any(p.is_symlink() for p in directory.rglob("*")):
            raise ValueError(f"Game directory contains links: {relative}")
    return path


def validate_source_content(game: Path) -> None:
    """Fail before staging/downloads when the public source rotation is uncovered."""
    try:
        rotation, mode, count = content_inventory.configured_rotation(
            PROJECT / "storage/t6/outlands_t6.cfg")
        report = content_inventory.build_inventory(game, rotation, mode, count)
    except (OSError, ValueError):
        raise ValueError("Source rotation content preflight failed. Run tools/content_inventory.py locally for details.") from None
    if not report["rotation"]["inventory_ready"]:
        raise ValueError("Owned game content does not cover the source rotation and native bot modes. Run tools/content_inventory.py locally for details.")


def download_manifest(path: Path) -> None:
    # This downloads metadata only, never game files or an executable.
    with urlopen(MANIFEST_URL, timeout=30) as response:
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname not in ("cdn.plutoniummod.com", "cdn.plutonium.pw"):
            raise ValueError("Unexpected manifest destination")
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Vendor manifest is too large")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("files"), list) or not isinstance(data.get("revision"), int):
        raise ValueError("Invalid vendor manifest")
    atomic_json(path, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path)
    parser.add_argument("--plutonium-dir", type=Path)
    parser.add_argument("--manifest", type=Path,
                        help="official manifest file; reuses the last verified host path when omitted")
    parser.add_argument("--apply", action="store_true", help="stage verified runtime and save local build paths; never starts containers")
    options = parser.parse_args()
    try:
        saved = PROJECT / "runtime/client.json"
        settings = json.loads(saved.read_text()) if saved.is_file() else {}
        host_settings_path = HOSTING / "host-settings.json"
        host_settings = read_host_settings(host_settings_path)
        local = HOSTING / "compose.local.json"
        local_settings = json.loads(local.read_text()) if local.is_file() else {}
        local_game = local_settings.get("services", {}).get("t6", {}).get("build", {}).get("additional_contexts", {}).get("game")
        game = options.game_dir or local_game or settings.get("game_dir")
        if game is None and (PROJECT.parent / "t6mp.exe").is_file():
            game = PROJECT.parent
        if game is None:
            parser.error("Pass --game-dir with the owned BO2 folder, or run client setup first")
        game = validate_game(Path(game))
        validate_source_content(game)
        plut = Path(options.plutonium_dir or host_settings.get("plutonium_dir") or settings.get("plutonium_dir") or (
            PROJECT / "runtime/compatdata/pfx/drive_c/users/steamuser/AppData/Local/Plutonium")).expanduser().resolve(strict=True)
        manifest = Path(options.manifest or host_settings.get("manifest") or (
            PROJECT / "runtime/downloads/plutonium-manifest.json")).expanduser().resolve()
        if not (plut / "info.json").is_file():
            raise ValueError("Run the official Plutonium updater before host setup")
        if not manifest.is_file():
            if not options.apply:
                raise ValueError("Vendor manifest is missing; --apply fetches official metadata, or pass --manifest")
            download_manifest(manifest)
        subprocess.run([sys.executable, "-B", str(HOSTING / "prepare_package.py"),
                        "--plutonium-dir", str(plut), "--manifest", str(manifest),
                        *(["--apply"] if options.apply else [])], check=True)
        if options.apply:
            scripts = [HOSTING / name for name in ("manage.sh", "docker.sh")]
            if any(script.is_symlink() or not script.is_file() for script in scripts):
                raise ValueError("Hosting launcher must be a regular source file")
            atomic_json(HOSTING / "compose.local.json", {"services": {"t6": {"build": {
                "additional_contexts": {"game": str(game)}}}}})
            atomic_json(host_settings_path, {"plutonium_dir": str(plut), "manifest": str(manifest)})
            for script in scripts:
                script.chmod(0o755)
            print("Source rotation content verified. The existing private host CFG was not inspected.")
            print("Private build paths saved. Run ./manage.sh smoke, then ./manage.sh up.")
        else:
            print("Host inputs and source rotation content verified. The existing private host CFG was not inspected.")
            print("No writes, downloads or containers started. Add --apply to prepare.")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Host preparation failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
