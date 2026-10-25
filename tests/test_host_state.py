"""Persistent hosting boundaries; synthetic files only, no Wine or game assets."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "hosting/entrypoint.py"
SPEC = importlib.util.spec_from_file_location("outlands_host_entrypoint_tests", SOURCE)
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


class HostStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="outlands-host-state-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.data = self.base / "data"
        self.mod = self.base / "mod"
        self.plutonium = self.data / "plutonium"
        self.storage = self.plutonium / "storage/t6"
        self.storage.mkdir(parents=True)
        for relative in host.MOD_PAYLOADS:
            path = self.mod / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic source payload\n", encoding="utf-8")
        (self.mod / host.CFG_NAME).write_text(
            'g_password "REPLACE_WITH_A_PRIVATE_JOIN_PASSWORD"\n'
            'sv_hostname "Synthetic source host"\n'
            'set outlands_chat_enabled "0"\n'
            'rcon_password ""\n', encoding="utf-8")
        self.cfg = self.storage / host.CFG_NAME
        self.cfg.write_text(
            'g_password "synthetic-existing-join-password"\n'
            'sv_hostname "Existing synthetic host"\n'
            'set outlands_chat_enabled "0"\n'
            'rcon_password ""\n'
            'set unrelated_custom_setting "preserve-me"\n', encoding="utf-8")
        self.stats = self.plutonium / "storage/demonware/synthetic-profile/mpstatsCompressed"
        self.stats.parent.mkdir(parents=True)
        self.stats.write_bytes(b"synthetic unrelated player stats\x00\x01\xff")
        self.original_stats = self.stats.read_bytes()
        constants = patch.multiple(host, DATA=self.data, MOD=self.mod, PLUTONIUM=self.plutonium)
        constants.start()
        self.addCleanup(constants.stop)
        environment = patch.dict(os.environ, {"T6_CHAT_ENABLED": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        self.secret = self.data / "private/outlands_rcon_password"

    def value(self, name):
        matches = list(host.assignment_pattern(name).finditer(self.cfg.read_text(encoding="utf-8")))
        self.assertEqual(len(matches), 1, name)
        return matches[0].group(1) if matches[0].group(1) is not None else matches[0].group(2)

    def test_mod_update_preserves_join_password_custom_settings_and_stats(self):
        password, _ = host.configure_mod("Renamed synthetic host")
        self.assertEqual(password, "synthetic-existing-join-password")
        self.assertEqual(self.value("g_password"), password)
        self.assertEqual(self.value("sv_hostname"), "Renamed synthetic host")
        self.assertEqual(self.value("unrelated_custom_setting"), "preserve-me")
        self.assertEqual(self.stats.read_bytes(), self.original_stats)
        for relative in host.MOD_PAYLOADS[1:]:
            self.assertEqual((self.storage / relative).read_bytes(), (self.mod / relative).read_bytes())

    def test_generated_rcon_secret_is_private_stable_and_loopback_restricted(self):
        _, first = host.configure_mod(None)
        first_bytes = self.secret.read_bytes()
        self.assertRegex(first, r"\A[A-Za-z0-9_-]{32,128}\Z")
        self.assertEqual(stat.S_IMODE(self.secret.stat().st_mode), 0o600)
        self.assertEqual(self.value("rcon_password"), first)
        self.assertEqual(self.value("outlands_chat_enabled"), "1")
        _, second = host.configure_mod(None)
        self.assertEqual(second, first)
        self.assertEqual(self.secret.read_bytes(), first_bytes)
        text = self.cfg.read_text(encoding="utf-8")
        self.assertEqual(text.count("rconWhitelistAdd 127.0.0.1"), 1)
        self.assertIn('set outlands_chat_enabled "1"', text)
        self.assertIn('set rcon_password "' + first + '"', text)
        self.assertEqual(self.stats.read_bytes(), self.original_stats)

    def test_disabling_chat_clears_rcon_and_retains_secret_for_reenable(self):
        _, original = host.configure_mod(None)
        with patch.dict(os.environ, {"T6_CHAT_ENABLED": "0"}):
            password, control = host.configure_mod(None)
        self.assertEqual(password, "synthetic-existing-join-password")
        self.assertEqual(control, "")
        self.assertEqual(self.value("rcon_password"), "")
        self.assertEqual(self.value("outlands_chat_enabled"), "0")
        text = self.cfg.read_text(encoding="utf-8")
        self.assertIn('set outlands_chat_enabled "0"', text)
        self.assertIn('set rcon_password ""', text)
        self.assertNotIn("rconWhitelistAdd", text)
        self.assertEqual(self.secret.read_text(encoding="ascii"), original)
        self.assertEqual(self.stats.read_bytes(), self.original_stats)
        _, reenabled = host.configure_mod(None)
        self.assertEqual(reenabled, original)

    def test_preexisting_public_rcon_secret_is_rejected_without_cfg_change(self):
        self.secret.parent.mkdir()
        self.secret.write_text("synthetic-private-secret-with-enough-characters", encoding="ascii")
        self.secret.chmod(0o644)
        original_cfg = self.cfg.read_bytes()
        with self.assertRaisesRegex(host.StartupError, "private mode 600"):
            host.configure_mod(None)
        self.assertEqual(self.cfg.read_bytes(), original_cfg)
        self.assertEqual(stat.S_IMODE(self.secret.stat().st_mode), 0o644)
        self.assertEqual(self.stats.read_bytes(), self.original_stats)

    def test_redaction_removes_all_three_credentials_with_overlapping_values(self):
        runner = host.ProcessRunner("synthetic-key", "synthetic-key-join", "synthetic-key-join-control")
        line = "server=synthetic-key password=synthetic-key-join rcon=synthetic-key-join-control ready"
        self.assertEqual(runner.redact(line), "server=[REDACTED] password=[REDACTED] rcon=[REDACTED] ready")
        self.assertEqual(host.ProcessRunner("").redact("unchanged operational line"), "unchanged operational line")


if __name__ == "__main__":
    unittest.main()
