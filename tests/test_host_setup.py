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
        self.source_cfg = self.project / "storage/t6/outlands_t6.cfg"
        self.source_cfg.parent.mkdir(parents=True)
        self.source_cfg.write_text((SOURCE / "storage/t6/outlands_t6.cfg").read_text())
        self.game = self.game_fixture("Owned Game Fixture")
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

    def game_fixture(self, name):
        path = self.root / name
        rotation, mode, _ = SETUP.content_inventory.configured_rotation(self.source_cfg)
        entries, _ = SETUP.content_inventory.parse_rotation(rotation, mode)
        files = set(SETUP.REQUIRED_GAME) | {"zone/all/" + entry["map_id"] + ".ff" for entry in entries}
        for relative in files:
            target = path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"synthetic non-game fixture")
        for relative in ("zone", "sound", "video", "redist", "Soundtrack"):
            (path / relative).mkdir(parents=True, exist_ok=True)
        return path

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
        validator = SETUP.validate_game
        def checked_game(value):
            result = validator(Path(value))
            self.game_calls.append(result)
            return result
        with patch.object(SETUP, "HOSTING", self.hosting), patch.object(SETUP, "PROJECT", self.project), \
                patch.object(SETUP, "validate_game", side_effect=checked_game), \
                patch.object(SETUP, "download_manifest", side_effect=AssertionError("Unexpected network request")), \
                patch.object(SETUP.subprocess, "run", side_effect=lambda args, **kwargs: self.calls.append(args)), \
                patch.object(sys, "argv", ["setup_host.py", *arguments]), redirect_stdout(output), redirect_stderr(output):
            result = SETUP.main()
        self.assertEqual(result, expected, output.getvalue())
        return output.getvalue()

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
        override_game = self.game_fixture("Explicit Game")
        before = self.snapshot()
        self.run_setup(["--game-dir", str(override_game), "--plutonium-dir", str(override_runtime),
                        "--manifest", str(override_manifest)])
        self.assertEqual(self.staged_paths(), (str(override_runtime), str(override_manifest)))
        self.assertEqual(self.game_calls[-1], override_game)
        self.assertEqual(self.snapshot(), before)

    def test_missing_manifest_readonly_does_not_download_or_write(self):
        before = self.snapshot()
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium)], expected=1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [])

    def test_missing_selected_map_fails_before_download_staging_or_settings_writes(self):
        # Drone is in the source rotation, beyond the old three-map preflight.
        (self.game / "zone/all/mp_drone.ff").unlink()
        missing_manifest = self.root / "must not be downloaded" / "manifest.json"
        before = self.snapshot()
        output = self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                                 "--manifest", str(missing_manifest), "--apply"], expected=1)
        self.assertIn("does not cover the source rotation", output)
        self.assertNotIn(str(self.root), output)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.hosting / "host-settings.json").exists())
        for name in ("manage.sh", "docker.sh"):
            self.assertEqual((self.hosting / name).stat().st_mode & 0o777, 0o644)

    def test_empty_core_asset_fails_source_inventory_before_apply(self):
        (self.game / "zone/all/common_mp.ff").write_bytes(b"")
        before = self.snapshot()
        output = self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                                 "--manifest", str(self.manifest), "--apply"], expected=1)
        self.assertIn("does not cover the source rotation", output)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.snapshot(), before)

    def test_optional_dlc_is_required_only_when_selected_by_source_rotation(self):
        self.assertFalse((self.game / "zone/all/mp_hydro.ff").exists())
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                        "--manifest", str(self.manifest)])
        self.calls.clear()
        self.source_cfg.write_text('sv_maprotation "gametype dom map mp_hydro"\n')
        before = self.snapshot()
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                        "--manifest", str(self.manifest), "--apply"], expected=1)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.calls, [])
        (self.game / "zone/all/mp_hydro.ff").write_bytes(b"synthetic selected DLC map")
        before = self.snapshot()
        self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                        "--manifest", str(self.manifest)])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.snapshot(), before)

    def test_source_only_preflight_does_not_read_private_operator_cfg(self):
        private = self.plutonium / "storage/t6/outlands_t6.cfg"
        private.parent.mkdir(parents=True)
        private.write_text('g_password "PRIVATE_SENTINEL"\n'
                           'sv_maprotation "gametype sd map mp_hydro"\n')
        before = self.snapshot()
        checked = SETUP.content_inventory.configured_rotation
        with patch.object(SETUP.content_inventory, "configured_rotation", wraps=checked) as rotation:
            output = self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                                     "--manifest", str(self.manifest)])
        rotation.assert_called_once_with(self.source_cfg)
        self.assertIn("existing private host CFG was not inspected", output)
        self.assertNotIn("PRIVATE_SENTINEL", output)
        self.assertEqual(self.snapshot(), before)

    def test_unsupported_or_malformed_source_rotation_fails_with_safe_error(self):
        for rotation in ('gametype sd map mp_raid', 'gametype dom map ../../PRIVATE_SENTINEL'):
            with self.subTest(rotation=rotation.split()[1]):
                self.source_cfg.write_text('g_password "PRIVATE_SENTINEL"\nsv_maprotation "' + rotation + '"\n')
                before = self.snapshot()
                output = self.run_setup(["--game-dir", str(self.game), "--plutonium-dir", str(self.plutonium),
                                         "--manifest", str(self.manifest), "--apply"], expected=1)
                self.assertNotIn("PRIVATE_SENTINEL", output)
                self.assertNotIn(str(self.root), output)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
