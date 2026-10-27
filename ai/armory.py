"""Outlands single-slot Armory backend. No native profile or inventory writes.

The caller supplies a trusted, fresh native catalog/unlock observation separately
from the untrusted class request. There is deliberately no client-supplied
"unlocked" flag, rank-to-unlock guess, bundled game catalog or HTTP endpoint.
The native editor/transport is a separate acceptance gate.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

ID = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
GUID = re.compile(r"[0-9a-fA-F]{1,32}\Z")
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")
MAX_BYTES = 2_097_152
MAX_REVISION = 2_147_483_647
WILDCARDS = frozenset({"primary_gunfighter", "secondary_gunfighter", "overkill",
                      "perk_1_greed", "perk_2_greed", "perk_3_greed",
                      "danger_close", "tactician"})
SLOTS = frozenset({"primary", "secondary", "perk1", "perk2", "perk3", "lethal", "tactical", "wildcard"})


class Rejected(ValueError):
    """Stable public reason code; never include identity or request text."""


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def identifier(value):
    return isinstance(value, str) and ID.fullmatch(value) is not None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class Item:
    slot: str
    # Tactical insertion/smoke etc. can be limited by the native catalog.
    max_count: int = 1


@dataclass(frozen=True)
class Catalog:
    revision: str
    items: dict[str, Item]
    # Each set is an entire allowed combination, including single attachments.
    # This supports incompatibilities involving three attachments too.
    combinations: dict[str, frozenset[frozenset[str]]]

    def check(self):
        if not token(self.revision) or not isinstance(self.items, dict) or not 1 <= len(self.items) <= 512:
            raise Rejected("catalog_unavailable")
        for name, item in self.items.items():
            if not identifier(name) or type(item) is not Item or not isinstance(item.slot, str) or item.slot not in SLOTS or not integer(item.max_count, 1, 2):
                raise Rejected("catalog_unavailable")
            if item.slot not in ("lethal", "tactical") and item.max_count != 1:
                raise Rejected("catalog_unavailable")
            if item.slot == "wildcard" and name not in WILDCARDS:
                raise Rejected("catalog_unavailable")
        if not isinstance(self.combinations, dict) or len(self.combinations) > 256:
            raise Rejected("catalog_unavailable")
        for weapon, combinations in self.combinations.items():
            if weapon not in self.items or self.items[weapon].slot not in ("primary", "secondary") or type(combinations) is not frozenset or len(combinations) > 1024:
                raise Rejected("catalog_unavailable")
            if any(type(row) is not frozenset or not 1 <= len(row) <= 3 or any(not identifier(x) for x in row) for row in combinations):
                raise Rejected("catalog_unavailable")


@dataclass(frozen=True)
class Observation:
    # These fields must come from the native server adapter, never the editor.
    identity: str
    session: str
    map_epoch: str
    spawn: int
    observed_ms: int
    catalog_revision: str
    allocation: int
    unlocked_items: frozenset[str]
    unlocked_attachments: frozenset[tuple[str, str]]
    human: bool
    playing: bool
    can_customize: bool

    def check(self, catalog, now):
        if type(self.human) is not bool or not self.human or type(self.playing) is not bool or not self.playing:
            raise Rejected("human_session_required")
        if type(self.can_customize) is not bool or not self.can_customize:
            raise Rejected("create_a_class_locked")
        if not isinstance(self.identity, str) or not GUID.fullmatch(self.identity) or not int(self.identity, 16) or not token(self.session) or not token(self.map_epoch):
            raise Rejected("human_session_required")
        if not integer(self.spawn, 0, MAX_REVISION) or not integer(now, 0, MAX_REVISION) or not integer(self.observed_ms, 0, now) or now - self.observed_ms > 5000:
            raise Rejected("observation_stale")
        catalog.check()
        if self.catalog_revision != catalog.revision or not integer(self.allocation, 1, 10):
            raise Rejected("catalog_unavailable")
        if type(self.unlocked_items) is not frozenset or len(self.unlocked_items) > 512 or any(x not in catalog.items for x in self.unlocked_items):
            raise Rejected("observation_invalid")
        if type(self.unlocked_attachments) is not frozenset or len(self.unlocked_attachments) > 8192:
            raise Rejected("observation_invalid")
        for pair in self.unlocked_attachments:
            if type(pair) is not tuple or len(pair) != 2 or any(not identifier(x) for x in pair):
                raise Rejected("observation_invalid")
            if pair[0] not in catalog.items or catalog.items[pair[0]].slot not in ("primary", "secondary"):
                raise Rejected("observation_invalid")


def shape(value):
    """Bound the untrusted JSON before touching catalog, counters or disk."""
    fields = {"primary", "secondary", "primary_attachments", "secondary_attachments",
              "perks", "lethal", "tactical", "wildcards"}
    if type(value) is not dict or set(value) != fields:
        raise Rejected("class_schema")
    for name in ("primary", "secondary"):
        if value[name] is not None and not identifier(value[name]):
            raise Rejected("class_schema")
    for name, limit in (("primary_attachments", 3), ("secondary_attachments", 2), ("wildcards", 3)):
        row = value[name]
        if type(row) is not list or len(row) > limit or any(not identifier(x) for x in row) or len(set(row)) != len(row):
            raise Rejected("class_schema")
    perks = value["perks"]
    if type(perks) is not list or len(perks) != 3:
        raise Rejected("class_schema")
    for row in perks:
        if type(row) is not list or len(row) > 2 or any(not identifier(x) for x in row) or len(set(row)) != len(row):
            raise Rejected("class_schema")
    for name in ("lethal", "tactical"):
        row = value[name]
        if type(row) is not dict or set(row) != {"item", "count"} or not integer(row["count"], 0, 2):
            raise Rejected("class_schema")
        if (row["item"] is None) != (row["count"] == 0) or row["item"] is not None and not identifier(row["item"]):
            raise Rejected("class_schema")
    return copy.deepcopy(value)


@dataclass(frozen=True)
class ValidClass:
    loadout: dict
    points: int
    fingerprint: str


def validate(loadout, catalog: Catalog, observation: Observation, now: int) -> ValidClass:
    value = shape(loadout)
    observation.check(catalog, now)
    cards = set(value["wildcards"])

    def item(name, slot):
        if name not in catalog.items:
            raise Rejected("unknown_item")
        definition = catalog.items[name]
        if definition.slot != slot:
            raise Rejected("wrong_slot")
        if name not in observation.unlocked_items:
            raise Rejected("item_locked")
        return definition

    for card in cards:
        if card not in WILDCARDS:
            raise Rejected("unknown_wildcard")
        item(card, "wildcard")
    points = len(cards)
    primary, secondary = value["primary"], value["secondary"]
    if primary is not None:
        item(primary, "primary")
        points += 1
    if secondary is not None:
        item(secondary, "primary" if "overkill" in cards else "secondary")
        if secondary == primary:
            raise Rejected("duplicate_weapon")
        points += 1
    elif "overkill" in cards:
        raise Rejected("wildcard_without_item")
    for slot in ("primary", "secondary"):
        weapon, attachments = value[slot], value[slot + "_attachments"]
        if attachments and weapon is None:
            raise Rejected("attachment_without_weapon")
        maximum = (3 if "primary_gunfighter" in cards else 2) if slot == "primary" else (2 if "secondary_gunfighter" in cards else 1)
        if len(attachments) > maximum:
            raise Rejected("wildcard_required")
        if attachments:
            if frozenset(attachments) not in catalog.combinations.get(weapon, frozenset()):
                raise Rejected("attachment_conflict")
            if any((weapon, attachment) not in observation.unlocked_attachments for attachment in attachments):
                raise Rejected("attachment_locked")
        if slot + "_gunfighter" in cards and weapon is None:
            raise Rejected("wildcard_without_item")
        points += len(attachments)
    all_perks = []
    for index, perks in enumerate(value["perks"], 1):
        if len(perks) > (2 if "perk_" + str(index) + "_greed" in cards else 1):
            raise Rejected("wildcard_required")
        for perk in perks:
            item(perk, "perk" + str(index))
        all_perks.extend(perks)
        points += len(perks)
    if len(set(all_perks)) != len(all_perks):
        raise Rejected("duplicate_perk")
    lethal, tactical = value["lethal"], value["tactical"]
    if lethal["count"] > 1 and "danger_close" not in cards:
        raise Rejected("wildcard_required")
    if "danger_close" in cards and lethal["count"] == 0:
        raise Rejected("wildcard_without_item")
    for name, equipment in (("lethal", lethal), ("tactical", tactical)):
        if equipment["item"] is not None:
            definition = item(equipment["item"], name)
            if equipment["count"] > definition.max_count:
                raise Rejected("equipment_count")
            points += equipment["count"]
    # Second tactical type in the lethal slot needs a separate schema. Refuse
    # Tactician until both native slot layout and count costs are accepted.
    if "tactician" in cards:
        raise Rejected("unsupported_wildcard")
    if points > observation.allocation:
        raise Rejected("allocation_exceeded")
    # A knife-only class remains legal; knife and cosmetics are not charged.
    return ValidClass(value, points, digest(value))


class ArmoryStore:
    """Single-writer, revision-checked private slot; identity is HMAC salted.

    Exactly one worker must own this file. Native saves and other Outlands
    ledgers are separate. Session tokens and raw native identity never persist.
    """
    def __init__(self, path):
        self.path = Path(path).absolute()
        self.failed = False
        if os.name == "nt":
            raise Rejected("store_requires_posix_host")
        for part in (self.path.parent, *self.path.parent.parents):
            if part.is_symlink():
                raise Rejected("store_path")
        info = self.path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise Rejected("store_permissions")
        self.state = {"schema": 1, "salt": secrets.token_hex(32), "players": {}}
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except FileNotFoundError:
            return
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > MAX_BYTES:
                raise Rejected("store_permissions")
            state = json.loads(stream.read(MAX_BYTES + 1))
        self.check(state)
        self.state = state

    @staticmethod
    def check(state):
        if type(state) is not dict or set(state) != {"schema", "salt", "players"} or not integer(state["schema"], 1, 1) or not isinstance(state["salt"], str) or not HEX.fullmatch(state["salt"]):
            raise Rejected("store_schema")
        if type(state["players"]) is not dict or len(state["players"]) > 512:
            raise Rejected("store_capacity")
        for key, record in state["players"].items():
            if not isinstance(key, str) or not HEX.fullmatch(key) or type(record) is not dict or set(record) != {"revision", "loadout", "catalog", "request", "fingerprint", "claim"}:
                raise Rejected("store_schema")
            if not integer(record["revision"], 1, MAX_REVISION) or not token(record["catalog"]) or any(not isinstance(record[x], str) or not HEX.fullmatch(record[x]) for x in ("request", "fingerprint")):
                raise Rejected("store_schema")
            if digest(shape(record["loadout"])) != record["fingerprint"]:
                raise Rejected("store_schema")
            claim = record["claim"]
            if claim is not None and (type(claim) is not dict or set(claim) != {"scope", "spawn"} or not isinstance(claim["scope"], str) or not HEX.fullmatch(claim["scope"]) or not integer(claim["spawn"], 0, MAX_REVISION)):
                raise Rejected("store_schema")

    def key(self, identity):
        if not isinstance(identity, str) or not GUID.fullmatch(identity) or not int(identity, 16):
            raise Rejected("human_session_required")
        return hmac.new(bytes.fromhex(self.state["salt"]), ("armory:" + identity.lower()).encode("ascii"), hashlib.sha256).hexdigest()

    def read(self, identity):
        if self.failed:
            raise Rejected("store_reload_required")
        return copy.deepcopy(self.state["players"].get(self.key(identity)))

    def commit(self, state):
        if self.failed:
            raise Rejected("store_reload_required")
        self.check(state)
        raw = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("ascii")
        if len(raw) > MAX_BYTES:
            raise Rejected("store_capacity")
        temporary = None
        renamed = False
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".armory-", delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists() or self.path.is_symlink():
                info = self.path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise Rejected("store_permissions")
            os.replace(temporary, self.path)
            renamed = True
            temporary = None
            directory = os.open(self.path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.state = state
        except OSError:
            # After rename, disk may contain the new revision even if directory
            # fsync failed. Require reload before any further reads or writes;
            # never acknowledge an uncertain commit or overwrite from old RAM.
            if renamed:
                self.failed = True
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save(self, observation, catalog, loadout, expected_revision, request, now):
        if self.failed:
            raise Rejected("store_reload_required")
        validated = validate(loadout, catalog, observation, now)
        if not integer(expected_revision, 0, MAX_REVISION - 1) or not token(request):
            raise Rejected("save_request")
        key = self.key(observation.identity)
        previous = self.state["players"].get(key)
        request_hash = digest([observation.session, request])
        if previous and previous["request"] == request_hash:
            if previous["revision"] == expected_revision + 1 and previous["fingerprint"] == validated.fingerprint and previous["catalog"] == catalog.revision:
                return copy.deepcopy(previous)
            raise Rejected("request_conflict")
        if (previous["revision"] if previous else 0) != expected_revision:
            raise Rejected("revision_conflict")
        state = copy.deepcopy(self.state)
        state["players"][key] = {"revision": expected_revision + 1, "loadout": validated.loadout,
                                 "catalog": catalog.revision, "request": request_hash,
                                 "fingerprint": validated.fingerprint, "claim": None}
        self.commit(state)
        return self.read(observation.identity)

    def scope(self, observation):
        value = json.dumps([self.key(observation.identity), observation.session, observation.map_epoch], separators=(",", ":"))
        return hmac.new(bytes.fromhex(self.state["salt"]), ("claim:" + value).encode("ascii"), hashlib.sha256).hexdigest()

    def was_claimed(self, observation, record):
        return record["claim"] is not None and record["claim"]["scope"] == self.scope(observation)

    def consume(self, observation, revision):
        record = self.read(observation.identity)
        if record is None or record["revision"] != revision:
            raise Rejected("revision_conflict")
        if self.was_claimed(observation, record):
            raise Rejected("revision_already_claimed")
        state = copy.deepcopy(self.state)
        state["players"][self.key(observation.identity)]["claim"] = {"scope": self.scope(observation), "spawn": observation.spawn}
        self.commit(state)


@dataclass(frozen=True)
class Ticket:
    identity_key: str
    session: str
    map_epoch: str
    after_spawn: int
    revision: int
    fingerprint: str
    catalog_revision: str


class RespawnQueue:
    """One replaceable pending revision per identity, consumed at most once.

    Never applies inventory itself. A future trusted adapter must call claim
    at the native pre-loadout boundary, verify the actual result, then report
    application. A claim is not an equipment acknowledgement. Pending requests
    are intentionally volatile; consumed claims are persisted before returning.
    """
    def __init__(self, store, catalog):
        self.store, self.catalog = store, copy.deepcopy(catalog)
        self.pending = {}

    def enqueue(self, observation, revision, now):
        observation.check(self.catalog, now)
        record = self.store.read(observation.identity)
        if not integer(revision, 1, MAX_REVISION) or record is None or record["revision"] != revision:
            raise Rejected("revision_conflict")
        validate(record["loadout"], self.catalog, observation, now)
        if record["catalog"] != self.catalog.revision:
            raise Rejected("catalog_changed")
        key = self.store.key(observation.identity)
        if self.store.was_claimed(observation, record):
            raise Rejected("revision_already_claimed")
        ticket = Ticket(key, observation.session, observation.map_epoch, observation.spawn,
                        revision, record["fingerprint"], self.catalog.revision)
        if key in self.pending and self.pending[key].revision == revision:
            if self.pending[key] != ticket:
                del self.pending[key]
                raise Rejected("queue_session_changed")
            return self.pending[key]
        if len(self.pending) >= 512 and key not in self.pending:
            raise Rejected("queue_capacity")
        self.pending[key] = ticket
        return ticket

    def cancel(self, identity):
        self.pending.pop(self.store.key(identity), None)

    def claim(self, observation, now):
        key = self.store.key(observation.identity)
        ticket = self.pending.get(key)
        if ticket is None:
            return None
        try:
            observation.check(self.catalog, now)
            if observation.session != ticket.session or observation.map_epoch != ticket.map_epoch or observation.spawn < ticket.after_spawn:
                raise Rejected("queue_session_changed")
            if observation.spawn == ticket.after_spawn:
                return None
            if observation.spawn != ticket.after_spawn + 1:
                raise Rejected("spawn_missed")
            record = self.store.read(observation.identity)
            if record is None or record["revision"] != ticket.revision or record["fingerprint"] != ticket.fingerprint or record["catalog"] != ticket.catalog_revision:
                raise Rejected("revision_conflict")
            validated = validate(record["loadout"], self.catalog, observation, now)
            # Durable consume before handing a class to an equip adapter. A
            # crash after this point may lose an equip, never replay it silently.
            self.store.consume(observation, ticket.revision)
        except (Rejected, ValueError, OSError):
            self.pending.pop(key, None)
            raise
        del self.pending[key]
        return {"revision": ticket.revision, "loadout": validated.loadout,
                "fingerprint": validated.fingerprint, "status": "claimed_not_applied"}
