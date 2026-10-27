"""Private Outlands identity/link/snapshot core; intentionally no HTTP routes.

Only an authentication adapter may supply a verified issuer/subject. Only an
operator-enrolled game worker may create sessions/challenges or submit native
observations. A LAN name/GUID alone never authorizes a personal dashboard.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import time
import uuid

SCHEMA = 1
FRESH_SECONDS = 30
PAIR_SECONDS = 180
SESSION_SECONDS = 1800
MAX_SESSIONS = 18
MAX_PENDING = 1152
MAX_PROFILES_PER_ACCOUNT = 32
MAX_ACCOUNTS = 4096
MAX_SERVERS = 64
MAX_RETAINED_SESSIONS = 8192
TOKEN = re.compile(r'[A-Za-z0-9_-]{16,128}\Z')
PROVIDERS = frozenset({'https://accounts.google.com'})
BROWSER = 'outlands-browser-session'
BROWSER_SECONDS = 7*86400
STATS = {'rank_xp': (0, 2_147_483_647), 'rank_level': (1, 55), 'prestige': (0, 11),
         'kills': (0, 1_000_000_000), 'deaths': (0, 1_000_000_000),
         'wins': (0, 1_000_000_000), 'losses': (0, 1_000_000_000)}


class Refused(ValueError):
    """A deliberately generic failure; do not reveal account/profile ownership."""


def token(value):
    return isinstance(value, str) and bool(TOKEN.fullmatch(value))


def label(value):
    return (isinstance(value, str) and value == value.strip()
            and bool(re.fullmatch(r'[A-Za-z0-9 _.~-]{1,24}', value)))


def bounded_stats(value):
    if not isinstance(value, dict) or not value or set(value)-STATS.keys():
        raise Refused('Invalid stat snapshot')
    for key, number in value.items():
        low, high = STATS[key]
        if type(number) is not int or not low <= number <= high:
            raise Refused('Invalid stat snapshot')
    # Explicit, bounded fields only. No files, names, chat, arbitrary native DDL
    # paths, client-submitted unlocks, scripts or merge instructions.
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class AccountStore:
    """Transactional local core for a future authenticated account service.

    Every browser operation takes the principal obtained from trusted auth, not
    an account ID supplied in JSON. Each game connection requires an expiring,
    one-use in-game challenge even when the LAN profile was linked previously.
    SQLite is for this single-host implementation; it is not a scale claim.
    """
    def __init__(self, path: Path, key: bytes, clock=time.time):
        self.path = Path(path).absolute()
        self.clock = clock
        if not isinstance(key, bytes) or len(key) != 32:
            raise Refused('A private stable 32-byte identity key is required')
        self.key = key
        for part in (self.path, *self.path.parents):
            if part.is_symlink():
                raise Refused('Linked account storage cannot use symlinks')
        parent = self.path.parent.stat()
        if not stat.S_ISDIR(parent.st_mode):
            raise Refused('Invalid private account directory')
        if os.name != 'nt' and (parent.st_uid != os.getuid() or parent.st_mode & 0o077):
            raise Refused('Account directory must be owned and mode 700')
        if self.path.exists():
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode) or (os.name != 'nt' and (info.st_uid != os.getuid() or info.st_mode & 0o077)):
                raise Refused('Account database must be an owned private file')
        else:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            os.close(descriptor)
        with self.connection() as db:
            current = db.execute('PRAGMA user_version').fetchone()[0]
            if current not in (0, SCHEMA):
                raise Refused('Unsupported account database schema')
            db.executescript('BEGIN IMMEDIATE;\n'+'''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY, principal TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS servers (
                    id TEXT PRIMARY KEY, credential TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS profiles (
                    server TEXT NOT NULL REFERENCES servers(id), profile TEXT NOT NULL,
                    account TEXT NOT NULL REFERENCES accounts(id), snapshot TEXT, observed INTEGER,
                    session TEXT, PRIMARY KEY(server,profile));
                CREATE TABLE IF NOT EXISTS sessions (
                    server TEXT NOT NULL REFERENCES servers(id), id TEXT NOT NULL,
                    profile TEXT NOT NULL, started INTEGER NOT NULL, touched INTEGER NOT NULL,
                    sequence INTEGER NOT NULL DEFAULT 0, snapshot TEXT, observed INTEGER,
                    confirmed TEXT REFERENCES accounts(id), closed INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(server,id));
                CREATE UNIQUE INDEX IF NOT EXISTS one_live_profile
                    ON sessions(server,profile) WHERE closed=0;
                CREATE TABLE IF NOT EXISTS challenges (
                    digest TEXT PRIMARY KEY, server TEXT NOT NULL, session TEXT NOT NULL,
                    expires INTEGER NOT NULL, FOREIGN KEY(server,session) REFERENCES sessions(server,id));
                CREATE UNIQUE INDEX IF NOT EXISTS one_challenge_per_session ON challenges(server,session);
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    digest TEXT PRIMARY KEY,account TEXT NOT NULL REFERENCES accounts(id),expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (principal TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL);
            ''')
            fingerprint = self.digest('key-check', 'outlands-account-schema-1')
            old = db.execute("SELECT value FROM metadata WHERE key='key-check'").fetchone()
            if old and not hmac.compare_digest(old[0], fingerprint):
                raise Refused('Account identity key does not match database')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('key-check',?)", (fingerprint,))
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA synchronous=FULL')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def now(self):
        value = self.clock()
        if type(value) not in (float, int) or not 0 <= value <= 4_102_444_800:
            raise Refused('Invalid service time')
        return int(value)

    def digest(self, domain, value):
        if not isinstance(value, str) or not value or len(value) > 512:
            raise Refused('Invalid identifier')
        return hmac.new(self.key, (domain+'\0'+value).encode(), hashlib.sha256).hexdigest()

    def principal(self, issuer, subject):
        # Provider names are a design allowlist, not an OAuth implementation.
        # Caller must verify signature, issuer, audience, expiry and auth state.
        if issuer not in PROVIDERS or not isinstance(subject, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', subject):
            raise Refused('Verified sign-in is required')
        return self.digest('principal', issuer+'\0'+subject)

    def provision(self, issuer, subject, display_name):
        principal = self.principal(issuer, subject)
        if not label(display_name):
            raise Refused('Invalid display name')
        with self.connection() as db:
            row = db.execute('SELECT id,display_name,revision FROM accounts WHERE principal=?', (principal,)).fetchone()
            if row:
                return dict(row)
            if db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0] >= MAX_ACCOUNTS:
                raise Refused('Account capacity reached')
            account = uuid.uuid4().hex
            db.execute('INSERT INTO accounts(id,principal,display_name) VALUES (?,?,?)', (account, principal, display_name))
            return {'id':account, 'display_name':display_name, 'revision':1}

    def account(self, db, issuer, subject):
        if issuer == BROWSER:
            if not token(subject):
                raise Refused('Sign-in required')
            row = db.execute('SELECT a.* FROM accounts a JOIN browser_sessions b ON b.account=a.id WHERE b.digest=? AND b.expires>?', (self.digest('browser',subject), self.now())).fetchone()
            if not row:
                raise Refused('Sign-in required')
            return row
        row = db.execute('SELECT * FROM accounts WHERE principal=?', (self.principal(issuer, subject),)).fetchone()
        if not row:
            raise Refused('Verified sign-in is required')
        return row

    def start_browser_session(self, issuer, subject):
        if issuer not in PROVIDERS:
            raise Refused('Verified Google sign-in required')
        now = self.now()
        credential = secrets.token_urlsafe(32)
        with self.connection() as db:
            account = self.account(db, issuer, subject)
            db.execute('DELETE FROM browser_sessions WHERE expires<=?', (now,))
            # Limit each account to ten devices/browser sessions.
            rows = db.execute('SELECT digest FROM browser_sessions WHERE account=? ORDER BY expires DESC', (account['id'],)).fetchall()
            for row in rows[9:]:
                db.execute('DELETE FROM browser_sessions WHERE digest=?', (row['digest'],))
            db.execute('INSERT INTO browser_sessions VALUES (?,?,?)', (self.digest('browser',credential),account['id'],now+BROWSER_SECONDS))
        return credential

    def logout(self, credential):
        if not token(credential):
            return
        with self.connection() as db:
            db.execute('DELETE FROM browser_sessions WHERE digest=?',(self.digest('browser',credential),))

    def rename(self, issuer, subject, display_name, expected_revision):
        if not label(display_name) or type(expected_revision) is not int:
            raise Refused('Invalid profile change')
        with self.connection() as db:
            account = self.account(db, issuer, subject)
            changed = db.execute('UPDATE accounts SET display_name=?,revision=revision+1 WHERE id=? AND revision=?',
                                 (display_name, account['id'], expected_revision)).rowcount
            if changed != 1:
                raise Refused('Profile changed; refresh before saving')
            return {'id':account['id'], 'display_name':display_name, 'revision':expected_revision+1}

    def enroll_server(self, server_id, persist=None):
        # Operator-only bootstrap. No public/admin HTTP route is implemented.
        if not token(server_id):
            raise Refused('Invalid server enrollment')
        credential = secrets.token_urlsafe(32)
        with self.connection() as db:
            if db.execute('SELECT 1 FROM servers WHERE id=?', (server_id,)).fetchone():
                raise Refused('Server already enrolled')
            if db.execute('SELECT COUNT(*) FROM servers').fetchone()[0] >= MAX_SERVERS:
                raise Refused('Server capacity reached')
            db.execute('INSERT INTO servers(id,credential) VALUES (?,?)', (server_id, self.digest('server-credential', credential)))
            if persist is not None:
                persist(credential) # offline private-file bootstrap; failure rolls back enrollment
        return credential

    def server(self, db, credential):
        if not token(credential):
            raise Refused('Game worker authentication required')
        row = db.execute('SELECT id FROM servers WHERE credential=? AND active=1', (self.digest('server-credential', credential),)).fetchone()
        if not row:
            raise Refused('Game worker authentication required')
        return row['id']

    def prune(self, db, now):
        # Keep closed IDs through a bounded replay window; a nonce cannot be
        # reopened during that window. New process/map sessions use new nonces.
        db.execute('DELETE FROM challenges WHERE expires<=?', (now,))
        db.execute('DELETE FROM challenges WHERE (server,session) IN (SELECT server,id FROM sessions WHERE touched<? OR closed=1)', (now-SESSION_SECONDS,))
        db.execute('UPDATE sessions SET closed=1,confirmed=NULL WHERE touched<?', (now-SESSION_SECONDS,))
        db.execute('DELETE FROM sessions WHERE closed=1 AND touched<?', (now-86400,))
        db.execute('DELETE FROM attempts WHERE window<?', (now-600,))
        db.execute('DELETE FROM browser_sessions WHERE expires<=?', (now,))

    def open_session(self, credential, session_id, profile_reference):
        if not token(session_id) or not isinstance(profile_reference, str) or not re.fullmatch(r'[0-9a-fA-F]{1,32}', profile_reference) or not int(profile_reference,16):
            raise Refused('Invalid native session')
        now = self.now()
        with self.connection() as db:
            server = self.server(db, credential)
            self.prune(db, now)
            if db.execute('SELECT 1 FROM sessions WHERE server=? AND id=?', (server, session_id)).fetchone():
                raise Refused('Session already exists')
            if db.execute('SELECT COUNT(*) FROM sessions WHERE server=?',(server,)).fetchone()[0] >= MAX_RETAINED_SESSIONS:
                raise Refused('Retained session capacity reached')
            profile = self.digest('profile:'+server, profile_reference.lower())
            # A fresh native connection invalidates prior delivery/approval for
            # that profile. It does not inherit the old browser authorization.
            db.execute('DELETE FROM challenges WHERE server=? AND session IN (SELECT id FROM sessions WHERE server=? AND profile=?)', (server,server,profile))
            db.execute('UPDATE sessions SET closed=1,confirmed=NULL WHERE server=? AND profile=? AND closed=0', (server,profile))
            active = db.execute('SELECT COUNT(*) FROM sessions WHERE server=? AND closed=0',(server,)).fetchone()[0]
            if active >= MAX_SESSIONS:
                raise Refused('Server session capacity reached')
            db.execute('INSERT INTO sessions(server,id,profile,started,touched) VALUES (?,?,?,?,?)', (server,session_id,profile,now,now))

    def challenge(self, credential, session_id):
        if not token(session_id):
            raise Refused('Current native session required')
        now = self.now()
        with self.connection() as db:
            server = self.server(db, credential)
            self.prune(db, now)
            row = db.execute('SELECT 1 FROM sessions WHERE server=? AND id=? AND closed=0', (server,session_id)).fetchone()
            if not row:
                raise Refused('Current native session required')
            pending = db.execute('SELECT COUNT(*) FROM challenges').fetchone()[0]
            if pending >= MAX_PENDING:
                raise Refused('Pairing capacity reached')
            code = secrets.token_hex(16).upper()
            db.execute('DELETE FROM challenges WHERE server=? AND session=?', (server,session_id))
            db.execute('INSERT INTO challenges VALUES (?,?,?,?)', (self.digest('pair', code), server,session_id,now+PAIR_SECONDS))
            # Transport must show this only to the exact native session that
            # requested it. Never public chat, console logs, URLs or the model.
            return {'code':code, 'expires_in':PAIR_SECONDS}

    def confirm(self, issuer, subject, code):
        if not isinstance(code, str) or not re.fullmatch(r'[0-9A-Fa-f]{32}', code):
            raise Refused('Invalid or expired pairing')
        now = self.now()
        failure = False
        with self.connection() as db:
            account = self.account(db, issuer, subject)
            self.prune(db, now)
            attempt = db.execute('SELECT window,count FROM attempts WHERE principal=?', (account['principal'],)).fetchone()
            count = attempt['count'] if attempt and now-attempt['window'] < 60 else 0
            if count >= 5:
                raise Refused('Pairing attempts exceeded; wait before retrying')
            window = attempt['window'] if count else now
            db.execute('INSERT INTO attempts VALUES (?,?,?) ON CONFLICT(principal) DO UPDATE SET window=excluded.window,count=excluded.count', (account['principal'],window,count+1))
            pair = db.execute('SELECT c.*,s.profile,s.closed,s.touched,s.snapshot,s.observed FROM challenges c JOIN sessions s ON s.server=c.server AND s.id=c.session WHERE c.digest=?', (self.digest('pair',code.upper()),)).fetchone()
            if not pair or pair['expires'] <= now or pair['closed'] or now-pair['touched'] >= SESSION_SECONDS:
                failure = True
            else:
                owner = db.execute('SELECT account FROM profiles WHERE server=? AND profile=?', (pair['server'],pair['profile'])).fetchone()
                if owner and owner['account'] != account['id']:
                    failure = True
                elif not owner and db.execute('SELECT COUNT(*) FROM profiles WHERE account=?',(account['id'],)).fetchone()[0] >= MAX_PROFILES_PER_ACCOUNT:
                    failure = True
                else:
                    db.execute('INSERT OR IGNORE INTO profiles(server,profile,account) VALUES (?,?,?)', (pair['server'],pair['profile'],account['id']))
                    db.execute('UPDATE sessions SET confirmed=? WHERE server=? AND id=?', (account['id'],pair['server'],pair['session']))
                    db.execute('UPDATE profiles SET snapshot=?,observed=?,session=? WHERE server=? AND profile=?', (pair['snapshot'],pair['observed'],pair['session'],pair['server'],pair['profile']))
                    db.execute('DELETE FROM challenges WHERE digest=?', (pair['digest'],))
        # A failed attempt still commits its rate-limit counter. No relink,
        # stealing, automatic identity transfer or profile merging happens.
        if failure:
            raise Refused('Invalid or expired pairing')
        return {'linked':True}

    def ingest(self, credential, session_id, sequence, values):
        raw = bounded_stats(values)
        if not token(session_id) or type(sequence) is not int or not 1 <= sequence <= 2_147_483_647:
            raise Refused('Invalid snapshot sequence')
        now = self.now()
        with self.connection() as db:
            server = self.server(db, credential)
            self.prune(db, now)
            previous = db.execute('SELECT * FROM sessions WHERE server=? AND id=? AND closed=0', (server,session_id)).fetchone()
            if not previous:
                raise Refused('Current native session required')
            if sequence <= previous['sequence']:
                if sequence == previous['sequence'] and raw == previous['snapshot']:
                    return {'accepted':True,'duplicate':True}
                raise Refused('Out-of-order snapshot')
            # Observe absolute values. Prestige/reset can reduce native stats;
            # never sum PC profiles or take maxima to invent native progression.
            db.execute('UPDATE sessions SET sequence=?,snapshot=?,observed=?,touched=? WHERE server=? AND id=?', (sequence,raw,now,now,server,session_id))
            if previous['confirmed'] is not None:
                db.execute('UPDATE profiles SET snapshot=?,observed=?,session=? WHERE server=? AND profile=? AND account=?', (raw,now,session_id,server,previous['profile'],previous['confirmed']))
            return {'accepted':True,'duplicate':False}

    def close_session(self, credential, session_id):
        if not token(session_id):
            raise Refused('Invalid native session')
        with self.connection() as db:
            server = self.server(db, credential)
            db.execute('DELETE FROM challenges WHERE server=? AND session=?', (server,session_id))
            db.execute('UPDATE sessions SET closed=1,confirmed=NULL WHERE server=? AND id=?', (server,session_id))

    def dashboard(self, issuer, subject):
        now = self.now()
        with self.connection() as db:
            account = self.account(db, issuer, subject)
            self.prune(db, now)
            rows = db.execute('''SELECT p.server,p.snapshot,p.observed,p.profile,s.closed,s.confirmed
                FROM profiles p LEFT JOIN sessions s ON s.server=p.server AND s.id=p.session
                WHERE p.account=? ORDER BY p.server,p.profile''', (account['id'],)).fetchall()
            profiles = []
            for row in rows:
                age = None if row['observed'] is None else now-row['observed']
                live = row['closed'] == 0 and row['confirmed'] == account['id'] and age is not None and 0 <= age <= FRESH_SECONDS
                profiles.append({'profile_id':self.digest('profile-view',account['id']+':'+row['server']+':'+row['profile']),
                                 'server':row['server'], 'live':live, 'observed_at':row['observed'],
                                 'stats':json.loads(row['snapshot']) if row['snapshot'] and age is not None and age >= 0 else None,
                                 'source':'server_observed_native', 'scope':'this_profile_on_this_server'})
            return {'id':account['id'],'display_name':account['display_name'],'revision':account['revision'],
                    'profiles':profiles, 'native_save_sync':False}

    def native_event(self, credential, event):
        """Only an enrolled worker calls this; never accept browser stat input."""
        if not isinstance(event,dict) or set(event)!={'session','sequence','kind','profile_reference','stats'} or event['kind'] not in ('hello','snapshot','link','depart') or not token(event['session']):
            raise Refused('Invalid native observation')
        reference=event['profile_reference']
        if not isinstance(reference,str) or not re.fullmatch(r'[0-9a-fA-F]{1,32}',reference) or not int(reference,16):
            raise Refused('Invalid native observation')
        if type(event['sequence']) is not int or not 1<=event['sequence']<=2_147_483_647:
            raise Refused('Invalid native observation')
        if event['stats']:bounded_stats(event['stats'])
        elif event['stats']!={}:raise Refused('Invalid native observation')
        # Re-handshake a restarted follower without resurrecting a closed nonce.
        with self.connection() as db:
            server=self.server(db,credential)
            existing=db.execute('SELECT profile,closed FROM sessions WHERE server=? AND id=?',(server,event['session'])).fetchone()
            if existing and (existing['closed'] or existing['profile']!=self.digest('profile:'+server,reference.lower())):
                raise Refused('Current native session required')
        if not existing:self.open_session(credential,event['session'],reference)
        if event['kind']=='depart':
            self.close_session(credential,event['session']);return {'accepted':True}
        if event['stats']:self.ingest(credential,event['session'],event['sequence'],event['stats'])
        if event['kind']=='link':return self.challenge(credential,event['session'])
        return {'accepted':True}
