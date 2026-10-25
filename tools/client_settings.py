#!/usr/bin/env python3
"""Read non-secret client settings; validate private inputs without echoing them."""

import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys

FIELDS = ("steam_dir", "proton_path", "game_dir", "plutonium_dir", "client_port")


def load_settings(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16384:
        raise ValueError("Client settings must be a small regular JSON file.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("Client settings are not readable JSON.") from None
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        raise ValueError("Client settings contain unsupported fields.")
    for key, value in data.items():
        if key == "client_port":
            validate_port(value)
        elif not isinstance(value, str) or any(c in value for c in "\0\r\n"):
            raise ValueError("Client settings contain an invalid path.")
    return data


def validate_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9 _.~-]{1,24}", value):
        raise ValueError("Name must contain 1-24 ASCII letters, numbers, spaces, dots, underscores, tildes or hyphens.")
    if value.startswith(" ") or value.endswith(" "):
        raise ValueError("Name cannot begin or end with a space.")
    return value


def read_name(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("A saved player name is missing or is not a regular file.")
    try:
        data = path.read_bytes()
        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n"):
            data = data[:-1]
        return validate_name(data.decode("ascii"))
    except (OSError, UnicodeError, ValueError):
        raise ValueError("The saved player name must contain one valid ASCII name.") from None


def validate_port(value):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,5}", str(value)):
        raise ValueError("Port must be an integer from 1 to 65535.")
    result = int(value)
    if not 1 <= result <= 65535:
        raise ValueError("Port must be an integer from 1 to 65535.")
    return result


def validate_address(value):
    # T6 direct-connect uses IPv4 or a DNS name, optionally followed by :port.
    if not isinstance(value, str) or value.count(":") > 1:
        raise ValueError("Host must be an IPv4 address or DNS name with an optional :port.")
    host, separator, port = value.partition(":")
    server_port = validate_port(port) if separator else 4977
    if re.fullmatch(r"[0-9.]+", host or ""):
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            raise ValueError("Host must contain a valid IPv4 address.") from None
    elif (len(host) > 253 or not host or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split("."))):
        raise ValueError("Host must contain a valid DNS name.")
    return f"{host}:{server_port}"


def validate_password(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(
            ord(c) < 32 or ord(c) > 126 or c in '\\";/' for c in value):
        raise ValueError("Password must be 1-128 printable ASCII characters, excluding quotes, slashes, backslashes and semicolons.")
    return value


def validate_join_file(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Private join CFG is missing or is not a small regular file.")
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        raise ValueError("Private join CFG must be readable ASCII.") from None
    if len(lines) != 2:
        raise ValueError("Private join CFG must contain only password and connect commands.")
    match = re.fullmatch(r'password "([^"]*)"', lines[0])
    connect = re.fullmatch(r"connect ([^\s]+)", lines[1])
    if not match or not connect:
        raise ValueError("Private join CFG does not match the expected command format.")
    validate_password(match[1])
    validate_address(connect[1])


def load_invite(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("Private invite must be a small regular JSON file.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("Private invite is not readable JSON.") from None
    if (not isinstance(data, dict) or set(data) != {"schema_version", "server_address", "server_port", "join_password"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1):
        raise ValueError("Private invite must use schema_version 1 and the documented fields.")
    host = data["server_address"]
    if not isinstance(host, str) or ":" in host:
        raise ValueError("Invite server_address must contain an IPv4 address or DNS name without a port.")
    address = validate_address(f"{host}:{validate_port(data['server_port'])}")
    return address, validate_password(data["join_password"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", type=Path, required=True,
                        help="Emit five validated non-secret fields, separated by NUL, for launch helpers.")
    args = parser.parse_args()
    try:
        data = load_settings(args.emit)
    except (OSError, ValueError) as error:
        print(f"Outlands client: {error}", file=sys.stderr)
        return 1
    for key in FIELDS:
        sys.stdout.buffer.write(str(data.get(key, "")).encode("utf-8") + b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
