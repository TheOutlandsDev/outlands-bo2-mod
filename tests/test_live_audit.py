import copy
import unittest
from hosting.live_audit import assess, worker_activity


class LiveAuditTests(unittest.TestCase):
    def fixtures(self):
        services = {'t6': {'running': True, 'health': 'healthy', 'restarts': 1,
                           'started_at': 'old', 'historical_oom_flag': False},
                    'ollama': {'running': True, 'health': 'healthy', 'restarts': 0,
                               'started_at': 'old', 'historical_oom_flag': True}}
        sample = {'native_errors': 0, 'log_age_seconds': 1, 'chat_deliveries': 10,
                  'rotation_acks': 4, 'pending': ['mp_raid', 'tdm'],
                  'installed_maps': ['mp_raid'], 'settings': {'outlands_bot_idle_fill': 16},
                  'catalog': {'maps': {'mp_raid': {}, 'mp_studio': {}}, 'modes': {'tdm': 3}},
                  'match': {'clock': 1, 'map': 'mp_raid', 'mode': 'tdm', 'humans': 0,
                            'bots': 16, 'teams': [{'players': 8}, {'players': 8}]}}
        later = copy.deepcopy(sample)
        later['match']['clock'] = 2
        worker = worker_activity('Bot response submitted (fallback)')
        return sample, later, services, copy.deepcopy(services), worker

    def test_excluded_dlc_historical_flags_and_missing_startup_do_not_fail(self):
        result = assess(*self.fixtures())
        self.assertTrue(result['passed'])
        self.assertEqual(result['excluded_uninstalled_maps'], ['mp_studio'])
        self.assertEqual(len(result['warnings']), 2)
        self.assertEqual(result['chat_deliveries_observed_in_window'], 0)

    def test_new_restart_stale_telemetry_script_errors_and_bad_mode_fail(self):
        for failure in ('restart', 'stale', 'script', 'mode', 'population', 'teams', 'worker'):
            with self.subTest(failure=failure):
                first, last, before, after, worker = self.fixtures()
                if failure == 'restart': after['t6']['restarts'] += 1
                if failure == 'stale': last['log_age_seconds'] = 40
                if failure == 'script': last['native_errors'] = 1
                if failure == 'mode': last['catalog']['modes']['sd'] = 1
                if failure == 'population': last['match']['bots'] = 15
                if failure == 'teams': last['match']['teams'][0]['players'] = 10
                if failure == 'worker': worker['tracebacks'] = 1
                self.assertFalse(assess(first, last, before, after, worker)['passed'])

    def test_model_fallback_is_activity_but_no_recent_activity_is_not(self):
        fixtures = self.fixtures()
        self.assertTrue(assess(*fixtures)['passed'])
        fixtures[-1]['fallback_submissions'] = 0
        self.assertFalse(assess(*fixtures)['passed'])


if __name__ == '__main__':
    unittest.main()
