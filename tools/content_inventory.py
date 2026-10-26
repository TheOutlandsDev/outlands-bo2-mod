#!/usr/bin/env python3
"""Report installed BO2 map metadata and configured native-bot rotation coverage.

Example: python3 -B tools/content_inventory.py --game-dir /path/to/owned/BO2
This reads configuration text and file metadata only. It never reads/copies
game asset contents, downloads content, checks accounts or launches a game.
Reports contain relative asset names, not absolute diagnostic paths.
"""

import argparse
import json
from pathlib import Path
import re
import shlex
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE_FILES = ("t6mp.exe", "zone/all/code_pre_gfx_mp.ff", "zone/all/common_mp.ff")
PACKS = {
    "base": "Base game",
    "nuketown_bonus": "Nuketown 2025 bonus map",
    "revolution": "Revolution",
    "uprising": "Uprising",
    "vengeance": "Vengeance",
    "apocalypse": "Apocalypse",
}
MAPS = {
    "mp_la": ("Aftermath", "base"),
    "mp_dockside": ("Cargo", "base"),
    "mp_carrier": ("Carrier", "base"),
    "mp_drone": ("Drone", "base"),
    "mp_express": ("Express", "base"),
    "mp_hijacked": ("Hijacked", "base"),
    "mp_meltdown": ("Meltdown", "base"),
    "mp_overflow": ("Overflow", "base"),
    "mp_nightclub": ("Plaza", "base"),
    "mp_raid": ("Raid", "base"),
    "mp_slums": ("Slums", "base"),
    "mp_village": ("Standoff", "base"),
    "mp_turbine": ("Turbine", "base"),
    "mp_socotra": ("Yemen", "base"),
    "mp_nuketown_2020": ("Nuketown 2025", "nuketown_bonus"),
    "mp_downhill": ("Downhill", "revolution"),
    "mp_mirage": ("Mirage", "revolution"),
    "mp_hydro": ("Hydro", "revolution"),
    "mp_skate": ("Grind", "revolution"),
    "mp_concert": ("Encore", "uprising"),
    "mp_magma": ("Magma", "uprising"),
    "mp_vertigo": ("Vertigo", "uprising"),
    "mp_studio": ("Studio", "uprising"),
    "mp_uplink": ("Uplink", "vengeance"),
    "mp_bridge": ("Detour", "vengeance"),
    "mp_castaway": ("Cove", "vengeance"),
    "mp_paintball": ("Rush", "vengeance"),
    "mp_dig": ("Dig", "apocalypse"),
    "mp_frostbite": ("Frost", "apocalypse"),
    "mp_pod": ("Pod", "apocalypse"),
    "mp_takeoff": ("Takeoff", "apocalypse"),
}
SUPPORTED_MODES = {
    "tdm": "Team Deathmatch", "dm": "Free-for-All", "conf": "Kill Confirmed",
    "ctf": "Capture the Flag", "dem": "Demolition", "dom": "Domination",
    "koth": "Hardpoint", "hq": "Headquarters",
}
OTHER_MODES = {
    "sd": "Search and Destroy", "gun": "Gun Game", "oic": "One in the Chamber",
    "sas": "Sticks and Stones", "shrp": "Sharpshooter", "oneflag": "One Flag CTF",
}
AUXILIARY_SUFFIXES = ("_load", "_fx", "_patch", "_preload")
MAP_ID = re.compile(r"mp_[a-z0-9_]{1,64}\Z")
MODE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
MAX_CONFIG_BYTES = 256 * 1024
MAX_ROTATION_CHARS = 32768


class InventoryError(ValueError):
    """Fixed, nonsecret diagnostic suitable for JSON output."""


class InventoryParser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, json.dumps({"schema_version": 1, "error": "Invalid arguments. Run --help."}) + "\n")


def asset_metadata(game, relative):
    result = {"path": relative, "available": False, "status": "missing", "size_bytes": None}
    try:
        metadata = (game / relative).stat()
    except FileNotFoundError:
        return result
    except OSError:
        result["status"] = "unreadable"
        return result
    if not stat.S_ISREG(metadata.st_mode):
        result["status"] = "not_regular"
    elif metadata.st_size == 0:
        result.update(status="empty", size_bytes=0)
    else:
        result.update(available=True, status="present", size_bytes=metadata.st_size)
    return result


def strip_cfg_comment(line):
    quoted = False
    for index, character in enumerate(line):
        if character == '"':
            quoted = not quoted
        if not quoted and line[index:index + 2] == "//":
            return line[:index]
    return line


def configured_rotation(path):
    """Extract only rotation/mode assignments, never return unrelated CFG text."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
            raise InventoryError("Configuration must be a small readable text file.")
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise InventoryError("Configuration must be a small readable text file.") from None
    rotation = None
    mode = None
    assignments = 0
    pattern = re.compile(r"^\s*(?:set(?:a|s)?\s+)?(sv_maprotation|g_gametype|set_gametype)\b(.*)$", re.I)
    for line in text.splitlines():
        match = pattern.match(strip_cfg_comment(line))
        if not match:
            continue
        try:
            values = shlex.split(match[2], comments=False, posix=True)
        except ValueError:
            raise InventoryError("Rotation or default-mode assignment is malformed.") from None
        if not values:
            raise InventoryError("Rotation or default-mode assignment is empty.")
        if match[1].lower() == "sv_maprotation":
            rotation = " ".join(values)
            assignments += 1
        else:
            if len(values) != 1 or not MODE_ID.fullmatch(values[0]):
                raise InventoryError("Default gametype must be one safe mode identifier.")
            mode = values[0]
    if rotation is None:
        raise InventoryError("Configuration has no sv_maprotation assignment.")
    return rotation, mode, assignments


def parse_rotation(rotation, default_mode=None):
    if not isinstance(rotation, str) or not rotation.strip() or len(rotation) > MAX_ROTATION_CHARS or "\0" in rotation:
        raise InventoryError("Rotation must contain a bounded multiplayer map sequence.")
    if default_mode is not None and not MODE_ID.fullmatch(default_mode):
        raise InventoryError("Default gametype must be one safe mode identifier.")
    try:
        tokens = shlex.split(rotation, comments=False, posix=True)
    except ValueError:
        raise InventoryError("Rotation quoting is malformed.") from None
    if len(tokens) % 2:
        raise InventoryError("Each rotation directive requires exactly one value.")
    mode = default_mode
    mode_source = "default_mode" if mode else "unresolved"
    settings = None
    entries = []
    warnings = set()
    for index in range(0, len(tokens), 2):
        command, value = tokens[index:index + 2]
        if command == "gametype":
            if not MODE_ID.fullmatch(value):
                raise InventoryError("Rotation contains an invalid gametype identifier.")
            mode, mode_source, settings = value, "gametype_directive", None
        elif command == "execgts":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}\.cfg", value):
                raise InventoryError("Settings directives require a plain CFG filename.")
            settings = value
            candidate = value[:-4]
            for prefix in ("outlands_", "gamesettings_"):
                if candidate.startswith(prefix):
                    candidate = candidate[len(prefix):]
                    break
            if candidate in SUPPORTED_MODES or candidate in OTHER_MODES:
                mode, mode_source = candidate, "settings_filename_inference"
                warnings.add("settings_mode_inferred_from_filename_not_file_contents")
            else:
                mode, mode_source = None, "unresolved_settings"
                warnings.add("custom_settings_mode_not_resolved")
        elif command == "dsr":
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
                raise InventoryError("DSR directives require a safe identifier.")
            mode, mode_source, settings = None, "unresolved_dsr", None
            warnings.add("dsr_mode_not_resolved")
        elif command == "map":
            if not MAP_ID.fullmatch(value):
                raise InventoryError("Map directives require a safe multiplayer map identifier.")
            support = "supported" if mode in SUPPORTED_MODES else "unsupported" if mode in OTHER_MODES else "unknown"
            entries.append({"index": len(entries), "map_id": value, "mode_id": mode,
                            "mode_source": mode_source, "native_bot_support": support,
                            "settings_file": settings})
        else:
            raise InventoryError("Rotation contains an unsupported directive.")
    if not entries:
        raise InventoryError("Rotation contains no multiplayer map entries.")
    return entries, sorted(warnings)


def discover_fastfiles(game, prefix):
    directory = game / "zone/all"
    if not directory.exists():
        return []
    try:
        paths = sorted(directory.glob(prefix + "*.ff"))
        return [asset_metadata(game, "zone/all/" + path.name) for path in paths
                if re.fullmatch(prefix + r"[a-z0-9_]+\.ff", path.name)]
    except OSError:
        raise InventoryError("The shared zone directory cannot be inventoried.") from None


def build_inventory(game, rotation, default_mode=None, assignment_count=1):
    game = Path(game)
    if not game.is_dir():
        raise InventoryError("Game directory must be an existing readable directory.")
    entries, warnings = parse_rotation(rotation, default_mode)
    core = [asset_metadata(game, name) for name in CORE_FILES]
    maps = [{"map_id": key, "name": name, "pack": pack,
             "asset": asset_metadata(game, "zone/all/" + key + ".ff")}
            for key, (name, pack) in sorted(MAPS.items())]
    lookup = {row["map_id"]: row for row in maps}
    packs = []
    for key, label in PACKS.items():
        expected = [row["map_id"] for row in maps if row["pack"] == key]
        available = [name for name in expected if lookup[name]["asset"]["available"]]
        missing = sorted(set(expected) - set(available))
        packs.append({"pack": key, "name": label, "expected_count": len(expected),
                      "available_count": len(available), "available_maps": available,
                      "missing_maps": missing, "main_fastfile_coverage_complete": not missing})
    for entry in entries:
        entry["catalogued_map"] = entry["map_id"] in lookup
        entry["asset"] = lookup[entry["map_id"]]["asset"] if entry["catalogued_map"] else asset_metadata(game, "zone/all/" + entry["map_id"] + ".ff")
    missing_maps = sorted({entry["map_id"] for entry in entries if not entry["asset"]["available"]})
    unknown_maps = sorted({entry["map_id"] for entry in entries if not entry["catalogued_map"]})
    unsupported = sorted({entry["mode_id"] for entry in entries if entry["native_bot_support"] == "unsupported"})
    unresolved = [entry["index"] for entry in entries if entry["native_bot_support"] == "unknown"]
    mp_files = discover_fastfiles(game, "mp_")
    unknown_files = [row for row in mp_files if Path(row["path"]).stem not in MAPS
                     and not Path(row["path"]).stem.endswith(AUXILIARY_SUFFIXES)]
    zm_files = discover_fastfiles(game, "zm_")
    zm_candidates = [row for row in zm_files if not Path(row["path"]).stem.endswith(AUXILIARY_SUFFIXES)]
    if assignment_count > 1:
        warnings.append("multiple_rotation_assignments_last_used")
    inventory_ready = all(row["available"] for row in core) and not (missing_maps or unknown_maps or unsupported or unresolved)
    return {
        "schema_version": 1,
        "scope": {"asset_contents_read": False, "game_launched": False, "network_used": False,
                  "ownership_verified": False, "runtime_loadability_verified": False,
                  "full_install_integrity_verified": False,
                  "coverage_basis": "Nonempty main fastfile presence only; supporting/localized assets are not verified."},
        "multiplayer": {"core_files": core, "maps": maps, "packs": packs,
                        "catalogued_map_count": len(maps),
                        "available_catalogued_map_count": sum(row["asset"]["available"] for row in maps),
                        "all_catalogued_main_fastfiles_present": all(row["asset"]["available"] for row in maps),
                        "unknown_main_fastfiles": unknown_files},
        "native_bot_modes": {"supported": SUPPORTED_MODES, "known_unsupported": OTHER_MODES,
                             "other_modes": "unknown; no native-bot compatibility claim"},
        "rotation": {"entries": entries, "missing_maps": missing_maps,
                     "uncatalogued_maps": unknown_maps, "unsupported_modes": unsupported,
                     "unresolved_mode_entries": unresolved, "warnings": sorted(warnings),
                     "inventory_ready": inventory_ready},
        "zombies": {"scope": "discovery_only", "catalog_complete": False,
                    "mode_implementation": False, "client_loadability_verified": False,
                    "executable": asset_metadata(game, "t6zm.exe"),
                    "discovered_fastfiles": zm_files, "discovered_fastfile_count": len(zm_files),
                    "main_candidates": zm_candidates, "main_candidate_count": len(zm_candidates)},
        "catalog_sources": [
            "https://github.com/xerxes-at/T6ServerConfigs/blob/master/localappdata/Plutonium/storage/t6/dedicated.cfg",
            "https://github.com/plutoniummod/t6-scripts/blob/main/MP/Core/maps/mp/bots/_bot.gsc",
        ],
    }


def main(argv=None):
    parser = InventoryParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True, help="Owned game directory; no assets are copied or read.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--config", type=Path, help="CFG containing sv_maprotation; default is the source host CFG.")
    source.add_argument("--rotation", help="Explicit rotation text instead of a CFG; never evaluated or executed.")
    parser.add_argument("--default-mode", help="Initial mode for a map-only rotation; otherwise unknown unless configured.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 for missing core/rotation maps or unknown/unsupported rotation modes/maps.")
    options = parser.parse_args(argv)
    try:
        rotation, mode, count = options.rotation, None, 1
        if rotation is None:
            rotation, mode, count = configured_rotation(options.config or ROOT / "storage/t6/outlands_t6.cfg")
        report = build_inventory(options.game_dir, rotation, options.default_mode or mode, count)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if options.strict and not report["rotation"]["inventory_ready"] else 0
    except (InventoryError, OSError):
        error = sys.exc_info()[1]
        message = str(error) if isinstance(error, InventoryError) else "Content metadata could not be inspected."
        print(json.dumps({"schema_version": 1, "error": message}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
