"""First Outlands camo award rules with synthetic trusted-native events only."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import camo_challenge as c


@unittest.skipIf(os.name == 'nt', 'Private store is hosted on Linux')
class ChallengeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.root.chmod(0o700)
        self.path = self.root / 'camo.json'
        self.store = c.ChallengeStore(self.path)
        self.player = 'a' * 64

    def event(self, sequence=1, **changes):
        return replace(c.KillEvent(self.player, 'server_session_1', 'match_1', sequence,
                                   c.WEAPON_ID, c.REVISION, True, True, True, True),
                       **changes)

    def test_exactly_once_unlock_survives_restart_and_player_separation(self):
        first = self.store.apply(self.event())
        self.assertEqual(first['progress'], 1)
        self.assertFalse(first['unlocked'])
        self.assertEqual(self.store.apply(self.event()), first)
        self.assertIsNone(self.store.apply(self.event(weapon='mp7_mp')))
        self.assertEqual(self.store.read('b' * 64)['progress'], 0)
        for number in range(2, c.TARGET + 1):
            result = self.store.apply(self.event(number))
        self.assertEqual(result['progress'], c.TARGET)
        self.assertTrue(result['unlocked'])
        self.assertEqual(c.ChallengeStore(self.path).read(self.player), result)
        self.assertEqual(c.ChallengeStore(self.path).apply(self.event(1)), result)
        self.assertEqual(c.ChallengeStore(self.path).apply(self.event(1, player_key='b' * 64))['progress'], 1)
        raw = self.path.read_text()
        self.assertNotIn('server_session_1', raw)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_wrong_weapon_bot_friendly_unconfirmed_and_conflicts_never_earn(self):
        for changes in ({'weapon': 'mp7_mp'}, {'human': False}, {'enemy': False},
                        {'headshot': False}, {'kill_confirmed': False},
                        {'revision': c.REVISION + 1}, {'session': '../bad'},
                        {'player_key': 'not-a-private-key'}, {'sequence': True}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.store.apply(self.event(**changes)))
        self.assertFalse(self.path.exists())
        self.assertEqual(self.store.apply(self.event())['progress'], 1)
        # Reusing a native session/sequence with changed payload is a conflict.
        self.assertIsNone(self.store.apply(self.event(match='match_2')))
        self.assertEqual(self.store.read(self.player)['progress'], 1)

    def test_interrupted_write_keeps_previous_reward_state(self):
        self.store.apply(self.event())
        before = self.path.read_bytes()
        with patch('camo_challenge.os.replace', side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):
                self.store.apply(self.event(2))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(c.ChallengeStore(self.path).read(self.player)['progress'], 1)

    def test_tampered_private_state_is_refused(self):
        self.path.write_text(json.dumps({'schema': 1, 'players': {self.player: {'progress': 1, 'seen': {}}}}))
        with self.assertRaisesRegex(ValueError, 'state|player'):
            c.ChallengeStore(self.path)
        self.path.unlink()
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises((ValueError, OSError)):
            c.ChallengeStore(self.path)

    def test_failure_after_rename_requires_reload_before_replay(self):
        self.store.apply(self.event())
        with patch('camo_challenge.os.fsync', side_effect=[None, OSError('synthetic directory fsync')]):
            with self.assertRaises(OSError):
                self.store.apply(self.event(2))
        with self.assertRaisesRegex(ValueError, 'reload'):
            self.store.apply(self.event(2))
        reloaded = c.ChallengeStore(self.path)
        self.assertEqual(reloaded.read(self.player)['progress'], 2)
        self.assertEqual(reloaded.apply(self.event(2))['progress'], 2)


if __name__ == '__main__':
    unittest.main()
