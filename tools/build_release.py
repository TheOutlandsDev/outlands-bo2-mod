#!/usr/bin/env python3
"""Audit or build the explicit source-only release; never package game or private data."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "LICENSE", "NOTICE.md", "VERSION", ".gitignore", "CHANGELOG.md",
              "setup-client-linux.sh", "setup-client-windows.cmd", "setup-client-windows.ps1",
              "launch-linux.sh", "launch-windows.cmd", "play-lan-linux.sh", "play-lan-windows.cmd",
              "play-outlands-linux.sh", "play-outlands-windows.cmd"}
HOST_FILES = {"README.md", ".gitignore", ".env.example", "Dockerfile", "Dockerfile.dockerignore",
              "Ollama.Dockerfile", "Ollama.Dockerfile.dockerignore", "compose.yaml",
              "compose.smoke.yaml", "compose.ai.yaml", "compose.dockhand.yaml",
              "compose.dockhand.ai.yaml", "manage.sh", "docker.sh", "entrypoint.py",
              "healthcheck.py", "store_key.py", "prepare_package.py", "setup_host.py", "export_invite.py",
              "backend_verify.py", "verification.gsc"}
AI_FILES = {"README.md", "Dockerfile", "Modelfile", "bridge.py", "tests/test_bridge.py",
            "config.example.json", "personalities.json", "careers.py", "tests/test_careers.py", "benchmark.py"}
TOOL_FILES = {"build_release.py", "client_settings.py", "install_files.py", "play_lan_windows.ps1",
              "preflight.py", "setup_client.py", "windows_client.ps1", "content_inventory.py"}
TEST_FILES = {"test_client_setup.py", "test_host_setup.py", "test_host_state.py", "test_release.py",
              "test_windows_client.ps1", "test_backend_verify.py", "test_content_inventory.py"}
DOC_FILES = {"VALIDATION.md", "RELEASING.md", "WINDOWS.md", "METHODOLOGY.md", "RIVALS.md"}
WORKFLOW_FILES = {"ci.yml", "release.yml"}
STORAGE_FILES = {"storage/t6/outlands_t6.cfg", "storage/t6/gamesettings/outlands_tdm.cfg",
                 "storage/t6/gamesettings/outlands_dm.cfg", "storage/t6/gamesettings/outlands_ctf.cfg",
                 "storage/t6/gamesettings/outlands_dem.cfg", "storage/t6/gamesettings/outlands_dom.cfg",
                 "storage/t6/gamesettings/outlands_koth.cfg", "storage/t6/gamesettings/outlands_hq.cfg",
                 "storage/t6/gamesettings/outlands_conf.cfg",
                 "storage/t6/scripts/mp/outlands_status.gsc", "storage/t6/scripts/mp/outlands_native_bots.gsc",
                 "storage/t6/scripts/mp/outlands_bot_identity.gsc", "storage/t6/scripts/mp/outlands_bot_profiles.gsc",
                 "storage/t6/scripts/mp/outlands_bot_careers.gsc",
                 "storage/t6/scripts/mp/outlands_chat.gsc", "storage/t6/bots.txt"}
PUBLIC_PATHS = frozenset(ROOT_FILES | STORAGE_FILES
                        | {"hosting/" + name for name in HOST_FILES}
                        | {"ai/" + name for name in AI_FILES}
                        | {"tools/" + name for name in TOOL_FILES}
                        | {"tests/" + name for name in TEST_FILES}
                        | {"docs/" + name for name in DOC_FILES}
                        | {".github/workflows/" + name for name in WORKFLOW_FILES})
ARCHIVE_PREFIX = "outlands-bo2-mod/"
ZIP_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
MAX_SOURCE_BYTES = 512 * 1024
TAILNET_NETWORK = ipaddress.ip_network((0x64400000, 10))
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
                             r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")


def release_version(root: Path = ROOT) -> str:
    """Return the bare version used by filenames and the matching v-prefixed Git tag."""
    raw = (root / "VERSION").read_bytes()
    if len(raw) > 128:
        raise ValueError("VERSION must contain one bare release version")
    version = raw.decode("ascii")
    if version.endswith("\n"):
        version = version[:-1]
        if version.endswith("\r"):
            version = version[:-1]
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("VERSION must contain a bare version such as 0.1.1 or 0.1.1-rc.1")
    return version


def public_files(root: Path = ROOT) -> list[Path]:
    """Return all required source files in order; extra files never enter the archive."""
    root = Path(root).absolute()
    resolved_root = root.resolve(strict=True)
    files = []
    for name in sorted(PUBLIC_PATHS):
        path = root / name
        current = root
        for part in Path(name).parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"Source path contains a link: {name}")
        if not path.exists():
            raise ValueError(f"Missing required public source: {name}")
        if not stat.S_ISREG(path.stat().st_mode):
            raise ValueError(f"Refusing a nonregular public source: {name}")
        try:
            path.resolve(strict=True).relative_to(resolved_root)
        except ValueError:
            raise ValueError(f"Public source escapes the project: {name}") from None
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError(f"Unexpected binary or oversized source: {name}")
        raw = path.read_bytes()
        if b"\0" in raw or len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f"Unexpected binary or oversized source: {name}")
        try:
            text = raw.decode("utf-8")
        except UnicodeError:
            raise ValueError(f"Public source is not UTF-8 text: {name}") from None
        addresses = re.findall(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])", text)
        has_tailnet_address = False
        for address in addresses:
            try:
                has_tailnet_address |= ipaddress.ip_address(address) in TAILNET_NETWORK
            except ValueError:
                pass
        private_path = re.search(r"/home/[A-Za-z0-9_.-]+/", text) or re.search(
            r"(?i)\b[A-Z]:[\\/]+Users[\\/]+[^\\/\s\"']+", text)
        private_host = re.search(r"(?i)\b(?:desktop|laptop)-[a-z0-9]{7}\b", text) or re.search(
            r"(?i)\b[a-z0-9.-]+\.ts\.net\b", text)
        if has_tailnet_address or private_path or private_host:
            raise ValueError(f"Private development setup appears in public source: {name}")
        files.append(path)
    release_version(root)
    return files


def source_mode(path: Path) -> int:
    return 0o755 if path.suffix == ".sh" else 0o644


def build_archive(output: Path, files: list[Path], root: Path = ROOT) -> str:
    """Create a new ZIP and SHA256SUMS without overwriting an earlier release."""
    names = [path.relative_to(root).as_posix() for path in files]
    if len(names) != len(PUBLIC_PATHS) or set(names) != PUBLIC_PATHS:
        raise ValueError("Archive inputs must exactly match the public source allowlist")
    output = Path(output)
    if output.suffix.lower() != ".zip" or any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in output.name):
        raise ValueError("Release output must be a .zip filename without control characters or backslashes")
    checksum = output.parent / "SHA256SUMS"
    if output.exists() or output.is_symlink() or checksum.exists() or checksum.is_symlink():
        raise ValueError("Release output or SHA256SUMS already exists; choose a fresh output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with output.open("xb") as target:
            created.append(output)
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
                    info = zipfile.ZipInfo(ARCHIVE_PREFIX + path.relative_to(root).as_posix(), ZIP_TIMESTAMP)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | source_mode(path)) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes(), compresslevel=9)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        with checksum.open("x", encoding="utf-8", newline="\n") as target:
            created.append(checksum)
            target.write(f"{digest}  {output.name}\n")
        return digest
    except Exception:
        for path in reversed(created):
            path.unlink()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--output", type=Path, help="new ZIP path; also create adjacent SHA256SUMS")
    operation.add_argument("--json", action="store_true", help="emit path/mode/content for Git tree creation")
    operation.add_argument("--version", action="store_true", help="print the bare VERSION for tag checks")
    options = parser.parse_args()
    try:
        if options.version:
            print(release_version(ROOT))
            return 0
        files = public_files(ROOT)
        if options.json:
            print(json.dumps([{"path": p.relative_to(ROOT).as_posix(),
                               "mode": f"100{source_mode(p):o}", "type": "blob",
                               "content": p.read_bytes().decode("utf-8")} for p in files]))
            return 0
        if options.output:
            print("SHA256 " + build_archive(options.output, files, ROOT))
        print(f"PASS: {len(files)} allowlisted text sources; no BO2 files, vendor binaries, runtime, invites or server state.")
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Release audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
