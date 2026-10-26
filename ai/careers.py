"""Private, bounded careers for allowlisted fictional native bots only.

The model cannot mutate this ledger. Only validated scoreboard samples can earn
career XP; neither chat text nor human identifiers belong in this file.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

MARKER = "OUTLANDS_BOT_V1|"
ROLES = ("rusher", "assault", "objective", "support", "marksman")
KINDS = frozenset(("hello", "snapshot", "depart", "match_end"))
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
MAX_SESSIONS = 128
MAX_RETIRED = 512
MAX_TOTAL = 1_000_000_000
XP_PER_LEVEL = 5000
MAX_XP = 11 * 55 * XP_PER_LEVEL - 1
MAX_FILE_BYTES = 524288


class CareerError(ValueError):
    pass


def integer(value, low=0, high=MAX_TOTAL):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


@dataclass(frozen=True)
class CareerEvent:
    session: str
    request_id: str
    sequence: int
    kind: str
    slot: int
    alias: str
    kills: int
    deaths: int
    score: int
    map_name: str
    gametype: str

    @classmethod
    def parse(cls, line: str, roster):
        if len(line) > 1024 or not line.startswith(MARKER):
            return None
        fields = line.rstrip("\r\n")[len(MARKER):].split("|")
        if len(fields) != 10:
            return None
        session, request, kind, slot, alias, kills, deaths, score, map_name, mode = fields
        if not TOKEN.fullmatch(session) or not IDENTIFIER.fullmatch(request) or not request.startswith(session + "_"):
            return None
        sequence = request[len(session) + 1:]
        if not re.fullmatch(r"[1-9][0-9]{0,9}", sequence) or int(sequence) > 2147483647:
            return None
        if kind not in KINDS or alias not in roster or not re.fullmatch(r"[0-9]{1,2}", slot) or int(slot) >= 18:
            return None
        if not all(re.fullmatch(r"[0-9]{1,6}", value) for value in (kills, deaths)):
            return None
        if not re.fullmatch(r"-?[0-9]{1,8}", score) or not -10_000_000 <= int(score) <= 10_000_000:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", map_name) or not re.fullmatch(r"[A-Za-z0-9_]{1,16}", mode):
            return None
        return cls(session, request, int(sequence), kind, int(slot), alias,
                   int(kills), int(deaths), int(score), map_name, mode)


def cosmetic_profile(xp, role):
    # Fictional display levels; these never touch BO2 player stats or unlocks.
    step = min(MAX_XP, xp) // XP_PER_LEVEL
    return {"level": step % 55 + 1, "prestige": min(10, step // 55), "role": role}


class CareerStore:
    """One process owns an atomic mode-600 JSON ledger in a private directory.

    128 connection records plus 512 retired hashes bound replay protection and
    disk growth. The console follower deliberately never replays an old log.
    """
    def __init__(self, path: Path, roster, roles=None):
        self.path = Path(path)
        self.roster = frozenset(roster)
        if not self.roster or len(self.roster) > 64 or any(not re.fullmatch(r"[A-Za-z0-9 ._~-]{1,24}", x) or x != x.strip() for x in self.roster):
            raise CareerError("Invalid fictional bot roster")
        self.roles = dict(roles or {})
        if any(name not in self.roster or role not in ROLES for name, role in self.roles.items()):
            raise CareerError("Invalid fictional bot role")
        self.state = {"schema_version": 1, "careers": {}, "sessions": {}, "retired": [], "social": {}}
        # Persisted counters are historical. Only a fresh sample observed by
        # this process may be described to a model as an own-match scoreboard.
        self.fresh_samples: dict[str, float] = {}
        self._private_parent()
        self._load()

    def _private_parent(self):
        # Resolve no links, including parent components, before either read or
        # write. The deployment gives this directory exclusively to UID 10001.
        parent = self.path.absolute().parent
        for component in (parent, *parent.parents):
            if component.is_symlink():
                raise CareerError("Career state parent cannot contain symlinks")
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CareerError("Career state directory must be owned and private (mode 700)")

    def _load(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > MAX_FILE_BYTES:
                raise CareerError("Career state must be an owned private regular file")
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = None
                data = json.load(stream)
        finally:
            if fd is not None:
                os.close(fd)
        self.state = self._validate(data)

    def _validate(self, data):
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1 or set(data) - {"schema_version", "careers", "sessions", "retired", "social"}:
            raise CareerError("Unsupported career state schema")
        # Additive schema-1 migration: older aggregate-only files may omit the
        # bounded transport/social caches; earned careers remain unchanged.
        for key, default in (("sessions", {}), ("retired", []), ("social", {})):
            data.setdefault(key, default)
        careers, sessions, retired, social = (data.get(key) for key in ("careers", "sessions", "retired", "social"))
        if not isinstance(careers, dict) or len(careers) > len(self.roster) or any(name not in self.roster for name in careers):
            raise CareerError("Career state contains an unknown bot")
        career_keys = {"xp", "earned_xp", "kills", "deaths", "score", "observed_rounds", "role"}
        for item in careers.values():
            if not isinstance(item, dict) or set(item) != career_keys or item["role"] not in ROLES or not integer(item["xp"], 0, MAX_XP) or any(not integer(item[key]) for key in career_keys - {"role", "xp"}):
                raise CareerError("Invalid career aggregate")
        if not isinstance(sessions, dict) or len(sessions) > MAX_SESSIONS:
            raise CareerError("Invalid career sessions")
        session_keys = {"alias", "slot", "sequence", "hello_sequence", "kills", "deaths", "score", "map", "mode", "closed"}
        for token, item in sessions.items():
            if not TOKEN.fullmatch(token) or not isinstance(item, dict) or set(item) != session_keys:
                raise CareerError("Invalid career session")
            if item["alias"] not in careers or not integer(item["slot"], 0, 17) or not integer(item["sequence"], 1, 2147483647) or not integer(item["hello_sequence"], 0, item["sequence"]) or not integer(item["kills"], 0, 999999) or not integer(item["deaths"], 0, 999999) or not integer(item["score"], -10_000_000, 10_000_000) or not isinstance(item["closed"], bool) or not isinstance(item["map"], str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", item["map"]) or not isinstance(item["mode"], str) or not re.fullmatch(r"[A-Za-z0-9_]{1,16}", item["mode"]):
                raise CareerError("Invalid career session fields")
        if not isinstance(retired, list) or len(retired) > MAX_RETIRED or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in retired) or len(set(retired)) != len(retired):
            raise CareerError("Invalid retired-session cache")
        if not isinstance(social, dict) or len(social) > len(self.roster):
            raise CareerError("Invalid bot social memory")
        for name, peers in social.items():
            if name not in self.roster or not isinstance(peers, dict) or len(peers) > len(self.roster) - 1 or any(peer not in self.roster or peer == name or not integer(count, 1, 1000000) for peer, count in peers.items()):
                raise CareerError("Invalid bot social peers")
        return data

    def _save(self):
        self._private_parent()
        # Refuse a replacement of an existing state file by a symlink, public
        # file or directory even though replace() itself would unlink a link.
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise CareerError("Refusing unsafe career state destination")
        raw = (json.dumps(self.state, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        if len(raw) > MAX_FILE_BYTES:
            raise CareerError("Career state exceeds bounded size")
        fd, temporary = tempfile.mkstemp(prefix=".careers-", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _career(self, alias):
        if alias not in self.roster:
            raise CareerError("Unknown fictional bot")
        careers = self.state["careers"]
        if alias not in careers:
            seed = hashlib.sha256(alias.encode("ascii")).digest()
            level = 1 + seed[0] % 55
            prestige_weights = (0,) * 12 + (1,) * 5 + (2,) * 3 + (3,) * 3 + (4,) * 2 + (5,) * 2 + (6, 7, 8, 9, 10)
            prestige = prestige_weights[seed[1] % len(prestige_weights)]
            careers[alias] = {"xp": (prestige * 55 + level - 1) * XP_PER_LEVEL,
                              "earned_xp": 0, "kills": 0, "deaths": 0, "score": 0,
                              "observed_rounds": 0, "role": self.roles.get(alias, ROLES[seed[2] % len(ROLES)])}
        return careers[alias]

    def profile(self, alias):
        item = self._career(alias)
        return cosmetic_profile(item["xp"], item["role"])

    @staticmethod
    def _session_hash(session):
        return hashlib.sha256(session.encode("ascii")).hexdigest()

    def _trim(self):
        while len(self.state["sessions"]) > MAX_SESSIONS:
            # JSON key order is not a clock. Closed entries are always retired
            # first; otherwise evict the first retained connection deterministically.
            sessions = self.state["sessions"]
            token = next((key for key, value in sessions.items() if value["closed"]), next(iter(sessions)))
            del sessions[token]
            self.fresh_samples.pop(token, None)
            digest = self._session_hash(token)
            self.state["retired"].append(digest)
            self.state["retired"] = self.state["retired"][-MAX_RETIRED:]

    def apply(self, event: CareerEvent):
        """Commit before returning a hello restore profile. Duplicate hello is safe."""
        if event.alias not in self.roster or self._session_hash(event.session) in self.state["retired"]:
            return None
        sessions = self.state["sessions"]
        sample = sessions.get(event.session)
        if sample is not None:
            if (sample["alias"], sample["slot"], sample["map"], sample["mode"]) != (event.alias, event.slot, event.map_name, event.gametype):
                return None
            if sample["closed"]:
                return None
            if event.kind == "hello":
                if sample["hello_sequence"] == 0 and event.sequence <= sample["sequence"]:
                    # The EOF follower may first see a snapshot and only later
                    # the emitter's identical initial hello retry.
                    sample["hello_sequence"] = event.sequence
                    self._save()
                elif event.sequence != sample["hello_sequence"]:
                    return None
                return self.profile(event.alias)
            if event.sequence <= sample["sequence"]:
                return None
        item = self._career(event.alias)
        if sample is None:
            sample = {"alias": event.alias, "slot": event.slot, "sequence": event.sequence,
                      "hello_sequence": event.sequence if event.kind == "hello" else 0,
                      "kills": event.kills, "deaths": event.deaths, "score": event.score,
                      "map": event.map_name, "mode": event.gametype, "closed": False}
            sessions[event.session] = sample
        else:
            delta = (event.kills - sample["kills"], event.deaths - sample["deaths"], event.score - sample["score"])
            if all(0 <= value <= limit for value, limit in zip(delta, (128, 128, 100000))):
                gain = delta[0] * 100 + delta[2]
                for key, amount in (("kills", delta[0]), ("deaths", delta[1]), ("score", delta[2]), ("earned_xp", gain)):
                    item[key] = min(MAX_TOTAL, item[key] + amount)
                item["xp"] = min(MAX_XP, item["xp"] + gain)
            # Reset/outlier samples become the new baseline without awards.
            sample.update(sequence=event.sequence, kills=event.kills, deaths=event.deaths, score=event.score)
        if event.kind in ("depart", "match_end"):
            sample["closed"] = True
            if event.kind == "match_end":
                item["observed_rounds"] = min(MAX_TOTAL, item["observed_rounds"] + 1)
        if event.kind == "snapshot":
            self.fresh_samples[event.session] = time.monotonic()
        elif event.kind in ("depart", "match_end"):
            self.fresh_samples.pop(event.session, None)
        self._trim()
        self._save()
        return self.profile(event.alias) if event.kind == "hello" else None

    def record_exchange(self, first, second):
        """Structured bot-only memory. Never store generated or human text."""
        if first not in self.roster or second not in self.roster or first == second:
            return False
        for left, right in ((first, second), (second, first)):
            peers = self.state["social"].setdefault(left, {})
            peers[right] = min(1000000, peers.get(right, 0) + 1)
        self._save()
        return True

    def context(self, alias, peer="", map_name="", gametype=""):
        if alias not in self.roster:
            return {}
        item = self.state["careers"].get(alias)
        if item is None:
            return {}
        result = {"fictional_bot_career": self.profile(alias),
                  "earned_career_xp": item["earned_xp"], "career_kills": item["kills"],
                  "career_deaths": item["deaths"], "observed_rounds": item["observed_rounds"]}
        now = time.monotonic()
        matching = [sample for token, sample in self.state["sessions"].items()
                    if sample["alias"] == alias and not sample["closed"] and (sample["map"], sample["mode"]) == (map_name, gametype)
                    and 0 <= now - self.fresh_samples.get(token, float("-inf")) <= 60]
        if len(matching) == 1:
            sample = matching[0]
            result["own_public_scoreboard"] = {key: sample[key] for key in ("kills", "deaths", "score")}
        if peer in self.roster and peer != alias:
            result["previous_bot_exchanges"] = self.state["social"].get(alias, {}).get(peer, 0)
        return result
