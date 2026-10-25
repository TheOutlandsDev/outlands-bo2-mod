#!/usr/bin/env python3
"""Build an allowlisted source ZIP with no game/runtime/private host data."""
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
ROOT_FILES = {"README.md", "LICENSE", "NOTICE.md", "VERSION", ".gitignore",
              "setup-client-linux.sh", "setup-client-windows.cmd", "setup-client-windows.ps1",
              "launch-linux.sh", "launch-windows.cmd", "play-lan-linux.sh", "play-lan-windows.cmd",
              "play-outlands-linux.sh", "play-outlands-windows.cmd"}
HOST_FILES = {"README.md", ".gitignore", ".env.example", "Dockerfile", "Dockerfile.dockerignore",
              "Ollama.Dockerfile", "Ollama.Dockerfile.dockerignore", "compose.yaml",
              "compose.smoke.yaml", "compose.ai.yaml", "compose.dockhand.yaml",
              "compose.dockhand.ai.yaml", "manage.sh", "docker.sh", "entrypoint.py",
              "healthcheck.py", "store_key.py", "prepare_package.py", "setup_host.py", "export_invite.py"}
AI_FILES = {"README.md", "Dockerfile", "Modelfile", "bridge.py", "tests/test_bridge.py",
            "config.example.json", "personalities.json"}
STORAGE_FILES = {"storage/t6/outlands_t6.cfg", "storage/t6/gamesettings/outlands_tdm.cfg",
                 "storage/t6/scripts/mp/outlands_status.gsc", "storage/t6/scripts/mp/outlands_native_bots.gsc",
                 "storage/t6/scripts/mp/outlands_chat.gsc", "storage/t6/bots.txt"}


def public_files(root: Path = ROOT) -> list[Path]:
    names = set(ROOT_FILES) | STORAGE_FILES
    names |= {"hosting/" + name for name in HOST_FILES}
    names |= {"ai/" + name for name in AI_FILES}
    for directory, suffixes in (("tools", {".py", ".ps1"}), ("tests", {".py"}), ("docs", {".md"})):
        base = root / directory
        if base.exists():
            names |= {p.relative_to(root).as_posix() for p in base.rglob("*") if p.suffix in suffixes and "__pycache__" not in p.parts}
    files = []
    for name in sorted(names):
        path = root / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Refusing a linked or nonregular public source: {name}")
        if any(part.is_symlink() for part in path.parents if part != root.parent):
            raise ValueError(f"Source path contains a link: {name}")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        if b"\0" in raw or len(raw) > 512 * 1024:
            raise ValueError(f"Unexpected binary or oversized source: {name}")
        addresses = re.findall(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])", text)
        has_tailnet_address = False
        for address in addresses:
            try:
                has_tailnet_address |= ipaddress.ip_address(address) in ipaddress.ip_network((0x64400000, 10))
            except ValueError:
                pass
        if has_tailnet_address or re.search(r"/home/[A-Za-z0-9_.-]+/", text):
            raise ValueError(f"Private development setup appears in public source: {name}")
        files.append(path)
    required = {"README.md", "LICENSE", "NOTICE.md", "VERSION", "setup-client-linux.sh",
                "setup-client-windows.cmd", "tools/setup_client.py", *STORAGE_FILES}
    if not required <= {p.relative_to(root).as_posix() for p in files}:
        raise ValueError("The distributable source is incomplete")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new ZIP path; without it, audit only")
    parser.add_argument("--json", action="store_true", help="emit path/mode/content for Git tree creation")
    options = parser.parse_args()
    try:
        files = public_files()
        if options.json:
            print(json.dumps([{"path": p.relative_to(ROOT).as_posix(), "mode": "100755" if p.suffix == ".sh" else "100644",
                               "type": "blob", "content": p.read_text(encoding="utf-8-sig")} for p in files]))
            return 0
        if options.output:
            options.output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(options.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in files:
                    info = zipfile.ZipInfo("outlands-bo2-mod/" + path.relative_to(ROOT).as_posix(), (2026, 1, 1, 0, 0, 0))
                    mode = 0o755 if path.suffix == ".sh" else 0o644
                    info.external_attr = (stat.S_IFREG | mode) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
            print("SHA256 " + hashlib.sha256(options.output.read_bytes()).hexdigest())
        print(f"PASS: {len(files)} allowlisted text sources; no BO2 files, vendor binaries, runtime, invites or server state.")
        return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(f"Release audit failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
