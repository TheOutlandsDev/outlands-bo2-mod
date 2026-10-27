"""Fixed native Armory transport. Runs independently of chat/model latency.

Only the native script emits these private log observations. No HTTP endpoint,
client-provided unlock metadata, names or chat are accepted by this adapter.
The first native editor supports seven base slots, without attachments/cards.
"""
from dataclasses import dataclass

from armory import (ArmoryStore, Catalog, Item, Observation, Rejected,
                    RespawnQueue, GUID, integer, token, identifier, digest)

MARKER = "OUTLANDS_ARMORY_V3|"
FIELDS = ("primary", "secondary", "perk1", "perk2", "perk3", "lethal", "tactical")
NONE = "none"
REVISION = "native_base_v1"
KINDS = frozenset({"hello", "save", "equip", "claim", "cancel", "applied", "failed"})
STATUSES = frozenset({"empty", "saved", "queued", "armed", "cancelled", "applied", "unconfirmed", "rejected"})


@dataclass(frozen=True)
class NativeRequest:
    session: str
    sequence: int
    kind: str
    slot: int
    identity: str
    epoch: str
    spawn: int
    allocation: int
    clock: int
    refs: tuple
    groups: tuple
    unlocked: str
    can_customize: bool
    revision: int

    @property
    def request_id(self):
        return self.session + "_" + str(self.sequence)

    @classmethod
    def parse(cls, text):
        if not isinstance(text, str) or not text.startswith(MARKER) or len(text) > 1500:
            return None
        row = text[len(MARKER):].split("|")
        if len(row) != 15:
            return None
        session, sequence, kind, slot, identity, epoch, spawn, allocation, clock, refs, groups, unlocked, customize, revision, version = row
        numbers = (sequence, slot, spawn, allocation, clock, revision)
        if any(not x.isascii() or not x.isdecimal() or len(x) > 10 or str(int(x)) != x for x in numbers):
            return None
        sequence, slot, spawn, allocation, clock, revision = map(int, numbers)
        if not token(session) or len(session) > 36 or not token(epoch) or kind not in KINDS or not 1 <= sequence <= 2147483647 or not 0 <= slot <= 17 or not 0 <= spawn <= 2147483647 or not 1 <= allocation <= 10 or not 0 <= clock <= 2147483647 or not 0 <= revision <= 2147483647:
            return None
        if not GUID.fullmatch(identity) or not int(identity, 16) or customize not in ("0", "1") or version != "base1":
            return None
        refs, groups = tuple(refs.split(",")), tuple(groups.split(","))
        if len(refs) != 7 or len(groups) != 7 or len(unlocked) != 7 or any(x not in "01" for x in unlocked):
            return None
        if any(not identifier(x) for x in refs) or any(x not in (*FIELDS, NONE) for x in groups):
            return None
        if any((ref == NONE) != (group == NONE) or ref == NONE and bit != "0" for ref, group, bit in zip(refs, groups, unlocked)):
            return None
        return cls(session, sequence, kind, slot, identity.lower(), epoch, spawn, allocation, clock, refs, groups, unlocked, customize == "1", revision)

    def context(self):
        items = {}
        for ref, group in zip(self.refs, self.groups):
            if ref == NONE:
                continue
            if ref in items and items[ref].slot != group:
                raise Rejected("native_metadata")
            items[ref] = Item(group)
        # An empty draft still needs a valid catalog, never an earned dummy item.
        if not items:
            items = {"armory_unavailable": Item("primary")}
        catalog = Catalog(REVISION, items, {})
        unlocked = frozenset(ref for ref, bit in zip(self.refs, self.unlocked) if bit == "1")
        observed = Observation(self.identity, self.session, self.epoch, self.spawn,
                               self.clock, REVISION, self.allocation, unlocked,
                               frozenset(), True, True, self.can_customize)
        primary, secondary, p1, p2, p3, lethal, tactical = self.refs
        optional = lambda value: None if value == NONE else value
        loadout = {"primary": optional(primary), "secondary": optional(secondary),
                   "primary_attachments": [], "secondary_attachments": [],
                   "perks": [[] if x == NONE else [x] for x in (p1, p2, p3)],
                   "lethal": {"item": optional(lethal), "count": int(lethal != NONE)},
                   "tactical": {"item": optional(tactical), "count": int(tactical != NONE)},
                   "wildcards": []}
        return catalog, observed, loadout


def native_refs(loadout):
    """No truncation of an advanced saved class into a different base class."""
    if loadout["primary_attachments"] or loadout["secondary_attachments"] or loadout["wildcards"] or any(len(row) > 1 for row in loadout["perks"]) or any(loadout[x]["count"] > 1 for x in ("lethal", "tactical")):
        raise Rejected("native_base_subset")
    return tuple([loadout["primary"] or NONE, loadout["secondary"] or NONE]
                 + [row[0] if row else NONE for row in loadout["perks"]]
                 + [loadout[x]["item"] or NONE for x in ("lethal", "tactical")])


def response(request, status, revision=0, refs=(NONE,) * 7):
    if status not in STATUSES or not integer(revision, 0, 2147483647) or len(refs) != 7 or any(not identifier(x) for x in refs):
        raise Rejected("native_response")
    # Request ID + slot bind to the server's one in-flight native mailbox.
    return "|".join((request.request_id, str(request.slot), status, str(revision), ",".join(refs)))


class NativeArmory:
    """Single writer for private Armory state, with bounded session replay guards."""
    def __init__(self, store: ArmoryStore):
        self.store = store
        self.sessions = {}
        self.retired = set()
        self.queues = {}

    def handle(self, request):
        # Validate manually constructed test/caller objects through the same parser.
        wire = MARKER + "|".join(map(str, (request.session, request.sequence, request.kind,
                request.slot, request.identity, request.epoch, request.spawn, request.allocation,
                request.clock, ",".join(request.refs), ",".join(request.groups), request.unlocked,
                int(request.can_customize), request.revision, "base1")))
        if NativeRequest.parse(wire) != request:
            return None
        key = self.store.key(request.identity)
        session = digest([request.session, request.epoch])
        if session in self.retired:
            return None
        previous = self.sessions.get(session)
        fingerprint = digest(wire)
        if previous:
            if previous["key"] != key or previous["slot"] != request.slot or request.sequence < previous["sequence"]:
                return None
            if request.sequence == previous["sequence"]:
                return previous["response"] if previous["fingerprint"] == fingerprint else None
        elif request.kind != "hello":
            # Native must re-handshake after worker restart. No pending replay.
            return response(request, "rejected")
        try:
            value = self.apply(key, request)
        except Rejected:
            value = response(request, "rejected")
        self.sessions[session] = {"key": key, "slot": request.slot, "sequence": request.sequence,
                                  "fingerprint": fingerprint, "response": value}
        while len(self.sessions) > 128:
            oldest = next(iter(self.sessions))
            self.retired.add(oldest)
            del self.sessions[oldest]
        # Refuse new sessions at capacity rather than reaccept retired nonces.
        if len(self.retired) > 4096:
            raise Rejected("native_session_capacity")
        return value

    def apply(self, key, request):
        record = self.store.read(request.identity)
        if request.kind == "hello":
            # Hello starts a new map/connection session and cancels any old queue.
            self.queues.pop(key, None)
            if record is None:
                return response(request, "empty")
            return response(request, "saved", record["revision"], native_refs(record["loadout"]))
        if request.kind == "cancel":
            self.queues.pop(key, None)
            return response(request, "cancelled", record["revision"] if record else 0)
        if request.kind in ("applied", "failed"):
            if record is None or record["revision"] != request.revision or not self.store.was_claimed(request.context()[1], record) or record["claim"]["spawn"] != request.spawn or native_refs(record["loadout"]) != request.refs:
                raise Rejected("native_ack")
            return response(request, "applied" if request.kind == "applied" else "unconfirmed", record["revision"], native_refs(record["loadout"]))
        catalog, observed, loadout = request.context()
        if request.kind == "save":
            record = self.store.save(observed, catalog, loadout, request.revision, str(request.sequence), request.clock)
            queue = RespawnQueue(self.store, catalog)
            queue.enqueue(observed, record["revision"], request.clock)
            self.queues[key] = queue
            return response(request, "queued", record["revision"], native_refs(record["loadout"]))
        if record is None or record["revision"] != request.revision or native_refs(record["loadout"]) != request.refs:
            raise Rejected("native_revision")
        if request.kind == "equip":
            queue = RespawnQueue(self.store, catalog)
            queue.enqueue(observed, record["revision"], request.clock)
            self.queues[key] = queue
            return response(request, "queued", record["revision"], request.refs)
        if request.kind == "claim":
            queue = self.queues.get(key)
            if queue is None:
                raise Rejected("native_queue_missing")
            queue.catalog = catalog
            claimed = queue.claim(observed, request.clock)
            if claimed is None:
                raise Rejected("native_claim")
            del self.queues[key]
            return response(request, "armed", claimed["revision"], request.refs)
        raise Rejected("native_kind")


def serve(path, tail, sink, stop, ansi, logger):
    """Independent thread, fixed loopback RCON sink, fail closed on store error."""
    try:
        service = NativeArmory(ArmoryStore(path))
        logger.info("Armory persistence ready; native identity requests only")
        while not stop.is_set():
            for line in tail.poll():
                event = NativeRequest.parse(ansi.sub("", line).rstrip("\r\n"))
                if event is None:
                    continue
                value = service.handle(event)
                if value is not None:
                    sink.send_armory(value)
            stop.wait(0.025)
    except (OSError, ValueError, TypeError):
        logger.error("Armory worker stopped; native requests will time out without applying")
