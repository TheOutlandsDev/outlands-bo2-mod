#!/usr/bin/env python3
"""Preview or install the staged T6 files into an existing Plutonium runtime."""

import argparse
import os
from pathlib import Path
import secrets
import sys


PLACEHOLDER = "REPLACE_WITH_A_PRIVATE_JOIN_PASSWORD"


def default_runtime(project):
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Plutonium"
    return (project / "runtime/compatdata/pfx/drive_c/users/steamuser"
            / "AppData/Local/Plutonium")


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plutonium-dir", type=Path,
                        default=default_runtime(project))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    runtime = args.plutonium_dir.resolve()
    if not (runtime / "bin/plutonium-bootstrapper-win32.exe").is_file():
        parser.error("Run the official updater first, or select the active Plutonium directory.")

    source_root = project / "storage/t6"
    destination_root = runtime / "storage/t6"
    pending = []
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        destination = destination_root / relative
        if destination.is_symlink():
            parser.error(f"Refusing a symlink destination: {destination}")
        if destination.exists():
            # A generated host CFG contains a private password and local edits.
            if relative == Path("outlands_t6.cfg"):
                print(f"KEEP existing host configuration: {relative}")
                continue
            if destination.read_bytes() != source.read_bytes():
                parser.error(f"Existing file differs; review it before replacing: {destination}")
            print(f"UNCHANGED: {relative}")
            continue
        pending.append((source, destination, relative))

    for source, destination, relative in pending:
        print(f"{'INSTALL' if args.apply else 'WOULD INSTALL'}: {relative}")
        if not args.apply:
            continue
        contents = source.read_text()
        if relative == Path("outlands_t6.cfg"):
            contents = contents.replace(PLACEHOLDER, secrets.token_urlsafe(24))
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation keeps an existing installation from being overwritten.
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
        if os.name == "posix":
            destination.chmod(0o600 if relative == Path("outlands_t6.cfg") else 0o644)

    print(f"{'Installed in' if args.apply else 'Preview destination'}: {destination_root}")
    print("The private join password is in the installed outlands_t6.cfg; it is not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
