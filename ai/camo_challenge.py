"""Portable first Outlands camo challenge; no native event adapter or render path yet.

Only a trusted server adapter may call apply() with server-observed kill events.
Client messages, scoreboard totals and browser requests are never evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

CHALLENGE_ID = 'outlands_dusk_an94_headshots'
CAMO_ID = 'outlands_dusk'
WEAPON_ID = 'an94_mp'
REVISION = 1
TARGET = 25
MAX_BYTES = 2_097_152
HEX = re.compile(r'[0-9a-f]{64}\Z')
TOKEN = re.compile(r'[A-Za-z0-9_-]{1,48}\Z')


@dataclass(frozen=True)
class KillEvent:
    # player_key is a trusted salted identity key; never a raw GUID or email.
    player_key: str
    session: str
    match: str
    sequence: int
    weapon: str
    revision: int
    human: bool
    enemy: bool
    headshot: bool
    kill_confirmed: bool

    def eligible(self):
        return (isinstance(self.player_key, str) and HEX.fullmatch(self.player_key)
                and isinstance(self.session, str) and TOKEN.fullmatch(self.session)
                and isinstance(self.match, str) and TOKEN.fullmatch(self.match)
                and type(self.sequence) is int and 1 <= self.sequence <= 2_147_483_647
                and self.weapon == WEAPON_ID and type(self.revision) is int
                and self.revision == REVISION and self.human is True
                and self.enemy is True and self.headshot is True
                and self.kill_confirmed is True)


def public_progress(player):
    return {'challenge': CHALLENGE_ID, 'camo': CAMO_ID, 'weapon': WEAPON_ID,
            'progress': player['progress'], 'target': TARGET,
            'unlocked': player['progress'] == TARGET}


class ChallengeStore:
    """Private exactly-once progress with commit-before-reward acknowledgment."""
    def __init__(self, path):
        self.path = Path(path).absolute()
        for parent in (self.path.parent, *self.path.parent.parents):
            if parent.is_symlink():
                raise ValueError('Challenge directory cannot contain links')
        info = self.path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Challenge directory must be owned and private')
        self.state = {'schema': 1, 'challenge': CHALLENGE_ID,
                      'revision': REVISION, 'target': TARGET, 'players': {}}
        self.poisoned = False
        try:
            fd = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except FileNotFoundError:
            return
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_BYTES):
                raise ValueError('Challenge state must be an owned private file')
            state = json.loads(stream.read(MAX_BYTES + 1))
        self.validate(state)
        self.state = state

    @staticmethod
    def validate(state):
        if (type(state) is not dict or set(state) != {'schema', 'challenge', 'revision', 'target', 'players'}
                or state['schema'] != 1 or state['challenge'] != CHALLENGE_ID
                or state['revision'] != REVISION or state['target'] != TARGET
                or type(state['players']) is not dict
                or len(state['players']) > 512):
            raise ValueError('Invalid challenge state')
        for key, player in state['players'].items():
            if (not isinstance(key, str) or not HEX.fullmatch(key)
                    or type(player) is not dict or set(player) != {'progress', 'seen'}
                    or type(player['progress']) is not int
                    or not 0 <= player['progress'] <= TARGET
                    or type(player['seen']) is not dict
                    or len(player['seen']) != player['progress']):
                raise ValueError('Invalid challenge player')
            if any(not isinstance(event_id, str) or not HEX.fullmatch(event_id)
                   or not isinstance(fingerprint, str) or not HEX.fullmatch(fingerprint)
                   for event_id, fingerprint in player['seen'].items()):
                raise ValueError('Invalid challenge receipt')

    def _commit(self, next_state):
        self.validate(next_state)
        data = json.dumps(next_state, sort_keys=True, separators=(',', ':')).encode('ascii')
        if len(data) > MAX_BYTES:
            raise ValueError('Challenge state capacity reached')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix='.camo-', delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.is_symlink():
                raise ValueError('Challenge state cannot be a link')
            os.replace(temporary, self.path)
            temporary = None
            fd = os.open(self.path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            self.state = next_state
        except Exception:
            if temporary is None:
                # Rename may have succeeded; reload before another mutation.
                self.poisoned = True
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, player_key):
        if self.poisoned:
            raise ValueError('Challenge store requires reload')
        if not isinstance(player_key, str) or not HEX.fullmatch(player_key):
            return None
        return public_progress(self.state['players'].get(player_key, {'progress': 0}))

    def apply(self, event):
        if self.poisoned:
            raise ValueError('Challenge store requires reload')
        if type(event) is not KillEvent or not event.eligible():
            return None
        player = self.state['players'].get(event.player_key, {'progress': 0, 'seen': {}})
        if player['progress'] == TARGET:
            return public_progress(player)
        event_id = hashlib.sha256((event.session + ':' + str(event.sequence)).encode('ascii')).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(asdict(event), sort_keys=True,
                                                 separators=(',', ':')).encode('ascii')).hexdigest()
        prior = player['seen'].get(event_id)
        if prior is not None:
            return public_progress(player) if prior == fingerprint else None
        if event.player_key not in self.state['players'] and len(self.state['players']) >= 512:
            raise ValueError('Challenge player capacity reached')
        next_state = {**self.state, 'players': dict(self.state['players'])}
        updated = {'progress': player['progress'] + 1,
                   'seen': {**player['seen'], event_id: fingerprint}}
        next_state['players'][event.player_key] = updated
        self._commit(next_state)
        return public_progress(updated)
