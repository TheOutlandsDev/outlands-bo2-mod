"""Content inventory regression checks with synthetic assets; no game/network needed."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("outlands_content_inventory", SOURCE / "tools/content_inventory.py")
INVENTORY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INVENTORY)


class ContentInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="outlands-content-inventory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / "Owned Game Fixture With Spaces"
        self.game.mkdir()

    def asset(self, name, data=b"\0synthetic non-game fixture"):
        path = self.game / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def core(self):
        for name in INVENTORY.CORE_FILES:
            self.asset(name)

    def map(self, name):
        return self.asset("zone/all/" + name + ".ff")

    def snapshot(self):
        return {path.relative_to(self.root).as_posix():
                (path.stat().st_mode, path.stat().st_mtime_ns,
                 path.read_bytes() if path.is_file() else None)
                for path in self.root.rglob("*")}

    def run_main(self, arguments, expected=0):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            result = INVENTORY.main(["--game-dir", str(self.game), *arguments])
        self.assertEqual(result, expected, error.getvalue())
        return json.loads(output.getvalue()) if output.getvalue() else json.loads(error.getvalue())

    def test_catalog_distinguishes_empty_full_and_optional_pack_coverage(self):
        empty = INVENTORY.build_inventory(self.game, "gametype tdm map mp_raid")
        self.assertEqual(empty["multiplayer"]["catalogued_map_count"], 31)
        self.assertEqual(empty["multiplayer"]["available_catalogued_map_count"], 0)
        self.assertFalse(empty["rotation"]["inventory_ready"])
        self.assertEqual({row["pack"]: row["expected_count"] for row in empty["multiplayer"]["packs"]},
                         {"base": 14, "nuketown_bonus": 1, "revolution": 4,
                          "uprising": 4, "vengeance": 4, "apocalypse": 4})
        self.core()
        for name in INVENTORY.MAPS:
            self.map(name)
        complete = INVENTORY.build_inventory(self.game, "gametype tdm map mp_raid")
        self.assertTrue(complete["multiplayer"]["all_catalogued_main_fastfiles_present"])
        self.assertTrue(all(row["main_fastfile_coverage_complete"] for row in complete["multiplayer"]["packs"]))
        self.assertTrue(complete["rotation"]["inventory_ready"])
        self.assertFalse(complete["scope"]["ownership_verified"])
        self.assertFalse(complete["scope"]["full_install_integrity_verified"])
        self.assertFalse(complete["scope"]["runtime_loadability_verified"])

    def test_missing_dlc_rotation_map_and_partial_pack_are_explicit(self):
        self.core()
        for name in ("mp_raid", "mp_downhill", "mp_mirage", "mp_skate"):
            self.map(name)
        report = INVENTORY.build_inventory(self.game, "gametype dom map mp_raid map mp_hydro")
        self.assertEqual(report["rotation"]["missing_maps"], ["mp_hydro"])
        pack = next(row for row in report["multiplayer"]["packs"] if row["pack"] == "revolution")
        self.assertEqual(pack["available_count"], 3)
        self.assertEqual(pack["missing_maps"], ["mp_hydro"])
        self.assertFalse(pack["main_fastfile_coverage_complete"])
        self.assertFalse(report["rotation"]["inventory_ready"])
        # Missing unselected optional DLC does not make a covered rotation fail.
        self.assertTrue(INVENTORY.build_inventory(self.game, "gametype dom map mp_raid")["rotation"]["inventory_ready"])

    def test_rotation_mode_inheritance_and_bot_support_boundaries(self):
        entries, warnings = INVENTORY.parse_rotation(
            "gametype dom map mp_raid map mp_hijacked execgts outlands_conf.cfg map mp_slums "
            "gametype sd map mp_express gametype custommode map mp_drone")
        self.assertEqual([entry["mode_id"] for entry in entries], ["dom", "dom", "conf", "sd", "custommode"])
        self.assertEqual([entry["native_bot_support"] for entry in entries],
                         ["supported", "supported", "supported", "unsupported", "unknown"])
        self.assertIn("settings_mode_inferred_from_filename_not_file_contents", warnings)
        self.assertEqual(entries[2]["mode_source"], "settings_filename_inference")
        self.assertEqual(INVENTORY.parse_rotation("map mp_raid", "tdm")[0][0]["mode_id"], "tdm")
        self.assertEqual(INVENTORY.parse_rotation("map mp_raid")[0][0]["native_bot_support"], "unknown")
        custom, warnings = INVENTORY.parse_rotation("gametype dom execgts custom.cfg map mp_raid")
        self.assertIsNone(custom[0]["mode_id"])
        self.assertIn("custom_settings_mode_not_resolved", warnings)
        dsr, warnings = INVENTORY.parse_rotation("dsr CUSTOM_default map mp_raid")
        self.assertEqual(dsr[0]["mode_source"], "unresolved_dsr")
        self.assertIn("dsr_mode_not_resolved", warnings)

    def test_unknown_main_fastfiles_and_zombies_are_separate_from_complete_catalog(self):
        self.core()
        for name in ("mp_raid", "mp_custom", "mp_raid_load", "mp_raid_fx", "mp_raid_patch",
                     "zm_transit", "zm_transit_load", "zm_example", "campaign_example"):
            self.map(name)
        report = INVENTORY.build_inventory(self.game, "gametype tdm map mp_custom")
        self.assertEqual([row["path"] for row in report["multiplayer"]["unknown_main_fastfiles"]],
                         ["zone/all/mp_custom.ff"])
        self.assertEqual(report["rotation"]["uncatalogued_maps"], ["mp_custom"])
        self.assertFalse(report["rotation"]["inventory_ready"])
        zombies = report["zombies"]
        self.assertEqual(zombies["discovered_fastfile_count"], 3)
        self.assertEqual(zombies["main_candidate_count"], 2)
        self.assertFalse(zombies["catalog_complete"])
        self.assertFalse(zombies["mode_implementation"])
        self.assertFalse(zombies["client_loadability_verified"])

    def test_config_uses_last_assignment_and_never_reports_secrets_or_absolute_paths(self):
        self.core()
        self.map("mp_raid")
        config = self.root / "Private Config With Spaces.cfg"
        secret = "DO_NOT_ECHO_PRIVATE_VALUE"
        config.write_text('g_password "' + secret + '"\n'
                          'rcon_password "' + secret + '"\n'
                          '// sv_maprotation "gametype dm map mp_hydro"\n'
                          'sv_maprotation "gametype sd map mp_drone"\n'
                          'set g_gametype "dom"\n'
                          'seta sv_maprotation "map mp_raid" // selected rotation\n')
        before = self.snapshot()
        report = self.run_main(["--config", str(config), "--strict"])
        self.assertEqual(report["rotation"]["entries"][0]["mode_id"], "dom")
        self.assertIn("multiple_rotation_assignments_last_used", report["rotation"]["warnings"])
        rendered = json.dumps(report)
        self.assertNotIn(secret, rendered)
        self.assertNotIn(str(self.root), rendered)
        self.assertEqual(self.snapshot(), before)

    def test_metadata_only_does_not_open_assets_and_does_not_accept_empty_or_directory_assets(self):
        self.core()
        self.map("mp_raid")
        self.asset("zone/all/mp_hydro.ff", b"")
        (self.game / "zone/all/mp_mirage.ff").mkdir()
        before = self.snapshot()
        with patch.object(Path, "open", side_effect=AssertionError("Inventory tried to open asset contents")):
            report = INVENTORY.build_inventory(self.game, "gametype tdm map mp_raid")
        maps = {row["map_id"]: row["asset"] for row in report["multiplayer"]["maps"]}
        self.assertEqual(maps["mp_hydro"]["status"], "empty")
        self.assertEqual(maps["mp_mirage"]["status"], "not_regular")
        self.assertFalse(maps["mp_hydro"]["available"])
        self.assertFalse(maps["mp_mirage"]["available"])
        self.assertEqual(self.snapshot(), before)

    def test_cli_missing_content_strict_exit_and_repeatable_report_without_writes(self):
        arguments = ["--rotation", "gametype tdm map mp_raid"]
        before = self.snapshot()
        normal = self.run_main(arguments)
        strict = self.run_main([*arguments, "--strict"], expected=1)
        self.assertEqual(normal, strict)
        self.assertEqual(self.run_main(arguments), normal)
        self.assertEqual(self.snapshot(), before)
        self.core()
        self.map("mp_raid")
        self.assertTrue(self.run_main([*arguments, "--strict"])["rotation"]["inventory_ready"])

    def test_malformed_or_traversing_inputs_fail_without_echoing_values_or_writes(self):
        invalid = ("gametype tdm map ../../private", "gametype tdm map zm_transit",
                   "gametype tdm map", "execgts ../../private.cfg map mp_raid",
                   "gametype tdm map mp_raid quit PRIVATE_SENTINEL", 'map "unterminated',
                   "gametype tdm", "", "map mp_raid\0PRIVATE_SENTINEL")
        before = self.snapshot()
        for value in invalid:
            with self.subTest(rotation=value[:30]):
                report = self.run_main(["--rotation", value], expected=2)
                self.assertNotIn("PRIVATE_SENTINEL", json.dumps(report))
                self.assertNotIn(str(self.root), json.dumps(report))
        missing = self.run_main(["--config", str(self.root / "PRIVATE_SENTINEL.cfg")], expected=2)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(missing))
        error = io.StringIO()
        with redirect_stderr(error), self.assertRaises(SystemExit) as rejected:
            INVENTORY.main(["--unsupported", "PRIVATE_SENTINEL"])
        self.assertEqual(rejected.exception.code, 2)
        self.assertNotIn("PRIVATE_SENTINEL", error.getvalue())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
