#!/usr/bin/env python3
"""Run offline development checks and record their scope against audited source.

This runner never launches BO2, connects to a model/server or reads player saves.
Passing source checks is deliberately separate from UI/client acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_release import ROOT, public_files


def source_digest(root: Path) -> str:
    """Bind evidence to names and bytes of the complete audited public payload."""
    digest = hashlib.sha256()
    for path in public_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def checks() -> list[tuple[str, list[str]]]:
    python = [sys.executable, "-B"]
    commands = [
        ("setup_host_release_regressions", python + ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("career_chat_contract_regressions", python + ["-m", "unittest", "discover", "-s", "ai/tests", "-v"]),
        ("chat_configuration", python + ["ai/bridge.py", "--check"]),
        ("rival_fallback", python + ["ai/benchmark.py", "--mode", "fallback"]),
        ("conversation_fallback", python + ["ai/conversation_benchmark.py", "--mode", "fallback"]),
        ("source_package_audit", python + ["tools/build_release.py"]),
    ]
    if os.name == "nt":
        # Host permission and Wine fixtures require POSIX. Windows has its own
        # PowerShell client suite in CI; do not pretend that ran these fixtures.
        commands[:2] = [("validation_harness_regressions", python + [
            "-m", "unittest", "discover", "-s", "tests", "-p", "test_system_validation.py", "-v"])]
    else:
        script = ("import subprocess; from tools.build_release import public_files; "
                  "[subprocess.run(['bash','-n',str(p)],check=True) "
                  "for p in public_files() if p.suffix=='.sh']")
        commands.append(("bash_syntax", python + ["-c", script]))
    return commands


def pending_acceptance() -> dict:
    # Register actual renderer/client tests here as implementations are added.
    # Do not mark these accepted from successful backend/source checks.
    return {
        "native_engine": {"status": "not_run", "method": "hosting/backend_verify.py"},
        "ui_data_and_navigation": {"status": "not_implemented"},
        "ui_rendering_and_input_windows": {"status": "pending_real_client"},
        "ui_rendering_and_input_linux": {"status": "pending_real_client"},
        "mid_match_loadout_editor": {"status": "not_implemented"},
        "native_progression_after_ui_use": {"status": "pending_real_client"},
    }


def new_directory(path: Path) -> Path:
    path = path.absolute()
    if path.exists() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Choose a fresh report directory without symlink parents")
    path.mkdir(parents=True, mode=0o700)
    return path


def private_write(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as stream:
        if os.name != "nt":
            os.fchmod(stream.fileno(), 0o600)
        stream.write(content)


def run_checks(root: Path, directory: Path, timeout: int = 300) -> dict:
    report = {"schema": 1, "scope": "offline_source", "status": "failed",
              "platform": sys.platform,
              "coverage_profile": "windows_portable_source" if os.name == "nt" else "posix_full_source",
              "created_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": None, "source_unchanged": False, "checks": [],
              "acceptance": pending_acceptance(), "ui_release_ready": False,
              "uses_game_or_player_data": False}
    try:
        before = source_digest(root)
        report["source_sha256"] = before
    except (OSError, ValueError, UnicodeError):
        report["checks"].append({"name": "source_fingerprint", "status": "failed"})
        return report
    for name, command in checks():
        started = time.monotonic()
        status = "failed"
        returncode = None
        log = directory / (name + ".log")
        # Direct-to-file output is bounded by disk rather than process memory.
        # Logs stay private; the summary never copies subprocess text or paths.
        with log.open("x", encoding="utf-8") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            try:
                result = subprocess.run(command, cwd=root, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=timeout,
                                        check=False)
                returncode = result.returncode
                status = "passed" if returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                status = "timed_out"
            except OSError:
                # OS exception strings can contain private executable paths.
                status = "could_not_start"
        report["checks"].append({"name": name, "status": status,
                                 "returncode": returncode,
                                 "seconds": round(time.monotonic() - started, 3)})
    try:
        report["source_unchanged"] = before == source_digest(root)
    except (OSError, ValueError, UnicodeError):
        pass
    if report["source_unchanged"] and all(x["status"] == "passed" for x in report["checks"]):
        report["status"] = "source_passed"
    return report


def exit_code(report: dict, require_ui: bool) -> int:
    if report["status"] != "source_passed":
        return 1
    # This command cannot currently accept the planned UI. Keep release gating
    # closed until real UI implementations and their acceptance tests exist.
    return 2 if require_ui and not report["ui_release_ready"] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, help="fresh private directory (default: runtime/validation/<run>)")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per source check (10-900)")
    parser.add_argument("--require-ui", action="store_true", help="exit 2 if source passes but UI acceptance is pending")
    args = parser.parse_args(argv)
    if not 10 <= args.timeout <= 900:
        parser.error("--timeout must be between 10 and 900")
    try:
        directory = new_directory(args.report_dir or ROOT / "runtime/validation" / uuid.uuid4().hex)
        report = run_checks(ROOT, directory, args.timeout)
        private_write(directory / "report.json", json.dumps(report, indent=2) + "\n")
        for check in report["checks"]:
            print(check["status"].upper() + ": " + check["name"])
        print("Source status: " + report["status"])
        print("Native engine: not run. UI and client acceptance: pending.")
        print("Report: " + str(directory / "report.json"))
        return exit_code(report, args.require_ui)
    except (OSError, ValueError):
        print("Validation could not write a fresh private report directory.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
