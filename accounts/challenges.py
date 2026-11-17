"""Opt-in account-owned challenge ledger, separate from native BO2 saves.

A server credential does not automatically gain reward access. The operator
enables it explicitly, and each grant requires the current browser-confirmed
native session. Issued grants bind delayed events to that immutable owner.
"""
import hashlib
import json
import re
import secrets

from accounts.store import Refused, BROWSER, FRESH_SECONDS, token
from ai.camo_challenge import CHALLENGE_ID, CAMO_ID, WEAPON_ID, REVISION, TARGET, KillEvent

GRANT_SECONDS = 6 * 3600
REPLAY_SECONDS = 7 * 86400
MAX_GRANTS = 65536
MAX_RECEIPTS = 1_000_000
HEX = re.compile(r'[0-9a-f]{64}\Z')
NATIVE_TOKEN = re.compile(r'[A-Za-z0-9_-]{1,48}\Z')
AWARD_FIELDS = frozenset(('kind', 'grant', 'session', 'match', 'event_session', 'sequence',
                          'weapon', 'revision', 'human', 'enemy', 'headshot', 'confirmed'))


def view(progress=0):
    return {'challenge': CHALLENGE_ID, 'weapon': WEAPON_ID, 'camo': CAMO_ID,
            'progress': progress, 'target': TARGET, 'completed': progress == TARGET,
            'reward_ready': False, 'scope': 'outlands_account', 'revision': REVISION}


class AccountChallenges:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            for ddl in (
                'CREATE TABLE IF NOT EXISTS reward_capabilities (server TEXT PRIMARY KEY REFERENCES servers(id), active INTEGER NOT NULL)',
                '''CREATE TABLE IF NOT EXISTS reward_grants (
                    digest TEXT PRIMARY KEY, nonce TEXT NOT NULL, server TEXT NOT NULL REFERENCES servers(id),
                    account TEXT NOT NULL REFERENCES accounts(id), session TEXT NOT NULL, profile TEXT NOT NULL,
                    created INTEGER NOT NULL, valid_until INTEGER NOT NULL, retained_until INTEGER NOT NULL)''',
                'CREATE INDEX IF NOT EXISTS reward_session ON reward_grants(server,session,created)',
                '''CREATE TABLE IF NOT EXISTS reward_progress (
                    account TEXT NOT NULL REFERENCES accounts(id), challenge TEXT NOT NULL,
                    progress INTEGER NOT NULL CHECK(progress>=0 AND progress<=25), PRIMARY KEY(account,challenge))''',
                '''CREATE TABLE IF NOT EXISTS reward_receipts (
                    id TEXT PRIMARY KEY, grant_digest TEXT NOT NULL REFERENCES reward_grants(digest) ON DELETE CASCADE,
                    fingerprint TEXT NOT NULL)''',
            ):
                db.execute(ddl)

    def enable_server(self, server_id, enabled=True):
        """Offline operator action; deliberately unavailable through HTTP."""
        if not token(server_id) or type(enabled) is not bool:
            raise Refused('Invalid challenge capability')
        with self.store.connection() as db:
            if not db.execute('SELECT 1 FROM servers WHERE id=?', (server_id,)).fetchone():
                raise Refused('Enrolled server required')
            db.execute('INSERT INTO reward_capabilities VALUES (?,?) ON CONFLICT(server) DO UPDATE SET active=excluded.active',
                       (server_id, int(enabled)))

    def server(self, db, credential):
        server = self.store.server(db, credential)
        row = db.execute('SELECT active FROM reward_capabilities WHERE server=?', (server,)).fetchone()
        if not row or row['active'] != 1:
            raise Refused('Challenge preview unavailable')
        return server

    def grant_token(self, row):
        return self.store.digest('reward-grant-token', row['server'] + ':' + row['nonce'])

    def bind(self, credential, event):
        if (set(event) != {'kind', 'session', 'profile_reference'} or event['kind'] != 'bind'
                or not token(event['session']) or not isinstance(event['profile_reference'], str)
                or not re.fullmatch(r'[0-9a-f]{1,32}', event['profile_reference']) or not int(event['profile_reference'], 16)):
            raise Refused('Invalid reward binding')
        now = self.store.now()
        with self.store.connection() as db:
            server = self.server(db, credential)
            row = db.execute('SELECT * FROM sessions WHERE server=? AND id=?', (server, event['session'])).fetchone()
            profile = self.store.digest('profile:' + server, event['profile_reference'])
            if (not row or row['closed'] or row['confirmed'] is None or row['profile'] != profile
                    or row['observed'] is None or not 0 <= now - row['observed'] <= FRESH_SECONDS):
                raise Refused('Fresh confirmed native session required')
            owner = db.execute('SELECT account FROM profiles WHERE server=? AND profile=?', (server, profile)).fetchone()
            if not owner or owner['account'] != row['confirmed']:
                raise Refused('Verified owner required')
            session = self.store.digest('reward-session:' + server, event['session'])
            grant = db.execute('SELECT * FROM reward_grants WHERE server=? AND session=? AND account=? AND profile=? ORDER BY created DESC LIMIT 1',
                               (server, session, row['confirmed'], profile)).fetchone()
            if grant and grant['valid_until'] > now + 10:
                return {'grant': self.grant_token(grant), 'valid_seconds': grant['valid_until'] - now}
            # Receipts cascade only after the explicit seven-day replay window.
            db.execute('DELETE FROM reward_grants WHERE retained_until<?', (now,))
            if db.execute('SELECT COUNT(*) FROM reward_grants').fetchone()[0] >= MAX_GRANTS:
                raise Refused('Reward grant capacity reached')
            nonce = secrets.token_hex(16)
            grant = {'server': server, 'nonce': nonce}
            credential_value = self.grant_token(grant)
            digest = self.store.digest('reward-grant-lookup', credential_value)
            db.execute('INSERT INTO reward_grants VALUES (?,?,?,?,?,?,?,?,?)',
                       (digest, nonce, server, row['confirmed'], session, profile, now,
                        now + GRANT_SECONDS, now + REPLAY_SECONDS))
            return {'grant': credential_value, 'valid_seconds': GRANT_SECONDS}

    def award(self, credential, event):
        if (set(event) != AWARD_FIELDS or event['kind'] != 'award'
                or not isinstance(event['grant'], str) or not HEX.fullmatch(event['grant'])
                or not token(event['session']) or not isinstance(event['event_session'], str)
                or not NATIVE_TOKEN.fullmatch(event['event_session'])):
            raise Refused('Invalid reward event')
        # One shared eligibility rule, with a synthetic internal key rather than
        # a browser-supplied account/player identifier.
        eligible = KillEvent('0' * 64, event['event_session'], event['match'], event['sequence'],
                             event['weapon'], event['revision'], event['human'], event['enemy'],
                             event['headshot'], event['confirmed'])
        if not eligible.eligible():
            raise Refused('Ineligible reward event')
        now = self.store.now()
        raw = json.dumps(event, sort_keys=True, separators=(',', ':'))
        fingerprint = hashlib.sha256(raw.encode('ascii')).hexdigest()
        with self.store.connection() as db:
            server = self.server(db, credential)
            digest = self.store.digest('reward-grant-lookup', event['grant'])
            grant = db.execute('SELECT * FROM reward_grants WHERE digest=? AND server=?', (digest, server)).fetchone()
            if (not grant or grant['retained_until'] < now
                    or grant['session'] != self.store.digest('reward-session:' + server, event['session'])):
                raise Refused('Reward grant unavailable')
            event_id = self.store.digest('reward-event:' + server,
                                         digest + ':' + event['event_session'] + ':' + str(event['sequence']))
            receipt = db.execute('SELECT fingerprint FROM reward_receipts WHERE id=?', (event_id,)).fetchone()
            if receipt and receipt['fingerprint'] != fingerprint:
                raise Refused('Conflicting reward replay')
            progress = db.execute('SELECT progress FROM reward_progress WHERE account=? AND challenge=?',
                                  (grant['account'], CHALLENGE_ID)).fetchone()
            count = progress['progress'] if progress else 0
            if receipt or count == TARGET:
                return {'accepted': True, 'duplicate': bool(receipt), 'progress': view(count)}
            if db.execute('SELECT COUNT(*) FROM reward_receipts').fetchone()[0] >= MAX_RECEIPTS:
                raise Refused('Reward receipt capacity reached')
            count += 1
            db.execute('INSERT INTO reward_receipts VALUES (?,?,?)', (event_id, digest, fingerprint))
            db.execute('INSERT INTO reward_progress VALUES (?,?,?) ON CONFLICT(account,challenge) DO UPDATE SET progress=excluded.progress',
                       (grant['account'], CHALLENGE_ID, count))
            return {'accepted': True, 'duplicate': False, 'progress': view(count)}

    def handle(self, credential, event):
        if not isinstance(event, dict):
            raise Refused('Invalid reward request')
        if event.get('kind') == 'bind':
            return self.bind(credential, event)
        if event.get('kind') == 'award':
            return self.award(credential, event)
        raise Refused('Invalid reward request')

    def dashboard(self, issuer, subject):
        with self.store.connection() as db:
            account = self.store.account(db, issuer, subject)
            row = db.execute('SELECT progress FROM reward_progress WHERE account=? AND challenge=?',
                             (account['id'], CHALLENGE_ID)).fetchone()
            return [view(row['progress'] if row else 0)]
