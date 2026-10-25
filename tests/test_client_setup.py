"""Client regression checks using synthetic files only; no downloads or game runs.

Run: python3 -B -m unittest discover -s tests -v
Linux flow tests require Bash. These do not execute the Windows installers.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("outlands_client_settings", SOURCE / "tools/client_settings.py")
SETTINGS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETTINGS)
TEST_PASSWORD = "synthetic-test-value-not-a-credential"
INVITE = dict(schema_version=1, server_address="example.invalid", server_port=4977,
              join_password=TEST_PASSWORD)


class InviteTests(unittest.TestCase):
    def test_invite_rejects_cfg_injection_and_invalid_schema(self):
        mutations = [
            {"server_address": "example.invalid;quit"},
            {"server_address": "example.invalid\nquit"},
            {"server_address": 'example.invalid"'},
            {"server_address": "example.invalid:4977"},
            {"join_password": 'bad";quit'}, {"join_password": "bad\nquit"},
            {"join_password": "bad;quit"}, {"join_password": "bad\\escape"},
            {"join_password": "bad//comment"}, {"server_port": 0},
            {"server_port": 65536}, {"schema_version": True},
            {"schema_version": 2}, {"unexpected": "field"},
        ]
        with tempfile.TemporaryDirectory(prefix="outlands-invite-test-") as directory:
            path = Path(directory) / "private-invite.json"
            path.write_text(json.dumps(INVITE))
            self.assertEqual(SETTINGS.load_invite(path), ("example.invalid:4977", TEST_PASSWORD))
            for mutation in mutations:
                with self.subTest(mutation=list(mutation)):
                    path.write_text(json.dumps({**INVITE, **mutation}))
                    with self.assertRaises(ValueError) as error:
                        SETTINGS.load_invite(path)
                    self.assertNotIn(TEST_PASSWORD, str(error.exception))
                    self.assertNotIn("example.invalid", str(error.exception))


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Linux client flow needs Bash")
class LinuxClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="outlands-client-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "Source Clone With Spaces"
        (self.project / "tools").mkdir(parents=True)
        self.shell_helpers = ("setup-client-linux.sh", "play-lan-linux.sh", "play-outlands-linux.sh", "launch-linux.sh")
        for name in self.shell_helpers:
            shutil.copy2(SOURCE / name, self.project / name)
            (self.project / name).chmod(0o644)
        for name in ("setup_client.py", "client_settings.py"):
            shutil.copy2(SOURCE / "tools" / name, self.project / "tools" / name)
        self.steam = self.root / "Fake Steam"
        self.steam.mkdir()
        self.game = self.root / "Owned Game Fixture Outside Clone"
        self.plutonium = self.root / "Private Runtime Fixture"
        self.prefix = self.project / "runtime/compatdata/pfx"
        for path in (self.game / "t6mp.exe", self.game / "zone/all/code_pre_gfx_mp.ff",
                     self.game / "zone/all/common_mp.ff", self.prefix / "system.reg",
                     self.plutonium / "bin/plutonium-bootstrapper-win32.exe",
                     self.plutonium / "games/t6mp.exe"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic fixture; never executed")
        (self.prefix / "dosdevices").mkdir()
        (self.prefix / "dosdevices/z:").symlink_to("/")
        self.marker = self.root / "UNEXPECTED_EXTERNAL_COMMAND"
        self.proton = self.root / "Fake Proton"
        fakebin = self.root / "bin"
        fakebin.mkdir()
        for executable in (self.proton, fakebin / "tailscale"):
            executable.write_text("#!/bin/sh\ntouch " + shlex.quote(str(self.marker)) + "\nexit 97\n")
            executable.chmod(0o755)
        self.storage = self.plutonium / "storage/t6"
        self.storage.mkdir(parents=True)
        self.name = self.storage / "outlands_player_name.txt"
        self.name.write_text("Saved Player\n")
        self.name.chmod(0o600)
        self.join = self.storage / "outlands_join.cfg"
        self.join.write_text('password "older-synthetic-value"\nconnect example.invalid:4977\n')
        self.join.chmod(0o600)
        self.stats = self.plutonium / "storage/demonware/profile/stats.dat"
        self.stats.parent.mkdir(parents=True)
        self.stats.write_bytes(b"existing earned profile fixture")
        self.config = self.project / "runtime/client.json"
        self.config.write_text(json.dumps(dict(steam_dir=str(self.steam), proton_path=str(self.proton),
                                               game_dir=str(self.game), plutonium_dir=str(self.plutonium), client_port=4976)))
        self.invite = self.root / "private-invite.json"
        self.invite.write_text(json.dumps(INVITE))
        self.environment = {key: value for key, value in os.environ.items() if not key.startswith("OUTLANDS_")}
        self.environment.update(PATH=str(fakebin) + os.pathsep + self.environment["PATH"],
                                PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(self.project / "tools"))

    def snapshot(self):
        result = {}
        for path in self.root.rglob("*"):
            relative = str(path.relative_to(self.root))
            if path.is_symlink():
                result[relative] = ("symlink", os.readlink(path))
            else:
                stat = path.stat()
                digest = hashlib.sha256(path.read_bytes()).digest() if path.is_file() else None
                result[relative] = (stat.st_mode, stat.st_mtime_ns, digest)
        return result

    def run_client(self, arguments, expected=0, readonly=True):
        before = self.snapshot()
        result = subprocess.run(arguments, env=self.environment, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn(TEST_PASSWORD, result.stdout + result.stderr)
        self.assertNotIn("example.invalid", result.stdout + result.stderr)
        self.assertFalse(self.marker.exists(), "A fake Proton/Tailscale command was unexpectedly executed")
        if readonly:
            self.assertEqual(before, self.snapshot(), "Validation changed fixture files")
        return result

    def test_check_and_dry_run_are_read_only_outside_game_folder(self):
        for script, options in (("setup-client-linux.sh", ["--dry-run", "--invite", str(self.invite)]),
                                ("setup-client-linux.sh", ["--check"]),
                                ("play-lan-linux.sh", ["--join", "--check"])):
            with self.subTest(script=script, options=options[:1]):
                self.run_client(["bash", str(self.project / script), *options])
        for name in self.shell_helpers:
            self.assertEqual((self.project / name).stat().st_mode & 0o777, 0o644)

    def test_missing_or_malformed_saved_name_rejects_without_writes(self):
        for contents in (None, b" Saved Player\n", b"Saved Player \n", b"Saved Player\n\n", b"Saved\0Player\n"):
            with self.subTest(contents=contents):
                self.name.unlink(missing_ok=True)
                if contents is not None:
                    self.name.write_bytes(contents)
                self.run_client(["bash", str(self.project / "setup-client-linux.sh"), "--check"], expected=1)

    def test_apply_preserves_profile_identity_and_private_permissions(self):
        before_stats = self.stats.read_bytes()
        runner = ("import setup_client,sys;from unittest.mock import patch\n"
                  "with patch('sys.stdin.isatty',return_value=True),patch('builtins.input',side_effect=['','','','','n']):\n"
                  " raise SystemExit(setup_client.main(sys.argv[1:]))\n")
        self.run_client([sys.executable, "-B", "-c", runner, "--skip-updater", "--invite", str(self.invite)], readonly=False)
        self.assertEqual(self.stats.read_bytes(), before_stats)
        self.assertEqual(self.name.read_bytes(), b"Saved Player\n")
        self.assertEqual(self.join.read_text(), f'password "{TEST_PASSWORD}"\nconnect example.invalid:4977\n')
        for path in (self.name, self.join, self.config):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for name in self.shell_helpers:
            self.assertEqual((self.project / name).stat().st_mode & 0o777, 0o755)
        settings = json.loads(self.config.read_text())
        self.assertNotIn(TEST_PASSWORD, json.dumps(settings))
        self.assertNotIn("server_address", settings)
        self.run_client([str(self.project / "play-outlands-linux.sh"), "--check"])

    def test_unsupported_secret_argument_is_not_echoed(self):
        self.run_client(["bash", str(self.project / "setup-client-linux.sh"), "--password", TEST_PASSWORD], expected=2)


if __name__ == "__main__":
    unittest.main()
