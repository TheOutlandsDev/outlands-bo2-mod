"""Server-observed Outlands milestones, separate from native BO2 progression.

Single worker, atomic private JSON. Only salted identity hashes and bounded
numeric observations persist; no names, chat, addresses or native saves.
"""
from dataclasses import dataclass
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

MARKER = 'OUTLANDS_OP_V1|'
TRACKS = ('assault', 'objective', 'support')
THRESHOLDS = {'assault': (25, 100, 250), 'objective': (3, 10, 25), 'support': (3, 10, 25)}
LIMIT = 1_000_000_000
MAX_BYTES = 2_097_152
TOKEN = re.compile(r'[A-Za-z0-9_-]{1,48}\Z')
HEX = re.compile(r'[0-9a-fA-F]{1,32}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')


def uint(value, maximum=LIMIT):
    return type(value) is int and 0 <= value <= maximum


@dataclass(frozen=True)
class OperationEvent:
    session: str
    sequence: int
    kind: str
    slot: int
    identity: str
    kills: int
    objective: int
    support: int
    track: str

    @property
    def request_id(self):
        return self.session + '_' + str(self.sequence)

    @classmethod
    def parse(cls, line):
        if not line.startswith(MARKER) or len(line) > 256:
            return None
        fields = line[len(MARKER):].split('|')
        if len(fields) != 9:
            return None
        session, seq, kind, slot, identity, kills, objective, support, track = fields
        if not TOKEN.fullmatch(session) or kind not in ('hello', 'snapshot', 'show', 'select'):
            return None
        if not all(re.fullmatch(r'0|[1-9][0-9]{0,9}', x) for x in (seq, slot, kills, objective, support)):
            return None
        seq, slot, kills, objective, support = map(int, (seq, slot, kills, objective, support))
        if not 1 <= seq <= 2_147_483_647 or slot > 17 or kills > 1_000_000 or objective > 10000 or support > 10000:
            return None
        if not HEX.fullmatch(identity) or not int(identity, 16):
            return None
        if (kind == 'select' and track not in TRACKS) or (kind != 'select' and track != 'none'):
            return None
        return cls(session, seq, kind, slot, identity.lower(), kills, objective, support, track)


class OperationStore:
    """Bounded private milestones with commit-before-response replay protection."""
    def __init__(self, path):
        self.path = Path(path).absolute()
        for part in (self.path.parent, *self.path.parent.parents):
            if part.is_symlink():
                raise ValueError('Operation directory cannot contain symlinks')
        info = self.path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Operation directory must be owned and mode 700')
        self.state = {'schema': 1, 'salt': secrets.token_hex(32), 'players': {}, 'sessions': {}, 'retired': []}
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > MAX_BYTES:
                raise ValueError('Operation state must be an owned private regular file')
            state = json.loads(stream.read(MAX_BYTES + 1))
        self.validate(state)
        self.state = state

    @staticmethod
    def validate(state):
        if not isinstance(state, dict) or set(state) != {'schema', 'salt', 'players', 'sessions', 'retired'} or type(state['schema']) is not int or state['schema'] != 1 or not isinstance(state['salt'], str) or not HASH.fullmatch(state['salt']):
            raise ValueError('Unsupported operation state')
        players, sessions, retired = state['players'], state['sessions'], state['retired']
        if not isinstance(players, dict) or len(players) > 512 or not isinstance(sessions, dict) or len(sessions) > 256 or not isinstance(retired, list) or len(retired) > 1024 or len(set(retired)) != len(retired):
            raise ValueError('Operation capacity or state invalid')
        if any(not isinstance(x, str) or not HASH.fullmatch(x) for x in retired):
            raise ValueError('Invalid retired operation session')
        for key, player in players.items():
            if not HASH.fullmatch(key) or not isinstance(player, dict) or set(player) != {*TRACKS, 'selected'} or player['selected'] not in TRACKS or any(not uint(player[t]) for t in TRACKS):
                raise ValueError('Invalid operation milestone')
        for key, item in sessions.items():
            if not HASH.fullmatch(key) or not isinstance(item, dict) or set(item) != {'player', 'slot', 'seq', 'counts', 'fingerprint'} or item['player'] not in players or not uint(item['slot'],17) or not uint(item['seq'],2_147_483_647) or item['seq'] < 1 or not isinstance(item['counts'],list) or len(item['counts']) != 3 or any(not uint(x) for x in item['counts']) or not isinstance(item['fingerprint'], str) or not HASH.fullmatch(item['fingerprint']):
                raise ValueError('Invalid operation observation')

    def _hash(self, domain, value):
        return hmac.new(bytes.fromhex(self.state['salt']), (domain + ':' + value).encode('ascii'), hashlib.sha256).hexdigest()

    def _commit(self, state):
        self.validate(state)
        raw = json.dumps(state, sort_keys=True, separators=(',', ':')).encode('ascii')
        if len(raw) > MAX_BYTES:
            raise ValueError('Operation state capacity reached')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.operations-', delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.is_symlink():
                raise ValueError('Operation state cannot be a link')
            os.replace(temporary, self.path)
            temporary = None
            directory = os.open(self.path.parent, os.O_RDONLY | getattr(os,'O_DIRECTORY',0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            self.state = state
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def apply(self, event):
        # Public entry also validates manually constructed synthetic objects.
        wire = MARKER + '|'.join(map(str, (event.session,event.sequence,event.kind,event.slot,event.identity,event.kills,event.objective,event.support,event.track)))
        if OperationEvent.parse(wire) != event:
            return None
        key = self._hash('player', event.identity)
        session = self._hash('session', event.session)
        if session in self.state['retired']:
            return None
        fingerprint = hashlib.sha256(wire.encode('ascii')).hexdigest()
        old = self.state['sessions'].get(session)
        if old:
            if old['player'] != key or old['slot'] != event.slot or event.sequence < old['seq']:
                return None
            if event.sequence == old['seq']:
                return self.profile(self.state['players'][key]) if old['fingerprint'] == fingerprint else None
        elif event.kind != 'hello':
            return None
        state = copy.deepcopy(self.state)
        if key not in state['players']:
            if len(state['players']) >= 512:
                raise ValueError('Operation player capacity reached')
            state['players'][key] = dict.fromkeys(TRACKS, 0) | {'selected': 'assault'}
        player = state['players'][key]
        counts = [event.kills, event.objective, event.support]
        if old and event.kind != 'hello':
            deltas = [new - previous for new, previous in zip(counts, old['counts'])]
            # Counter decreases rebase that metric. Implausible jumps reject
            # all rewards for this sample while establishing a fresh baseline.
            if all(delta <= cap for delta, cap in zip(deltas, (256, 5, 5))):
                for track, delta in zip(TRACKS, deltas):
                    player[track] = min(LIMIT, player[track] + max(0, delta))
        if event.kind == 'select':
            player['selected'] = event.track
        state['sessions'][session] = {'player':key, 'slot':event.slot, 'seq':event.sequence, 'counts':counts, 'fingerprint':fingerprint}
        while len(state['sessions']) > 256:
            retired = next(iter(state['sessions']))
            del state['sessions'][retired]
            state['retired'] = (state['retired'] + [retired])[-1024:]
        self._commit(state)
        return self.profile(player)

    @staticmethod
    def profile(player):
        result = {t: player[t] for t in TRACKS}
        result['selected'] = player['selected']
        result['operation'] = int(all(player[t] >= THRESHOLDS[t][0] for t in TRACKS))
        return result


def response_value(event, profile):
    if set(profile) != {*TRACKS, 'selected', 'operation'} or any(not uint(profile[t]) for t in TRACKS) or profile['selected'] not in TRACKS or not uint(profile['operation'],1):
        raise ValueError('Unsafe operation profile')
    if not TOKEN.fullmatch(event.session) or not uint(event.slot,17) or not 1 <= event.sequence <= 2_147_483_647:
        raise ValueError('Unsafe operation response identity')
    return '|'.join(map(str,(event.request_id,event.slot,profile['assault'],profile['objective'],profile['support'],profile['selected'],profile['operation'])))
