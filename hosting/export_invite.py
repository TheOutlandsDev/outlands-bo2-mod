#!/usr/bin/env python3
"""Export a private friend invite from this running Outlands server."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

HOSTING = Path(__file__).resolve().parent


def capture(arguments: list[str]) -> str:
    result = subprocess.run([str(HOSTING / "docker.sh"), "compose", "-f",
                             str(HOSTING / "compose.dockhand.yaml"), *arguments],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError("Could not read the running host. Start its Tailscale and game services first.")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HOSTING.parent / "runtime/invites/outlands-dev.invite.json")
    options = parser.parse_args()
    try:
        target = options.output.expanduser().absolute()
        if target.exists() or target.is_symlink():
            raise ValueError("Invite output already exists. Choose a new output filename.")
        # Do not put the password in arguments, stdout or a generated public CFG.
        secret_reader = (
            'import json,os,re; from pathlib import Path; '
            'text=Path("/data/plutonium/storage/t6/outlands_t6.cfg").read_text(); '
            'matches=re.findall(r\'^g_password\\s+"([^"\\r\\n]+)"\\s*$\',text,re.M); '
            'assert len(matches)==1; '
            'print(json.dumps({"join_password":matches[0],"server_port":int(os.environ.get("T6_PORT","4977"))}))'
        )
        settings = json.loads(capture(["exec", "-T", "t6", "python3", "-c", secret_reader]))
        address = capture(["exec", "-T", "tailscale", "tailscale", "ip", "-4"])
        address = str(ipaddress.IPv4Address(address))
        password = settings["join_password"]
        if not isinstance(password, str) or not password or any(ord(c) < 33 or c in '";\\' for c in password):
            raise ValueError("Stored join password is not supported by the invite format")
        value = {"schema_version": 1, "server_address": address,
                 "server_port": settings["server_port"], "join_password": password}
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        print(f"Private invite saved: {target}")
        print("Share privately with trusted dev players on your tailnet. Never upload it to GitHub.")
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"Invite export failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
