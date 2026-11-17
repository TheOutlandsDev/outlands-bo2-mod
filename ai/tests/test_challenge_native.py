import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camo_challenge import ChallengeStore
from challenge_native import ChallengeAdapter, NativeEvent, NativeLog, identity_salt, writer_lock


@unittest.skipIf(os.name == 'nt', 'Challenge worker is hosted on Linux')
class NativeChallengeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.root.chmod(0o700)
        self.store = ChallengeStore(self.root / 'progress.json')
        self.adapter = ChallengeAdapter(self.store, 'a' * 64, identity_salt(self.root))

    def line(self, seq=1, kind='hello', **changes):
        row = {'credential': 'a'*64, 'match': 'match1', 'session': 'session1', 'seq': seq,
               'kind': kind, 'slot': 0, 'guid': 'abc123', 'weapon': 'none' if kind != 'kill' else 'an94_mp',
               'human': 1, 'enemy': int(kind == 'kill'), 'headshot': int(kind == 'kill'), 'confirmed': int(kind == 'kill')}
        row.update(changes)
        return 'OUTLANDS_CHALLENGE_V1|' + '|'.join(map(str, row.values()))

    def test_bound_native_events_unlock_once_after_worker_restart(self):
        lines = [self.line()] + [self.line(i, 'kill') for i in range(2, 27)]
        for line in lines: result = self.adapter.ingest(line)
        self.assertTrue(result['unlocked']); self.assertEqual(result['progress'], 25)
        reopened = ChallengeAdapter(ChallengeStore(self.root/'progress.json'), 'a'*64, identity_salt(self.root))
        for line in lines: result = reopened.ingest(line)
        self.assertEqual(result['progress'], 25)
        self.assertNotIn('abc123', (self.root/'progress.json').read_text())
        self.assertNotIn('session1', (self.root/'progress.json').read_text())

    def test_wrong_token_bots_prefixes_invalid_numbers_and_unbound_kills_rejected(self):
        for changes in ({'credential': 'b'*64}, {'human': 0}, {'seq': '01'}, {'slot': 18}):
            self.assertIsNone(self.adapter.ingest(self.line(**changes)))
        self.assertIsNone(self.adapter.ingest('player: '+self.line()))
        self.assertIsNone(self.adapter.ingest(self.line(2, 'kill')))
        self.assertFalse((self.root/'progress.json').exists())

    def test_slot_reuse_departure_and_out_of_order_events_cannot_cross_award(self):
        self.adapter.ingest(self.line()); self.adapter.ingest(self.line(2, 'kill'))
        self.adapter.ingest(self.line(3, 'depart'))
        self.adapter.ingest(self.line(4, 'hello'))
        self.assertNotIn(0, self.adapter.sessions)
        self.adapter.ingest(self.line(1, 'hello', session='session2', guid='def456'))
        self.assertIsNone(self.adapter.ingest(self.line(5, 'kill')))
        self.adapter.ingest(self.line(2, 'kill', session='session2', guid='def456'))
        for identity in ('abc123', 'def456'):
            self.assertEqual(self.store.read(self.adapter.player_key(identity))['progress'], 1)

    def test_ineligible_event_sequence_cannot_be_rewritten_into_reward(self):
        self.adapter.ingest(self.line())
        for seq, changes in enumerate(({'enemy': 0}, {'headshot': 0}, {'confirmed': 0}, {'weapon': 'mp7_mp'}), 2):
            self.assertIsNone(self.adapter.ingest(self.line(seq, 'kill', **changes)))
            self.assertIsNone(self.adapter.ingest(self.line(seq, 'kill')))
        self.assertFalse((self.root/'progress.json').exists())

    def test_current_log_replay_and_long_lines_are_bounded(self):
        path = self.root/'console.log'; path.write_text('x'*70000+'\n'+self.line()+'\n'+self.line(2,'kill')+'\n')
        tail = NativeLog(path)
        for _ in range(3):
            for line in tail.poll(): self.adapter.ingest(line)
        self.assertEqual(self.store.read(self.adapter.player_key('abc123'))['progress'], 1)
        self.assertEqual(tail.poll(), [])
        self.assertIsNotNone(NativeEvent.parse(self.line()))

    def test_writer_lock_blocks_a_second_writer_and_releases(self):
        with writer_lock(self.root):
            with self.assertRaises(BlockingIOError):
                with writer_lock(self.root): self.fail('second writer admitted')
        with writer_lock(self.root): pass
        self.assertFalse((self.root/'progress.json').exists())

    def test_session_cannot_move_to_another_slot_or_identity(self):
        self.adapter.ingest(self.line())
        self.adapter.ingest(self.line(2, 'hello', slot=1))
        self.assertNotIn(1, self.adapter.sessions)
        self.adapter.ingest(self.line(2, 'hello', guid='def456'))
        self.assertEqual(self.adapter.sessions[0]['key'][2], 'abc123')


if __name__ == '__main__': unittest.main()
