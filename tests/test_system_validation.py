"""Exercise validation failures and evidence boundaries, without running BO2."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_system as validation


class SystemValidationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.report_dir = validation.new_directory(self.root / "report")

    def execute(self, outcomes, digests=("a", "a")):
        commands = [("case" + str(i), ["synthetic-check"]) for i in range(len(outcomes))]
        with patch.object(validation, "checks", return_value=commands), \
                patch.object(validation, "source_digest", side_effect=digests), \
                patch.object(validation.subprocess, "run", side_effect=outcomes):
            return validation.run_checks(self.root, self.report_dir, 10)

    def test_success_does_not_accept_unbuilt_ui_native_engine_or_clients(self):
        report = self.execute([subprocess.CompletedProcess([], 0)])
        self.assertEqual(validation.exit_code(report, False), 0)
        self.assertEqual(validation.exit_code(report, True), 2)
        self.assertFalse(report["ui_release_ready"])
        self.assertEqual(report["acceptance"]["native_engine"]["status"], "not_run")
        self.assertTrue(all(x["status"] != "passed" for x in report["acceptance"].values()))

    def test_failure_timeout_and_start_error_continue_checks_and_fail_gate(self):
        report = self.execute([subprocess.CompletedProcess([], 3),
                               subprocess.TimeoutExpired("private-command", 10),
                               OSError("private path and secret"),
                               subprocess.CompletedProcess([], 0)])
        self.assertEqual([x["status"] for x in report["checks"]],
                         ["failed", "timed_out", "could_not_start", "passed"])
        self.assertEqual(validation.exit_code(report, True), 1)
        self.assertNotIn("private", json.dumps(report))

    def test_source_changes_during_run_invalidate_otherwise_passing_evidence(self):
        report = self.execute([subprocess.CompletedProcess([], 0)], ("old", "new"))
        self.assertFalse(report["source_unchanged"])
        self.assertEqual(validation.exit_code(report, False), 1)

    def test_bad_source_stops_before_subprocesses_and_excludes_error_text(self):
        with patch.object(validation, "source_digest", side_effect=ValueError("private path")), \
                patch.object(validation.subprocess, "run") as run:
            report = validation.run_checks(self.root, self.report_dir)
        run.assert_not_called()
        self.assertEqual(validation.exit_code(report, False), 1)
        self.assertNotIn("private", json.dumps(report))

    def test_fingerprint_changes_for_content_and_names_excludes_runtime(self):
        source = self.root / "public.py"
        source.write_bytes(b"original")
        with patch.object(validation, "public_files", side_effect=lambda root: [source]):
            first = validation.source_digest(self.root)
            (self.root / "private-state").write_text("synthetic")
            self.assertEqual(validation.source_digest(self.root), first)
            source.write_bytes(b"changed")
            self.assertNotEqual(validation.source_digest(self.root), first)
            source.write_bytes(b"original")
            source = source.rename(self.root / "renamed.py")
            self.assertNotEqual(validation.source_digest(self.root), first)

    def test_reused_or_symlink_report_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            validation.new_directory(self.report_dir)
        if sys.platform != "win32":
            link = self.root / "link"
            link.symlink_to(self.report_dir, target_is_directory=True)
            with self.assertRaises(ValueError):
                validation.new_directory(link / "nested")
            self.assertEqual(self.report_dir.stat().st_mode & 0o777, 0o700)
            validation.private_write(self.report_dir / "summary.json", "{}")
            self.assertEqual((self.report_dir / "summary.json").stat().st_mode & 0o777, 0o600)

    def test_source_checks_have_no_model_game_or_network_entrypoints(self):
        commands = validation.checks()
        self.assertGreaterEqual(len(commands), 5)
        self.assertEqual(len({name for name, _ in commands}), len(commands))
        for _, command in commands:
            self.assertEqual(command[:2], [sys.executable, "-B"])
            if "--mode" in command:
                self.assertEqual(command[-1], "fallback")
            self.assertNotIn("hosting/backend_verify.py", command)

    def test_windows_profile_uses_portable_fixtures_and_explicitly_omits_posix_suites(self):
        with patch.object(validation.os, "name", "nt"):
            names = [name for name, _ in validation.checks()]
        self.assertIn("validation_harness_regressions", names)
        self.assertNotIn("setup_host_release_regressions", names)
        self.assertNotIn("career_chat_contract_regressions", names)
        self.assertNotIn("bash_syntax", names)


if __name__ == "__main__":
    unittest.main()
