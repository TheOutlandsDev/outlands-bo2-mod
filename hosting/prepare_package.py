#!/usr/bin/env python3
"""Verify and stage official Plutonium files without copying client credentials."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def sha1(path):
    value = hashlib.sha1()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    hosting = Path(__file__).resolve().parent
    project = hosting.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plutonium-dir", type=Path, default=(
        project / "runtime/compatdata/pfx/drive_c/users/steamuser/AppData/Local/Plutonium"))
    parser.add_argument("--manifest", type=Path,
                        default=project / "runtime/downloads/plutonium-manifest.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    source = args.plutonium_dir.resolve()
    revision = json.loads((source / "info.json").read_text())["revision"]
    if manifest["revision"] != revision:
        parser.error("Installed runtime and vendor manifest revisions differ; update before packaging.")
    destination = hosting / "package/plutonium"
    entries = []
    names = set()
    for entry in manifest["files"]:
        name = PurePosixPath(entry["name"])
        if (name.is_absolute() or ".." in name.parts or "\\" in str(name)
                or not name.parts or name.parts[0] not in {"bin", "games", "storage"}
                or str(name) in names):
            parser.error("Unexpected path in official file manifest.")
        names.add(str(name))
        path = source.joinpath(*name.parts)
        if path.is_symlink() or not path.is_file():
            parser.error(f"Missing regular vendor file: {name}")
        if path.stat().st_size != entry["size"] or sha1(path) != entry["hash"]:
            parser.error(f"Vendor file differs from the official manifest: {name}")
        target = destination.joinpath(*name.parts)
        if target.exists() and (target.is_symlink() or not target.is_file()
                                or sha1(target) != entry["hash"]):
            parser.error(f"Existing package differs: {name}")
        entries.append((path, target))

    if destination.exists():
        actual = {p.relative_to(destination).as_posix()
                  for p in destination.rglob("*") if p.is_file()}
        if actual - names - {"info.json"}:
            parser.error("Existing package has files absent from the vendor manifest.")
    print(f"Verified {len(entries)} vendor files for Plutonium r{revision}.")
    print("Client config.json, login token and unlisted profile files are excluded.")
    if not args.apply:
        print("Preview only. Add --apply to create the private build package.")
        return 0
    for path, target in entries:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    metadata = {"revision": revision, "launchTarget": "bin/plutonium-launcher-win32.exe"}
    (destination / "info.json").write_text(json.dumps(metadata) + "\n")
    print(f"Private build package prepared: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
