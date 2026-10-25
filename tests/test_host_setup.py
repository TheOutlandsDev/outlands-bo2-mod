"""Headless host-path regression checks; no game assets, Docker or network."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("outlands_setup_host", SOURCE / "hosting/setup_host.py")
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


@unittest.skipUnless(os.name == "posix", "Container-host preparation targets Linux")
class HostSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="outlands-host-setup-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "Headless Source Clone"
        self.hosting = self.project / "hosting"
        self.hosting.mkdir(parents=True)
        self.game = self.root / "Owned Game Fixture"
        self.game.mkdir()
        self.plutonium = self.runtime("External Plutonium Fixture")
        self.manifest = self.root / "Custom Metadata" / "official-manifest.json"
        self.manifest.parent.mkdir()
        self.manifest.write_text('{"revision":1,"files":[]}')
        for name in ("manage.sh", "docker.sh"):
            path = self.hosting / name
            path.write_text("#!/bin/sh\nexit 97\n")
            path.chmod(0o644)
        self.calls = []
        self.game_calls = []

    def runtime(self, name):
        path = self.root / name
        path.mkdir()
        (path / "info.json").write_text('{"revision":1}')
        return path

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.stat().st_mode, p.stat().st_mtime_ns,
                hashlib.sha256(p.read_bytes()).digest() if p.is_file() else None)
                for p in self.root.rglob("*")}

    def run_setup(self, arguments, expected=0):
        output = io.StringIO()
        def checked_game(value):
            result = Path(value).resolve()
            self.game_calls.append(result)
            return result
        with patch.object(SETUP, "HOSTING", self.hosting), patch.object(SETUP, "PROJECT", self.project), \
                patch.object(SETUP, "validate_game", side_effect=checked_game), \
                patch.object(SETUP, "download_manifest", side_effect=AssertionError("Unexpected network request")), \
                patch.object(SETUP.subprocess, "run", side_effect=lambda args, **kwargs: self.calls.append(args)), \
                patch.object(sys, "argv", ["setup_host.py", *arguments]), redirect_stdout(output), redirect_stderr(output):
            result = SETUP.main()
        self.assertEqual(result, expected, output.getvalue())

    def staged_paths(self):
        call = self.calls[-1]
        return call[call.index("--plutonium-dir") + 1], call[call.index("--manifest") + 1]

    def test_headless_apply_remembers_external_runtime_and_custom_manifest(self):
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                        "--manifest", str(self.manifest), "--apply"])
        saved = self.hosting / "host-settings.json"
        self.assertEqual(json.loads(saved.read_text()), {"plutonium_dir": str(self.plutonium), "manifest": str(self.manifest)})
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.project / "runtime/client.json").exists())
        self.run_setup(["--apply"])
        self.assertEqual(self.staged_paths(), (str(self.plutonium), str(self.manifest)))
        self.assertFalse((self.project / "runtime/client.json").exists())
        for name in ("manage.sh", "docker.sh"):
            self.assertEqual((self.hosting / name).stat().st_mode & 0o777, 0o755)

    def test_saved_host_paths_win_over_client_settings_and_cli_wins_over_saved(self):
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                        "--manifest", str(self.manifest), "--apply"])
        client_runtime = self.runtime("Different Client Runtime")
        (self.project / "runtime").mkdir()
        (self.project / "runtime/client.json").write_text(json.dumps({"plutonium_dir": str(client_runtime),
                                                                     "game_dir": str(self.root / "Client Game")}))
        for name in ("manage.sh", "docker.sh"):
            (self.hosting / name).chmod(0o644)
        before = self.snapshot()
        self.run_setup([])
        self.assertEqual(self.staged_paths(), (str(self.plutonium), str(self.manifest)))
        self.assertEqual(self.game_calls[-1], self.game)
        self.assertEqual(self.snapshot(), before, "Read-only host validation wrote files or modes")
        override_runtime = self.runtime("Explicit Override Runtime")
        override_manifest = self.root / "override-manifest.json"
        override_manifest.write_text('{"revision":1,"files":[]}')
        before = self.snapshot()
        self.run_setup(["--game-dir", str(self.root / "Explicit Game"), "--plutonium-dir", str(override_runtime),
                        "--manifest", str(override_manifest)])
        self.assertEqual(self.staged_paths(), (str(override_runtime), str(override_manifest)))
        self.assertEqual(self.game_calls[-1], self.root / "Explicit Game")
        self.assertEqual(self.snapshot(), before)

    def test_missing_manifest_readonly_does_not_download_or_write(self):
        before = self.snapshot()
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium)], expected=1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
