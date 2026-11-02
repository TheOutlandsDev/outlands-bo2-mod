"""Replayable tactical plans for the observed native fictional-bot roster.

The seed controls this planner, never the engine RNG, human stats or targeting.
Profiles are public fictional characters; match observations stay private.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ._~-:|"
MODULUS = 65521
ROLES = ("rusher", "assault", "objective", "support", "marksman")
TIERS = ("developing", "regular", "experienced", "standout")
SPECIALTIES = ("none", "shotcaller", "flanker")
try:
    from .bot_settings import selected_preset, TIERS as COMBAT_TIERS
except ImportError:
    from bot_settings import selected_preset, TIERS as COMBAT_TIERS


def combat_tuning(tier, preset="mixed"):
    """Validated native combat settings, independent of cosmetic rank."""
    if not isinstance(tier, str) or tier not in COMBAT_TIERS:
        raise ValueError("Unknown combat tier")
    return dict(selected_preset(preset)['combat'][tier])


def aim_blend(elapsed_ms, smoothing_ms):
    if type(elapsed_ms) is not int or not 0 <= elapsed_ms <= 1000 or type(smoothing_ms) is not int or not 100 <= smoothing_ms <= 1000:
        raise ValueError("Invalid aim timing")
    return max(0.1, min(0.75, elapsed_ms / smoothing_ms))
TEAMS = ("allies", "axis")
MAP = re.compile(r"mp_[a-z0-9_]{1,40}\Z")
MODES = ("dom", "ctf", "koth", "hq", "dem", "tdm", "conf", "dm")


def number(value, low, high):
    return type(value) is int and low <= value <= high


def hash_text(text, seed=1):
    if not isinstance(text, str) or len(text) > 256 or not number(seed, 0, MODULUS - 1):
        raise ValueError("Invalid planner hash input")
    value = seed
    for char in text:
        if char not in ALPHABET:
            raise ValueError("Invalid planner token")
        value = (value * 131 + ALPHABET.index(char) + 1) % MODULUS
    return value


def match_seed(seed, map_name, mode):
    if not number(seed, 1, MODULUS - 1) or not isinstance(map_name, str) or not MAP.fullmatch(map_name) or mode not in MODES:
        raise ValueError("Invalid match plan context")
    return hash_text(map_name + "|" + mode, seed)


def load_profiles(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name("rival_profiles.json")
    if path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError("Invalid rival catalog file")
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {"schema_version", "profiles"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported rival catalog")
    profiles = data["profiles"]
    if not isinstance(profiles, dict) or not 1 <= len(profiles) <= 64:
        raise ValueError("Invalid rival roster")
    keys = {"role", "specialty", "tier", "aggression", "teamwork", "route_preference", "favorite_primaries"}
    for alias, row in profiles.items():
        if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9 ._~-]{1,24}", alias) or alias != alias.strip() or not isinstance(row, dict) or set(row) != keys:
            raise ValueError("Invalid rival profile")
        if row["role"] not in ROLES or row["specialty"] not in SPECIALTIES or row["tier"] not in TIERS or row["route_preference"] not in ("direct", "balanced", "wide"):
            raise ValueError("Invalid rival traits")
        if (row["tier"] == "standout") != (row["specialty"] != "none") or not number(row["aggression"], 20, 80) or not number(row["teamwork"], 20, 85):
            raise ValueError("Invalid rival trait bounds")
        favorites = row["favorite_primaries"]
        if not isinstance(favorites, list) or not 1 <= len(favorites) <= 3 or any(not isinstance(x, str) or not re.fullmatch(r"[a-z0-9_]{1,32}_mp", x) for x in favorites) or len(set(favorites)) != len(favorites):
            raise ValueError("Invalid favorite weapon references")
    return profiles


def tendency(alias, profile, seed):
    """Mirror native arithmetic exactly; fixed aliases retain fixed preferences."""
    value = hash_text(alias, seed)
    spread = 9 if profile["tier"] == "standout" else 13 if profile["tier"] == "experienced" else 21
    aggression = max(10, min(90, profile["aggression"] + value % spread - spread // 2))
    teamwork = max(10, min(90, profile["teamwork"] + (value // 21) % spread - spread // 2))
    commit = {"developing":12, "regular":14, "experienced":16, "standout":18}[profile["tier"]]
    route = {"direct":0, "balanced":1, "wide":2}[profile["route_preference"]] if value % 100 < 70 else (value // 441) % 3
    return {"aggression": aggression, "teamwork": teamwork,
            "route": route, "commit_seconds": commit + value % (3 if commit == 18 else 5),
            "priority": hash_text(alias + ":priority", seed)}


def plan(roster, seed, map_name, mode, profiles=None):
    """Plan only explicitly observed allowlisted bots, never infer humans.

Native names/teams remain engine-owned. An unknown alias, duplicate name/slot,
or malformed observation is rejected rather than exported as a fictional bot.
"""
    profiles = load_profiles() if profiles is None else profiles
    derived = match_seed(seed, map_name, mode)
    if not isinstance(roster, list) or not 1 <= len(roster) <= 18:
        raise ValueError("Invalid observed roster")
    seen_names, seen_slots, result = set(), set(), []
    for bot in roster:
        if not isinstance(bot, dict) or set(bot) != {"alias", "slot", "team"} or not isinstance(bot["alias"], str) or bot["alias"] not in profiles or bot["alias"] in seen_names or not number(bot["slot"], 0, 17) or bot["slot"] in seen_slots or bot["team"] not in TEAMS:
            raise ValueError("Invalid observed fictional bot")
        seen_names.add(bot["alias"]); seen_slots.add(bot["slot"])
        profile = profiles[bot["alias"]]
        result.append({**bot, "role": profile["role"], "specialty": profile["specialty"],
                       "tier": profile["tier"], **tendency(bot["alias"], profile, derived), "standout_active": False})
    for team in TEAMS:
        eligible = [row for row in result if row["team"] == team and row["specialty"] != "none"]
        if eligible:
            min(eligible, key=lambda x: (x["priority"], x["slot"]))["standout_active"] = True
    return {"schema_version": 1, "seed": seed, "derived_seed": derived,
            "map": map_name, "mode": mode, "bots": sorted(result, key=lambda x: x["slot"])}


def duty_score(row, duty, incumbent=False, committed=False):
    if duty not in ("attack", "defend"):
        raise ValueError("Unknown squad duty")
    if duty == "attack":
        value = row["aggression"] + {"objective": 70, "rusher": 55, "assault": 30, "support": 10, "marksman": 0}[row["role"]]
        if row["standout_active"]:
            value += 30
    else:
        value = row["teamwork"] + {"objective": 20, "rusher": 0, "assault": 25, "support": 65, "marksman": 55}[row["role"]]
    return value + (12 if incumbent else 0) + (1000 if incumbent and committed else -1000 if committed else 0)


def generated_catalog(profiles):
    """Data-only native catalog. Checked against JSON in portable tests."""
    lines = ["// Generated by ai/rivals.py --emit-catalog; fictional profiles only.",
             "lookup( alias )", "{", "    switch ( alias )", "    {"]
    for alias, row in profiles.items():
        fields = [alias, row["role"], row["specialty"], row["tier"], str(row["aggression"]),
                  str(row["teamwork"]), row["route_preference"], ",".join(row["favorite_primaries"])]
        lines.append(f'        case "{alias}": return strtok( "' + "|".join(fields) + '", "|" );')
    lines += ["    }", "    return undefined;", "}", ""]
    return "\n".join(lines)


def position_cost(travel_sq, objective_sq, route, nearby, danger_seconds):
    """Native experiment's local cost; no enemy/human identifiers or positions."""
    if not number(travel_sq, 0, 1000000000) or not number(objective_sq, 0, 1000000000) or not number(route, 0, 2) or not number(nearby, 0, 17) or not number(danger_seconds, 0, 45):
        raise ValueError("Invalid local position observation")
    bias = objective_sq // 32768 if route == 0 else objective_sq // 65536
    if route == 2: bias = -bias
    return travel_sq // 16384 + nearby * 400 + danger_seconds * 10 + bias


def favorite_weight(profile, weapon, duplicates=0):
    if not isinstance(weapon, str) or not re.fullmatch(r'[a-z0-9_+]{0,128}', weapon) or not number(duplicates, 0, 17):
        raise ValueError("Invalid native candidate observation")
    base = weapon.split('+', 1)[0]
    weight = 4
    if base in profile['favorite_primaries']:
        weight += 12 - 4 * profile['favorite_primaries'].index(base)
    for _ in range(duplicates): weight = max(1, weight // 2)
    return weight


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-catalog", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--map", default="mp_raid")
    parser.add_argument("--mode", default="dom")
    args = parser.parse_args()
    profiles = load_profiles()
    if args.emit_catalog:
        print(generated_catalog(profiles), end="")
    else:
        aliases = sorted(profiles, key=lambda a: hash_text(a, match_seed(args.seed, args.map, args.mode)))[:16]
        roster = [{"alias": alias, "slot": slot, "team": TEAMS[slot % 2]} for slot, alias in enumerate(aliases)]
        print(json.dumps({"scope": "synthetic_observed_roster_preview", "plan": plan(roster, args.seed, args.map, args.mode, profiles)}, indent=2))


if __name__ == "__main__":
    main()
