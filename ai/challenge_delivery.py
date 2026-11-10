#!/usr/bin/env python3
"""Durable, opt-in account challenge transport. No native save or model access.

Completed records in retained rename-rotated logs are staged with their cursor
in one local transaction. Remote rewards and receipts commit together, and the
local outbox is acknowledged only after a valid remote response.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import stat
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

try:
    from challenge_native import ANSI, HEX, GUID, TOKEN, read_private, writer_lock
    from camo_challenge import KillEvent, REVISION, WEAPON_ID, CHALLENGE_ID, TARGET
except ModuleNotFoundError:
    from ai.challenge_native import ANSI, HEX, GUID, TOKEN, read_private, writer_lock
    from ai.camo_challenge import KillEvent, REVISION, WEAPON_ID, CHALLENGE_ID, TARGET

BIND = 'OUTLANDS_CHALLENGE_BIND_V1|'
KILL = 'OUTLANDS_CHALLENGE_KILL_V2|'
ACCOUNT_SESSION = re.compile(r'[A-Za-z0-9_-]{16,100}\Z')
REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
FIELDS = frozenset(('kind', 'grant', 'session', 'match', 'event_session', 'sequence',
                    'weapon', 'revision', 'human', 'enemy', 'headshot', 'confirmed'))
MAX_FILES = 4096
MAX_EVENTS = 1_000_000


class ContinuityError(ValueError):
    pass


def canonical(event):
    if (not isinstance(event, dict) or set(event) != FIELDS or event['kind'] != 'award'
            or not isinstance(event['grant'], str) or not HEX.fullmatch(event['grant'])
            or not isinstance(event['session'], str) or not ACCOUNT_SESSION.fullmatch(event['session'])):
        raise ValueError('Invalid staged challenge event')
    value = KillEvent('0'*64, event['event_session'], event['match'], event['sequence'],
                      event['weapon'], event['revision'], event['human'], event['enemy'],
                      event['headshot'], event['confirmed'])
    if not value.eligible():
        raise ValueError('Ineligible staged challenge event')
    return json.dumps(event, sort_keys=True, separators=(',', ':'))


@dataclass(frozen=True)
class Binding:
    request: str
    slot: int
    session: str
    identity: str


def parse_native(line, credential):
    if not isinstance(line, str) or len(line) > 1024:
        return None
    line = ANSI.sub('', line).rstrip('\r\n')
    if not line.startswith((BIND, KILL)):
        return None
    fields = line.split('|')[1:]
    if not fields or not HEX.fullmatch(fields[0]) or not hmac.compare_digest(fields[0], credential):
        return None
    if line.startswith(BIND):
        if len(fields) != 5:
            return None
        _, request, slot, session, identity = fields
        if (not REQUEST_ID.fullmatch(request) or not re.fullmatch(r'0|[1-9][0-9]?', slot)
                or int(slot) > 17 or not ACCOUNT_SESSION.fullmatch(session)
                or not GUID.fullmatch(identity) or not int(identity, 16)):
            return None
        return Binding(request, int(slot), session, identity)
    if len(fields) != 11:
        return None
    _, grant, session, match, event_session, sequence, weapon, human, enemy, headshot, confirmed = fields
    if not re.fullmatch(r'[1-9][0-9]{0,9}', sequence) or any(x != '1' for x in (human, enemy, headshot, confirmed)):
        return None
    event = {'kind': 'award', 'grant': grant, 'session': session, 'match': match,
             'event_session': event_session, 'sequence': int(sequence), 'weapon': weapon,
             'revision': REVISION, 'human': True, 'enemy': True, 'headshot': True, 'confirmed': True}
    try:
        canonical(event)
    except (TypeError, ValueError):
        return None
    return event


class DeliveryStore:
    """One worker owns the DB; separate tests may open it to simulate recovery."""
    def __init__(self, path, binding_digest):
        self.path = Path(path).absolute()
        if not isinstance(binding_digest, str) or not HEX.fullmatch(binding_digest):
            raise ValueError('Private destination binding required')
        if any(p.is_symlink() for p in (self.path, *self.path.parents)):
            raise ValueError('Delivery storage cannot contain links')
        info = self.path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Delivery directory must be owned and private')
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Delivery database must be owned and private')
        else:
            os.close(descriptor)
        with self.connection() as db:
            for ddl in (
                'CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                '''CREATE TABLE IF NOT EXISTS cursors (
                    id TEXT PRIMARY KEY, offset INTEGER NOT NULL, prefix_length INTEGER NOT NULL,
                    prefix TEXT NOT NULL, anchor TEXT NOT NULL, discard INTEGER NOT NULL, sealed INTEGER NOT NULL)''',
                '''CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT,
                    delivered INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0)''',
            ):
                db.execute(ddl)
            old = db.execute("SELECT value FROM metadata WHERE key='binding'").fetchone()
            if old and old['value'] != binding_digest:
                raise ValueError('Delivery destination changed; explicit backlog migration required')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('binding',?)", (binding_digest,))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=DELETE'); db.execute('PRAGMA synchronous=FULL')
        try:
            db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
        except Exception:
            db.rollback(); raise
        finally:
            db.close()

    def stage(self, db, event):
        raw = canonical(event)
        event_id = hashlib.sha256((event['grant']+':'+event['event_session']+':'+str(event['sequence'])).encode()).hexdigest()
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        previous = db.execute('SELECT fingerprint FROM outbox WHERE id=?', (event_id,)).fetchone()
        if previous:
            if previous['fingerprint'] != fingerprint:
                raise ContinuityError('Conflicting native reward replay')
            return
        if db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0] >= MAX_EVENTS:
            raise ContinuityError('Delivery capacity reached; source cursor retained')
        db.execute('INSERT INTO outbox(id,fingerprint,payload) VALUES (?,?,?)', (event_id, fingerprint, raw))

    def checkpoint(self, db, values):
        db.execute('INSERT OR REPLACE INTO cursors VALUES (?,?,?,?,?,?,?)', values)

    def pending(self, now, limit=16):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM outbox WHERE delivered=0 AND next_attempt<=? ORDER BY rowid LIMIT ?', (now, limit))]

    def acknowledge(self, event_id):
        with self.connection() as db:
            db.execute('UPDATE outbox SET delivered=1,payload=NULL WHERE id=?', (event_id,))

    def retry(self, event_id, now):
        with self.connection() as db:
            row = db.execute('SELECT attempts FROM outbox WHERE id=?', (event_id,)).fetchone()
            if row:
                attempts = min(30, row['attempts']+1)
                db.execute('UPDATE outbox SET attempts=?,next_attempt=? WHERE id=?',
                           (attempts, now + min(60, 2**min(6, attempts)), event_id))

    def summary(self):
        with self.connection() as db:
            return {'pending': db.execute('SELECT COUNT(*) FROM outbox WHERE delivered=0').fetchone()[0],
                    'acknowledged': db.execute('SELECT COUNT(*) FROM outbox WHERE delivered=1').fetchone()[0],
                    'files': db.execute('SELECT COUNT(*) FROM cursors').fetchone()[0]}


class ArchiveReader:
    """Rename/create rotation only. Removed unread logs and rewrites fail closed."""
    def __init__(self, log, store, credential):
        self.log = Path(log).absolute(); self.store = store; self.credential = credential

    def candidates(self):
        if any(p.is_symlink() for p in self.log.parents):
            raise ContinuityError('Native log directory contains links')
        archive = self.log.parent/'logs'
        if archive.is_symlink():
            raise ContinuityError('Native archive directory contains links')
        paths = sorted(archive.glob('console-*.log')) if archive.exists() else []
        paths += [self.log]
        if len(paths) > MAX_FILES:
            raise ContinuityError('Native log inventory exceeds its explicit bound')
        result = {}
        for path in paths:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ContinuityError('Native log must be an owned regular file')
            result[str(info.st_dev)+':'+str(info.st_ino)] = path
        return result

    def poll(self):
        paths = self.candidates()
        with self.store.connection() as db:
            if any(row['id'] not in paths and not row['sealed'] for row in db.execute('SELECT id,sealed FROM cursors')):
                raise ContinuityError('Previously unsealed native log is missing')
        bindings = []
        for identity, path in paths.items():
            bindings.extend(self.read_file(identity, path))
        return bindings

    def read_file(self, identity, path):
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor, 'rb') as stream, self.store.connection() as db:
            info = os.fstat(stream.fileno())
            if identity != str(info.st_dev)+':'+str(info.st_ino) or not stat.S_ISREG(info.st_mode):
                raise ContinuityError('Native log changed during inventory')
            row = db.execute('SELECT * FROM cursors WHERE id=?', (identity,)).fetchone()
            if row is None:
                if db.execute('SELECT COUNT(*) FROM cursors').fetchone()[0] >= MAX_FILES:
                    raise ContinuityError('Native cursor capacity reached')
                length = min(128, info.st_size)
                if length == 0:
                    return []
                prefix = hashlib.sha256(stream.read(length)).hexdigest()
                offset = 0; discard = False
            else:
                length, prefix, offset, discard = row['prefix_length'], row['prefix'], row['offset'], bool(row['discard'])
                if info.st_size < offset or hashlib.sha256(stream.read(length)).hexdigest() != prefix:
                    raise ContinuityError('Native log was truncated or rewritten')
                stream.seek(max(0, offset-64))
                if hashlib.sha256(stream.read(min(64, offset))).hexdigest() != row['anchor']:
                    raise ContinuityError('Native log checkpoint bytes changed')
            stream.seek(offset)
            bindings = []; read = 0
            archived = path != self.log
            while read < 65536:
                line = stream.readline(1025)
                if not line:
                    break
                if not line.endswith(b'\n'):
                    if len(line) < 1025:
                        if archived:
                            if BIND.encode() in line or KILL.encode() in line:
                                raise ContinuityError('Incomplete archived challenge record')
                            offset += len(line)
                        break
                    discard = True; offset += len(line); read += len(line); continue
                if not discard and len(line) <= 1024:
                    event = parse_native(line.decode('ascii', 'replace'), self.credential)
                    if isinstance(event, Binding):
                        bindings.append(event)
                    elif isinstance(event, dict):
                        self.store.stage(db, event)
                discard = False; offset += len(line); read += len(line)
            stream.seek(max(0, offset-64))
            anchor = hashlib.sha256(stream.read(min(64, offset))).hexdigest()
            sealed = int(archived and offset == info.st_size)
            self.store.checkpoint(db, (identity, offset, length, prefix, anchor, int(discard), sealed))
            return bindings


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class AccountTransport:
    def __init__(self, api, origin, credential):
        url, public = urlsplit(api), urlsplit(origin)
        if (url.username or url.password or url.query or url.fragment or url.path not in ('', '/')
                or url.scheme not in ('https', 'http') or not url.hostname
                or url.scheme == 'http' and url.hostname != '127.0.0.1'
                or public.scheme != 'https' or not public.hostname or public.username or public.password
                or public.query or public.fragment or public.path not in ('', '/')
                or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', credential)):
            raise ValueError('Reviewed account HTTPS or loopback transport required')
        self.url = api.rstrip('/')+'/internal/challenges'
        self.host = public.netloc; self.credential = credential
        self.opener = build_opener(NoRedirect(), ProxyHandler({}))

    def post(self, event):
        request = Request(self.url, data=json.dumps(event).encode(), headers={
            'Host': self.host, 'Authorization': 'Bearer '+self.credential, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(8193)
        except HTTPError as error:
            error.close()
            raise OSError('Account challenge request unavailable') from None
        if len(raw) > 8192:
            raise ValueError('Oversized challenge response')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Challenge response object required')
        return result


def deliver(store, transport, now):
    for row in store.pending(now):
        try:
            response = transport.post(json.loads(row['payload']))
            if not isinstance(response, dict) or not isinstance(response.get('progress'), dict):
                raise ValueError('Reward acknowledgment required')
            progress = response.get('progress', {})
            if (response.get('accepted') is not True or type(response.get('duplicate')) is not bool
                    or progress.get('challenge') != CHALLENGE_ID or progress.get('target') != TARGET
                    or type(progress.get('progress')) is not int or not 0 <= progress['progress'] <= TARGET):
                raise ValueError('Reward acknowledgment required')
        except (OSError, ValueError, TypeError):
            store.retry(row['id'], now)
        else:
            store.acknowledge(row['id'])


def grant_packet(binding, result, password):
    if not isinstance(result, dict):
        raise ValueError('Invalid fixed challenge grant response')
    grant, seconds = result.get('grant'), result.get('valid_seconds')
    if (not isinstance(binding, Binding) or not REQUEST_ID.fullmatch(binding.request)
            or type(binding.slot) is not int or not 0 <= binding.slot <= 17
            or not ACCOUNT_SESSION.fullmatch(binding.session)
            or not isinstance(grant, str) or not HEX.fullmatch(grant) or type(seconds) is not int
            or not 1 <= seconds <= 21600 or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', password)):
        raise ValueError('Invalid fixed challenge grant response')
    value = '|'.join((binding.request, str(binding.slot), binding.session, grant, str(seconds)))
    return b'\xff\xff\xff\xffrcon '+password.encode()+b' set outlands_challenge_grant "'+value.encode()+b'"'


def secret_text(path):
    path = Path(path)
    if any(p.is_symlink() for p in path.parents):
        raise ValueError('Private credential cannot contain links')
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(descriptor, 'r') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 128:
            raise ValueError('Owned private worker credential required')
        value = stream.read(129).strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value):
        raise ValueError('Invalid private worker credential')
    return value


def wait_secret(path, seconds=60):
    """Native entrypoint may create its private RCON secret after this worker."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            return secret_text(path)
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise ValueError('Required private worker credential did not become ready') from None
            time.sleep(.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--state', type=Path, default=Path('/challenges'))
    parser.add_argument('--log', type=Path, default=Path('/data/plutonium/console.log'))
    parser.add_argument('--credential', type=Path, default=Path('/data/private/challenge_token'))
    parser.add_argument('--server-credential', type=Path, default=Path('/run/outlands/server.credential'))
    parser.add_argument('--rcon-secret', type=Path, default=Path('/data/private/outlands_rcon_password'))
    parser.add_argument('--account-api', required=True)
    parser.add_argument('--account-origin', required=True)
    parser.add_argument('--port', type=int, default=4977)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('Invalid native loopback port')
    if not args.run:
        print('Plan: private durable outbox, confirmed account grants, fixed native grant mailbox; no native saves')
        return 0
    credential = secret_text(args.server_credential)
    transport = AccountTransport(args.account_api, args.account_origin, credential)
    binding_digest = hashlib.sha256((transport.url+'\0'+credential).encode()).hexdigest()
    with writer_lock(args.state):
        store = DeliveryStore(args.state/'delivery.sqlite3', binding_digest)
        reader = ArchiveReader(args.log, store, read_private(args.credential))
        password = wait_secret(args.rcon_secret)
        pending = {}; next_summary = 0
        print('Outlands account challenge follower ready; durable native events only', flush=True)
        while True:
            try:
                for request in reader.poll():
                    pending[request.slot] = request
            except (OSError, ValueError, sqlite3.Error):
                print('Challenge ingestion blocked; checkpoints and pending events retained', flush=True)
                time.sleep(1)
            if pending:
                slot = next(iter(pending)); request = pending.pop(slot)
                try:
                    result = transport.post({'kind': 'bind', 'session': request.session, 'profile_reference': request.identity})
                    packet = grant_packet(request, result, password)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.sendto(packet, ('127.0.0.1', args.port))
                except (OSError, ValueError, TypeError):
                    pass  # Native requests retry; no kills emit before a grant.
            deliver(store, transport, time.time())
            if time.monotonic() >= next_summary:
                print('Account challenge delivery: '+json.dumps(store.summary(), sort_keys=True), flush=True)
                next_summary = time.monotonic()+10
            time.sleep(.1)


if __name__ == '__main__': raise SystemExit(main())
