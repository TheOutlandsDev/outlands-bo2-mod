"""Weighted map decks, native next-map transport and private restart history.

Only catalogued, nonempty main fastfiles are eligible. Presence is not a
full install or client ownership check. No game assets or player data are read.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import random
import re
import socket
import stat
import tempfile

MODES = frozenset(('dom', 'tdm', 'conf', 'koth', 'ctf', 'dem', 'hq', 'dm'))
MAP = re.compile(r'mp_[a-z0-9_]{1,40}\Z')
START = re.compile(r'OUTLANDS_ROTATION_V1\|([a-zA-Z0-9_]{1,60})\|(mp_[a-z0-9_]{1,40})\|([a-z]{2,4})\Z')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def number(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def load_catalog(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
        raise ValueError('Invalid rotation catalog')
    data = json.loads(path.read_text())
    if set(data) != {'schema_version', 'recent_maps', 'recent_modes', 'maps', 'modes'} or data['schema_version'] != 1:
        raise ValueError('Invalid rotation schema')
    if not number(data['recent_maps'], 0, 30) or not number(data['recent_modes'], 0, 7):
        raise ValueError('Invalid rotation recent window')
    if not isinstance(data['maps'], dict) or not 1 <= len(data['maps']) <= 31 or not isinstance(data['modes'], dict) or not data['modes'] or set(data['modes']) - MODES:
        raise ValueError('Invalid rotation pool')
    for key, row in data['maps'].items():
        if not MAP.fullmatch(key) or not isinstance(row, dict) or set(row) != {'name', 'pack', 'weight'} or not number(row['weight'], 0, 8) or not isinstance(row['name'], str) or len(row['name']) > 40 or not re.fullmatch(r'[a-z_]{1,24}', row['pack']):
            raise ValueError('Invalid map weight')
    if any(not number(weight, 0, 8) for weight in data['modes'].values()):
        raise ValueError('Invalid mode weight')
    if not any(data['modes'].values()):
        raise ValueError('All modes disabled')
    return data


def installed_maps(catalog, game):
    def present(path):
        return not path.is_symlink() and path.is_file() and path.stat().st_size > 0
    return {key: row['weight'] for key, row in catalog['maps'].items()
            if row['weight'] and present(Path(game) / 'zone/all' / (key + '.ff'))}


def rotation_entry(map_name, mode):
    if not MAP.fullmatch(map_name) or mode not in MODES:
        raise ValueError('Invalid next map')
    return f'gametype {mode} execgts outlands_{mode}.cfg map {map_name}'


def draw(weights, remaining, history, window, rng):
    """Draw a weighted ticket without replacement; relax only if exhausted.

    Every enabled map has tickets in each complete deck. A five-map hard recent
    window applies whenever a remaining ticket permits it. At a constrained deck
    boundary the oldest exclusion relaxes first, retaining no immediate repeat
    whenever at least two maps are enabled. Unused tickets are never discarded.
    """
    if not weights:
        raise ValueError('No eligible rotation maps')
    remaining = {key: min(remaining.get(key, 0), weight) for key, weight in weights.items()}
    if not any(remaining.values()):
        remaining = dict(weights)
    limit = min(window, max(0, len(weights) - 1))
    if len(weights) > 1 and history:
        limit = max(1, limit)
    while True:
        excluded = set(history[-limit:]) if limit else set()
        choices = [key for key in weights if remaining[key] and key not in excluded]
        if choices:
            break
        # Preserve immediate-repeat protection even when the only remaining
        # ticket is the previous map. Refill just that exhausted deck boundary;
        # its residual ticket remains and is consumed on a later legal draw.
        if limit <= 1:
            choices = [key for key in weights if not history or key != history[-1]] or list(weights)
            for key in choices:
                remaining[key] = max(remaining[key], weights[key])
            break
        limit -= 1
    tickets = [key for key in choices for _ in range(remaining[key])]
    return rng.choice(tickets), remaining, limit


class Rotation:
    """One game process owns this state under the host's existing volume lock."""
    def __init__(self, catalog, game, state, secret='', port=4977, rng=None, send=None):
        self.catalog = load_catalog(catalog)
        self.maps = installed_maps(self.catalog, game)
        self.modes = {key: value for key, value in self.catalog['modes'].items() if value}
        if not self.maps:
            raise ValueError('No installed maps in weighted rotation')
        self.path = Path(state)
        self.secret, self.port = secret, port
        self.rng = rng or random.SystemRandom()
        self.send = send or self.send_native
        self.events = set()
        self.data = self.read()
        self.plan()

    def read(self):
        empty = {'schema_version': 1, 'map_history': [], 'mode_history': [],
                 'map_deck': {}, 'mode_deck': {}, 'pending': None}
        if not self.path.exists() and not self.path.is_symlink():
            return empty
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 32768:
            raise ValueError('Invalid private rotation state')
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or set(data) != set(empty) or data['schema_version'] != 1:
            raise ValueError('Invalid rotation state schema')
        for kind, pool in (('map', self.catalog['maps']), ('mode', MODES)):
            history, deck = data[kind + '_history'], data[kind + '_deck']
            if not isinstance(history, list) or len(history) > 64 or any(x not in pool for x in history):
                raise ValueError('Invalid rotation history')
            if not isinstance(deck, dict) or any(k not in pool or not number(v, 0, 8) for k, v in deck.items()):
                raise ValueError('Invalid rotation deck')
        pending = data['pending']
        if pending is not None and (not isinstance(pending, list) or len(pending) != 2 or pending[0] not in self.catalog['maps'] or pending[1] not in MODES):
            raise ValueError('Invalid pending rotation')
        return data

    def save(self):
        parent = self.path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Rotation state parent must be private')
        if self.path.is_symlink():
            raise ValueError('Refusing linked rotation state')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=parent, delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                stream.write((json.dumps(self.data, sort_keys=True) + '\n').encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def plan(self):
        pending = self.data['pending']
        if pending and pending[0] in self.maps and pending[1] in self.modes:
            return pending
        values = []
        for kind, pool, window in (('map', self.maps, self.catalog['recent_maps']),
                                   ('mode', self.modes, self.catalog['recent_modes'])):
            value, deck, _ = draw(pool, self.data[kind + '_deck'], self.data[kind + '_history'], window, self.rng)
            self.data[kind + '_deck'] = deck
            values.append(value)
        self.data['pending'] = values
        self.save()
        return values

    def observe(self, line):
        match = START.fullmatch(ANSI.sub('', line).strip())
        if not match or match[2] not in self.maps or match[3] not in self.modes:
            return False
        nonce, map_name, mode = match.groups()
        event = hashlib.sha256(nonce.encode()).hexdigest()
        if event not in self.events:
            if len(self.events) >= 128:
                self.events.clear()
            self.events.add(event)
            # Halftime/reload notifications for the same map/mode do not spend
            # another ticket. A genuine change is recorded before next-map ACK.
            previous = list(zip(self.data['map_history'], self.data['mode_history']))
            if not previous or previous[-1] != (map_name, mode):
                for kind, value in (('map', map_name), ('mode', mode)):
                    self.data[kind + '_history'] = (self.data[kind + '_history'] + [value])[-64:]
                    deck = self.data[kind + '_deck']
                    deck[value] = max(0, deck.get(value, 0) - 1)
                self.data['pending'] = None
                self.plan()
        selected = self.plan()
        # A single fixed mailbox avoids two-packet RCON rate-limit/order races.
        # Native code validates the nonce and installed allowlists, then writes
        # the normal next-rotation dvar and emits its own readback receipt.
        self.send('set outlands_rotation_plan "' + nonce + '|' + '|'.join(selected) + '"')
        return True

    def send_native(self, command):
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', self.secret) or not number(self.port, 1024, 65535):
            raise ValueError('Invalid local rotation transport')
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.settimeout(0.2)
            connection.sendto(b'\xff\xff\xff\xffrcon ' + self.secret.encode('ascii') + b' ' + command.encode('ascii') + b'\n', ('127.0.0.1', self.port))
