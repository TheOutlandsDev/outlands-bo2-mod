#!/usr/bin/env python3
"""Opt-in native challenge follower; no HTTP, chat, RCON or save-file writes.

This preview is not enabled by the live worker. The separately installed native
adapter must supply a private token, a bound human session and confirmed kills.
Progress is server-local; Google-account ownership migration is a later gate.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import stat
import time

try:
    from camo_challenge import ChallengeStore, KillEvent, REVISION, WEAPON_ID
except ModuleNotFoundError:
    from ai.camo_challenge import ChallengeStore, KillEvent, REVISION, WEAPON_ID

MARKER = 'OUTLANDS_CHALLENGE_V1|'
TOKEN = re.compile(r'[A-Za-z0-9_-]{1,48}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
GUID = re.compile(r'[0-9a-f]{1,32}\Z')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


@dataclass(frozen=True)
class NativeEvent:
    credential: str
    match: str
    session: str
    sequence: int
    kind: str
    slot: int
    identity: str
    weapon: str
    human: bool
    enemy: bool
    headshot: bool
    confirmed: bool

    @classmethod
    def parse(cls, line):
        if not isinstance(line, str) or len(line) > 512:
            return None
        line = ANSI.sub('', line)
        if not line.startswith(MARKER):
            return None
        fields = line.rstrip('\r\n').split('|')[1:]
        if len(fields) != 12:
            return None
        credential, match, session, seq, kind, slot, guid, weapon, human, enemy, headshot, confirmed = fields
        if (not HEX.fullmatch(credential) or not TOKEN.fullmatch(match) or not TOKEN.fullmatch(session)
                or kind not in ('hello', 'kill', 'depart') or not GUID.fullmatch(guid) or not int(guid, 16)
                or not re.fullmatch(r'[1-9][0-9]{0,9}', seq) or int(seq) > 2147483647
                or not re.fullmatch(r'0|[1-9][0-9]?', slot) or int(slot) > 17
                or any(x not in ('0', '1') for x in (human, enemy, headshot, confirmed))
                or not re.fullmatch(r'[a-z0-9_]{1,48}', weapon)):
            return None
        if kind != 'kill' and (weapon != 'none' or (enemy, headshot, confirmed) != ('0', '0', '0')):
            return None
        return cls(credential, match, session, int(seq), kind, int(slot), guid,
                   weapon, human == '1', enemy == '1', headshot == '1', confirmed == '1')


def read_private(path):
    path = Path(path)
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Private challenge key cannot contain links')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size != 64:
            raise ValueError('Owned private challenge key required')
        value = stream.read(65).decode('ascii')
    if not HEX.fullmatch(value):
        raise ValueError('Invalid private challenge key')
    return value


def identity_salt(directory):
    directory = Path(directory)
    path = directory / 'identity.key'
    if path.exists() or path.is_symlink():
        return read_private(path)
    if (directory / 'progress.json').exists():
        raise ValueError('Existing challenge ledger requires its original identity key')
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(secrets.token_hex(32)); stream.flush(); os.fsync(stream.fileno())
    return read_private(path)


class ChallengeAdapter:
    def __init__(self, store, credential, salt):
        if not HEX.fullmatch(credential) or not HEX.fullmatch(salt):
            raise ValueError('Private challenge keys required')
        self.store, self.credential, self.salt = store, credential, bytes.fromhex(salt)
        self.sessions = {}
        self.retired = set()
        self.accepted = self.rejected = self.records = 0

    def player_key(self, identity):
        return hmac.new(self.salt, ('outlands-challenge-native-v1:' + identity).encode('ascii'), hashlib.sha256).hexdigest()

    def ingest(self, line):
        event = NativeEvent.parse(line)
        if event is None:
            return None
        self.records += 1
        if not hmac.compare_digest(event.credential, self.credential) or not event.human:
            self.rejected += 1
            return None
        current = self.sessions.get(event.slot)
        key = (event.match, event.session, event.identity)
        if event.kind == 'hello':
            if event.session in self.retired or len(self.retired) >= 4096:
                self.rejected += 1
                return None
            if any(row['key'][1] == event.session and (slot != event.slot or row['key'] != key)
                   for slot, row in self.sessions.items()):
                self.rejected += 1
                return None
            if current and current['key'] != key:
                self.retired.add(current['key'][1])
            if current and current['key'] == key and event.sequence <= current['sequence']:
                self.rejected += 1
                return None
            self.sessions[event.slot] = {'key': key, 'sequence': event.sequence}
            return None
        if not current or current['key'] != key or event.sequence <= current['sequence']:
            self.rejected += 1
            return None
        # Observe order before eligibility; a later event cannot re-use an
        # ignored native sequence with a more favourable payload.
        current['sequence'] = event.sequence
        if event.kind == 'depart':
            self.retired.add(event.session)
            del self.sessions[event.slot]
            return None
        result = self.store.apply(KillEvent(self.player_key(event.identity), event.session,
                                           event.match, event.sequence, event.weapon, REVISION,
                                           event.human, event.enemy, event.headshot, event.confirmed))
        if result is None:
            self.rejected += 1
        else:
            self.accepted += 1
        return result


class NativeLog:
    """Bounded regular-file reader. Replays current log safely after restart.

    The ledger deduplicates awards. A worker offline across archived log rotation
    can miss events; this preview never infers rewards from scoreboard totals.
    """
    def __init__(self, path):
        self.path = Path(path); self.identity = None; self.offset = 0
        self.buffer = b''; self.discard = False

    def poll(self):
        try:
            descriptor = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return []
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('Native log must be regular')
            identity = info.st_dev, info.st_ino
            if identity != self.identity or info.st_size < self.offset:
                self.identity = identity; self.offset = 0; self.buffer = b''; self.discard = False
            stream.seek(self.offset); data = stream.read(65536); self.offset += len(data)
        pieces = (self.buffer + data).split(b'\n'); self.buffer = pieces.pop()
        result = []
        for part in pieces:
            if not self.discard and len(part) <= 512:
                result.append(part.decode('ascii', 'replace').rstrip('\r'))
            self.discard = False
        if len(self.buffer) > 512:
            self.buffer = b''; self.discard = True
        return result


@contextmanager
def writer_lock(directory):
    import fcntl
    # Reuse the store's owned/private-directory validation before creating a
    # lock. O_NOFOLLOW also protects the lock file itself.
    ChallengeStore(Path(directory) / 'progress.json')
    descriptor = os.open(Path(directory)/'writer.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Private owned challenge lock required')
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def follow(args):
    store = ChallengeStore(args.state / 'progress.json')
    adapter = ChallengeAdapter(store, read_private(args.credential), identity_salt(args.state))
    log = NativeLog(args.log)
    print('Outlands challenge follower ready; native human sessions only', flush=True)
    next_summary = time.monotonic() + 10
    while True:
        for line in log.poll():
            adapter.ingest(line)
        if time.monotonic() >= next_summary:
            print('Challenge observations: records=%d accepted=%d rejected=%d' %
                  (adapter.records, adapter.accepted, adapter.rejected), flush=True)
            next_summary = time.monotonic() + 10
        time.sleep(.1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--state', type=Path, default=Path('/challenges'))
    parser.add_argument('--log', type=Path, default=Path('/data/plutonium/console.log'))
    parser.add_argument('--credential', type=Path, default=Path('/data/private/challenge_token'))
    args = parser.parse_args()
    if not args.run:
        print('Preview: private native events only; no client, camo rendering or account portability acceptance')
        return 0
    with writer_lock(args.state):
        return follow(args)


if __name__ == '__main__':
    raise SystemExit(main())
