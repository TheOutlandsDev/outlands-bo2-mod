#!/usr/bin/env python3
"""Inspect local T6 prerequisites without launching or changing anything."""

import argparse
from pathlib import Path
import shutil
import sys


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, default=project.parent)
    parser.add_argument("--plutonium-dir", type=Path,
                        help="Active Plutonium directory containing bin/ and storage/")
    args = parser.parse_args()
    missing = []

    def check(label, ok):
        print(f"{'OK' if ok else 'MISSING'}: {label}")
        if not ok:
            missing.append(label)

    check("BO2 multiplayer executable", (args.game_dir / "t6mp.exe").is_file())
    for name in ("mp_raid", "mp_hijacked", "mp_village"):
        check(f"map asset {name}.ff",
              (args.game_dir / "zone" / "all" / f"{name}.ff").is_file())

    check("Tailscale command", shutil.which("tailscale") is not None)
    print("INFO: Tailscale account state, peers and network access are not queried.")

    if args.plutonium_dir is None:
        check("explicit active Plutonium directory (--plutonium-dir)", False)
    else:
        check("Plutonium bootstrapper",
              (args.plutonium_dir / "bin" / "plutonium-bootstrapper-win32.exe").is_file())
        storage = args.plutonium_dir / "storage" / "t6"
        for source in sorted((project / "storage" / "t6").rglob("*")):
            if source.is_file():
                relative = source.relative_to(project / "storage" / "t6")
                check(f"staged payload installed: {relative}",
                      (storage / relative).is_file())

    if sys.platform != "win32":
        print("INFO: Linux needs a separately verified Wine/Proton setup. "
              "Its presence and compatibility are not tested here.")
    print("INFO: This file check does not prove bots, progression or private networking.")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
