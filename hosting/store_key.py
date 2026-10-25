#!/usr/bin/env python3
"""Store a dedicated server key from stdin inside the persistent data volume."""

import os
from pathlib import Path
import sys

from entrypoint import StartupError, atomic_write, ensure_directory


def main():
    key = sys.stdin.read().strip()
    if not key or any(c.isspace() or ord(c) < 32 or c in '\";\\' for c in key):
        print('Expected a nonempty, single-line dedicated server key.', file=sys.stderr)
        return 1
    os.umask(0o077)
    directory = Path('/data/private')
    ensure_directory(directory)
    directory.chmod(0o700)
    atomic_write(directory / 'plutonium_server_key', key.encode(), 0o600)
    print('Dedicated server key saved in the persistent container data volume.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, StartupError):
        print('Could not write the dedicated server key to the data volume.', file=sys.stderr)
        raise SystemExit(1)
