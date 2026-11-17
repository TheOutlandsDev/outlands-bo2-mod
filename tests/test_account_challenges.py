"""Synthetic confirmed identities only; no real OAuth or game client evidence."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from accounts.store import AccountStore, Refused
from accounts.challenges import AccountChallenges, REPLAY_SECONDS
from ai.camo_challenge import TARGET, WEAPON_ID, REVISION

ISSUER = 'https://accounts.google.com'
SERVER = 'synthetic_server_001'
SESSION = 'synthetic_session_001'


class AccountChallengeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name); self.directory.chmod(0o700)
        self.now = [10000]
        self.store = AccountStore(self.directory/'accounts.sqlite3', b'k'*32, lambda: self.now[0])
        self.store.provision(ISSUER, 'subject_1', 'PlayerOne')
        self.store.provision(ISSUER, 'subject_2', 'PlayerTwo')
        self.credential = self.store.enroll_server(SERVER)
        self.core = AccountChallenges(self.store)

    def link(self, credential=None, session=SESSION, guid='abc123', subject='subject_1'):
        credential = credential or self.credential
        self.store.open_session(credential, session, guid)
        self.store.ingest(credential, session, 1, {'rank_xp': 100, 'rank_level': 1})
        code = self.store.challenge(credential, session)['code']
        self.store.confirm(ISSUER, subject, code)
        return {'kind': 'bind', 'session': session, 'profile_reference': guid}

    def grant(self, **options):
        self.core.enable_server(SERVER)
        binding = self.link(**options)
        return self.core.bind(self.credential, binding)['grant']

    def event(self, grant, sequence=1, **changes):
        event = {'kind': 'award', 'grant': grant, 'session': SESSION, 'match': 'match_1',
                 'event_session': 'challenge_session_1', 'sequence': sequence,
                 'weapon': WEAPON_ID, 'revision': REVISION, 'human': True,
                 'enemy': True, 'headshot': True, 'confirmed': True}
        event.update(changes)
        return event

    def count(self, subject='subject_1'):
        return self.core.dashboard(ISSUER, subject)[0]['progress']

    def test_capability_and_fresh_confirmed_session_are_required(self):
        binding = self.link()
        with self.assertRaises(Refused): self.core.bind(self.credential, binding)
        self.core.enable_server(SERVER)
        for changes in ({'profile_reference': 'def456'}, {'session': 'unknown_session_001'}, {'account': 'injected_owner'}):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                self.core.bind(self.credential, binding | changes)
        original = self.core.bind(self.credential, binding)
        self.assertEqual(self.core.bind(self.credential, binding), original)
        self.now[0] += 31
        with self.assertRaises(Refused): self.core.bind(self.credential, binding)
        self.store.open_session(self.credential, 'new_session_same_guid', 'abc123')
        self.store.ingest(self.credential, 'new_session_same_guid', 1, {'rank_xp': 100})
        with self.assertRaises(Refused):
            self.core.bind(self.credential, binding | {'session': 'new_session_same_guid'})

    def test_same_account_earns_across_pcs_and_servers_without_native_save_merge(self):
        first = self.grant()
        self.core.award(self.credential, self.event(first))
        binding = self.link(session='synthetic_windows_pc2', guid='def456')
        second = self.core.bind(self.credential, binding)['grant']
        self.core.award(self.credential, self.event(second, session=binding['session']))
        other_credential = self.store.enroll_server('synthetic_server_002')
        self.core.enable_server('synthetic_server_002')
        binding = self.link(credential=other_credential, session='synthetic_linux_pc3', guid='fed987')
        third = self.core.bind(other_credential, binding)['grant']
        self.core.award(other_credential, self.event(third, session=binding['session']))
        self.assertEqual(self.count(), 3)
        self.assertEqual(self.count('subject_2'), 0)
        profiles = self.store.dashboard(ISSUER, 'subject_1')['profiles']
        self.assertEqual(len(profiles), 3)
        self.assertTrue(all(p['stats']['rank_xp'] == 100 for p in profiles))
        reopened = AccountChallenges(AccountStore(self.directory/'accounts.sqlite3', b'k'*32, lambda:self.now[0]))
        self.assertEqual(reopened.dashboard(ISSUER, 'subject_1')[0]['progress'], 3)

    def test_delayed_closed_session_event_keeps_original_owner_and_cannot_rebind(self):
        grant = self.grant()
        self.store.close_session(self.credential, SESSION)
        binding = self.link(session='other_player_session', guid='def456', subject='subject_2')
        other = self.core.bind(self.credential, binding)['grant']
        self.core.award(self.credential, self.event(grant))
        self.assertEqual((self.count(), self.count('subject_2')), (1, 0))
        with self.assertRaises(Refused): self.core.award(self.credential, self.event(grant, session=binding['session']))
        self.core.award(self.credential, self.event(other, session=binding['session']))
        self.assertEqual((self.count(), self.count('subject_2')), (1, 1))

    def test_replays_parallel_requests_and_wrong_server_do_not_double_award(self):
        grant = self.grant(); event = self.event(grant)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.core.award(self.credential, event), range(8)))
        self.assertEqual(self.count(), 1)
        self.assertEqual(sum(not row['duplicate'] for row in results), 1)
        for changes in ({'match': 'other_match'}, {'headshot': False}, {'weapon': 'mp7_mp'}, {'sequence': True}):
            with self.subTest(changes=changes), self.assertRaises(Refused):
                self.core.award(self.credential, event | changes)
        foreign = self.store.enroll_server('foreign_server_001'); self.core.enable_server('foreign_server_001')
        with self.assertRaises(Refused): self.core.award(foreign, event)
        self.assertEqual(self.count(), 1)

    def test_receipt_and_progress_roll_back_together(self):
        grant = self.grant()
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON reward_progress BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.core.award(self.credential, self.event(grant))
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reward_receipts').fetchone()[0], 0)
            db.execute('DROP TRIGGER synthetic_failure')
        self.assertEqual(self.core.award(self.credential, self.event(grant))['progress']['progress'], 1)

    def test_completion_does_not_claim_a_rendered_reward_and_expiry_is_explicit(self):
        grant = self.grant()
        for sequence in range(1, TARGET+3):
            result = self.core.award(self.credential, self.event(grant, sequence))
        self.assertEqual(result['progress']['progress'], TARGET)
        self.assertTrue(result['progress']['completed'])
        self.assertFalse(result['progress']['reward_ready'])
        dashboard = json.dumps(self.core.dashboard(ISSUER, 'subject_1'))
        for private in (grant, self.credential, SESSION, 'abc123'): self.assertNotIn(private, dashboard)
        self.now[0] += REPLAY_SECONDS + 1
        with self.assertRaises(Refused): self.core.award(self.credential, self.event(grant, 100))
        self.assertEqual(self.count(), TARGET)


if __name__ == '__main__': unittest.main()
