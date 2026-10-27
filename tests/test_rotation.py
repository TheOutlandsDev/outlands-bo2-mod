"""Weighted rotation fairness, restart persistence and fixed native transport."""
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from hosting.rotation import Rotation, draw, installed_maps, load_catalog, rotation_entry
from tools.content_inventory import MAPS, SUPPORTED_MODES

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'storage/t6/outlands_rotation.json'


class DeckTests(unittest.TestCase):
    def test_full_catalog_includes_all_packs_and_native_modes(self):
        catalog = load_catalog(CATALOG)
        self.assertEqual(set(catalog['maps']), set(MAPS))
        self.assertEqual(set(catalog['modes']), set(SUPPORTED_MODES))
        self.assertEqual(len(catalog['maps']), 31)

    def test_equal_weights_cover_every_map_once_per_deck_and_avoid_recent(self):
        weights = {str(i): 1 for i in range(31)}
        rng = random.Random(123)
        history, deck = [], {}
        for turn in range(3100):
            selected, deck, window = draw(weights, deck, history, 5, rng)
            self.assertNotEqual(selected, history[-1] if history else None)
            self.assertNotIn(selected, history[-window:] if window else [])
            history.append(selected)
            deck[selected] -= 1
            if turn % 31 == 30:
                self.assertEqual(set(history[-31:]), set(weights))

    def test_weighted_decks_follow_ticket_ratios_without_starvation(self):
        weights = {str(i): 1 + (i % 3) for i in range(15)}
        rng, history, deck = random.Random(4), [], {}
        counts = dict.fromkeys(weights, 0)
        for _ in range(sum(weights.values()) * 100):
            selected, deck, _ = draw(weights, deck, history, 5, rng)
            self.assertNotEqual(selected, history[-1] if history else None)
            counts[selected] += 1
            history.append(selected)
            deck[selected] -= 1
        # No-immediate-repeat takes priority at constrained deck boundaries.
        # The supported 15-map pool must still stay within five percent of its
        # requested long-run shares, including the least-weighted maps.
        for key, weight in weights.items():
            self.assertLessEqual(abs(counts[key] - weight * 100), weight * 5)

    def test_small_pool_relaxes_oldest_exclusion_without_immediate_repeat(self):
        deck, history = {}, []
        for _ in range(100):
            selected, deck, _ = draw({'a': 8, 'b': 1}, deck, history, 5, random.Random(1))
            self.assertNotEqual(selected, history[-1] if history else None)
            history.append(selected)
            deck[selected] -= 1
        self.assertEqual(draw({'a': 1}, {}, ['a'], 5, random.Random(1))[0], 'a')

    def test_next_command_rejects_injection_or_unsupported_mode(self):
        self.assertEqual(rotation_entry('mp_raid', 'dom'), 'gametype dom execgts outlands_dom.cfg map mp_raid')
        for name, mode in (('mp_raid;quit', 'dom'), ('mp_raid', 'sd'), ('../map', 'tdm')):
            with self.assertRaises(ValueError): rotation_entry(name, mode)


@unittest.skipUnless(os.name == 'posix', 'Private container state is POSIX')
class DirectorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        for name in ('mp_raid', 'mp_slums', 'mp_hijacked'):
            for suffix in ('.ff', '_load.ff'):
                p = self.game / 'zone/all' / (name + suffix)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'not game data')
        self.path = self.root / 'private/rotation.json'
        self.sent = []

    def service(self):
        return Rotation(CATALOG, self.game, self.path, rng=random.Random(1), send=self.sent.append)

    def test_uninstalled_dlc_and_partial_map_are_never_selected(self):
        catalog = load_catalog(CATALOG)
        eligible = installed_maps(catalog, self.game)
        self.assertEqual(set(eligible), {'mp_raid', 'mp_slums', 'mp_hijacked'})
        (self.game / 'zone/all/mp_slums.ff').unlink()
        self.assertNotIn('mp_slums', installed_maps(catalog, self.game))
        p = self.game / 'zone/all/mp_raid.ff'
        p.write_bytes(b'')
        self.assertNotIn('mp_raid', installed_maps(catalog, self.game))

    def test_zero_weight_disables_installed_map_and_invalid_weights_fail(self):
        catalog = load_catalog(CATALOG)
        catalog['maps']['mp_raid']['weight'] = 0
        self.assertNotIn('mp_raid', installed_maps(catalog, self.game))
        custom = self.root / 'catalog.json'
        for value in (-1, 9, True, '2'):
            catalog['maps']['mp_raid']['weight'] = value
            custom.write_text(json.dumps(catalog))
            with self.assertRaises(ValueError): load_catalog(custom)

    def test_restart_keeps_pending_and_history_and_does_not_double_consume(self):
        service = self.service()
        selected = list(service.plan())
        self.assertEqual(self.service().plan(), selected)
        wire = 'OUTLANDS_ROTATION_V1|map_1|' + '|'.join(selected)
        self.assertTrue(service.observe(wire))
        after = json.loads(self.path.read_text())
        self.assertEqual(after['map_history'], [selected[0]])
        self.assertNotEqual(after['pending'][0], selected[0])
        self.assertTrue(service.observe(wire))
        self.assertEqual(json.loads(self.path.read_text()), after)
        self.assertTrue(service.observe(wire.replace('map_1', 'halftime_1')))
        self.assertEqual(json.loads(self.path.read_text()), after)
        self.assertEqual(self.service().plan(), after['pending'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(cmd.startswith('set outlands_rotation_plan "') for cmd in self.sent))
        self.assertEqual(len(self.sent), 3)

    def test_bad_or_chat_prefixed_events_cannot_change_state(self):
        service = self.service()
        before = self.path.read_bytes()
        for wire in ('Player: OUTLANDS_ROTATION_V1|map_1|mp_raid|dom',
                     'OUTLANDS_ROTATION_V1|map_1|mp_hydro|dom',
                     'OUTLANDS_ROTATION_V1|map_1|mp_raid|sd',
                     'OUTLANDS_ROTATION_V1|map_1|mp_raid|dom|extra'):
            self.assertFalse(service.observe(wire))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.sent)

    def test_atomic_write_failure_preserves_previous_state(self):
        service = self.service()
        before = self.path.read_bytes()
        with patch('hosting.rotation.os.replace', side_effect=OSError('fixture')):
            with self.assertRaises(OSError): service.save()
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_state_is_refused_instead_of_overwriting_it(self):
        service = self.service()
        self.path.write_text('{bad')
        with self.assertRaises(ValueError): self.service()
        self.assertEqual(self.path.read_text(), '{bad')
        self.path.unlink()
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError): self.service()
