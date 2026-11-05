"""Synthetic DLC approval checks; no game assets, network or server needed."""
import json
from pathlib import Path
import tempfile
import unittest

from hosting.dlc_gate import build_acceptance, main, save_private
from hosting.rotation import installed_maps, load_catalog

ROOT = Path(__file__).resolve().parents[1]


class DlcGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / 'game'
        self.game.mkdir()
        for name in ('mp_raid.ff', 'mp_hydro.ff'):
            path = self.game / 'zone/all' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic map fixture')
        (self.game / 'zone/all/dlc1.ipak').write_bytes(b'synthetic support fixture')
        self.path = self.root / 'private/dlc_acceptance.json'
        self.catalog = load_catalog(ROOT / 'storage/t6/outlands_rotation.json')
        self.catalog['modes'] = {'tdm': 1, 'dom': 1}
        self.files = {'mp_hydro': ['zone/all/mp_hydro.ff', 'zone/all/dlc1.ipak']}

    def receipt(self, mode, passed=True):
        case = {'map_name': 'mp_hydro', 'mode': mode}
        return {'plan': {'network_mode': 'none', 'published_ports': False,
                         'human_clients': False, 'live_state': False,
                         'cases': [case]},
                'results': [{'case': case, 'passed': passed, 'native_crash': False,
                             'script_error': False,
                             'samples': [{'kind': 'complete', 'stage': 0, 'map': 'mp_hydro',
                                          'mode': mode, 'bots': 16, 'moved': 9,
                                          'kills': 5, 'score': 500}]}]}

    def test_dlc_denied_without_all_native_modes_and_valid_packages(self):
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid'})
        report = self.root / 'tdm.json'
        report.write_text(json.dumps(self.receipt('tdm')))
        with self.assertRaisesRegex(ValueError, 'Missing passing'):
            build_acceptance(self.game, self.files, [report], {'tdm', 'dom'})
        report.write_text(json.dumps(self.receipt('tdm', passed=False)))
        with self.assertRaisesRegex(ValueError, 'Missing passing'):
            build_acceptance(self.game, self.files, [report], {'tdm'})
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid'})

    def test_valid_receipts_gate_dlc_and_hash_changes_revoke_it(self):
        reports = []
        for mode in ('tdm', 'dom'):
            path = self.root / (mode + '.json')
            path.write_text(json.dumps(self.receipt(mode)))
            reports.append(path)
        data = build_acceptance(self.game, self.files, reports, {'tdm', 'dom'})
        save_private(self.path, data)
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid', 'mp_hydro'})
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            save_private(self.path, data)
        (self.game / 'zone/all/dlc1.ipak').write_bytes(b'changed support')
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid'})

    def test_dlc_denied_when_new_mode_enabled_or_manifest_corrupt(self):
        reports = []
        for mode in ('tdm', 'dom'):
            path = self.root / (mode + '.json')
            path.write_text(json.dumps(self.receipt(mode)))
            reports.append(path)
        save_private(self.path, build_acceptance(self.game, self.files, reports, {'tdm', 'dom'}))
        self.catalog['modes']['conf'] = 1
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid'})
        self.path.write_text('{broken')
        self.assertEqual(set(installed_maps(self.catalog, self.game, self.path)), {'mp_raid'})

    def test_cli_creates_private_gate_from_reports_and_refuses_unsafe_path(self):
        candidate = self.root / 'candidate.json'
        candidate.write_text(json.dumps(self.files))
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps(self.catalog))
        reports = []
        for mode in ('tdm', 'dom'):
            path = self.root / (mode + '.json')
            path.write_text(json.dumps(self.receipt(mode)))
            reports.extend(['--report', str(path)])
        args = ['--game-dir', str(self.game), '--candidate', str(candidate),
                '--catalog', str(catalog), '--output', str(self.path), *reports]
        self.assertEqual(main(args), 0)
        self.assertIn('mp_hydro', installed_maps(self.catalog, self.game, self.path))
        self.assertEqual(main(args), 1)
        candidate.write_text(json.dumps({'mp_hydro': ['zone/all/mp_hydro.ff', '../private.ipak']}))
        self.path.unlink()
        self.assertEqual(main(args), 1)
        self.assertFalse(self.path.exists())

    def test_compiled_sound_bank_can_be_a_reviewed_dependency(self):
        bank = self.game / 'sound/mpl_hydro.all.sabs'
        bank.parent.mkdir(parents=True)
        bank.write_bytes(b'synthetic sound package')
        files = {'mp_hydro': ['zone/all/mp_hydro.ff', 'sound/mpl_hydro.all.sabs']}
        reports = []
        for mode in ('tdm', 'dom'):
            path = self.root / (mode + '.json')
            path.write_text(json.dumps(self.receipt(mode)))
            reports.append(path)
        save_private(self.path, build_acceptance(self.game, files, reports, {'tdm', 'dom'}))
        self.assertIn('mp_hydro', installed_maps(self.catalog, self.game, self.path))


if __name__ == '__main__':
    unittest.main()
