#!/usr/bin/env python3
"""Check the dedicated socket and the diagnostic script's startup marker."""

import os
from pathlib import Path
import sys


def main():
    port = int(os.environ.get("T6_PORT", "4977"))
    expected = f"{port:04X}"
    bound = False
    for name in ("/proc/net/udp", "/proc/net/udp6"):
        path = Path(name)
        if path.exists():
            for row in path.read_text().splitlines()[1:]:
                fields = row.split()
                if len(fields) > 1 and fields[1].rsplit(":", 1)[-1] == expected:
                    bound = True
    log = Path("/data/plutonium/console.log")
    if not bound or not log.exists():
        return 1
    # Do not emit log contents: future runtime logs may contain host details.
    with log.open("rb") as handle:
        handle.seek(max(0, log.stat().st_size - 2_000_000))
        recent = handle.read()
    return 0 if b'GSC Executed "scripts/mp/outlands_status::init()"' in recent else 1


if __name__ == "__main__":
    sys.exit(main())
