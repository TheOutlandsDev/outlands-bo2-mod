import copy
import unittest
from hosting.live_audit import assess, worker_activity, challenge_activity


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

    def test_optional_challenge_queue_age_blocks_and_privacy(self):
        health={'schema':1,'scope':'operator_aggregate','status':'idle','pending':0,'acknowledged':0,
                'oldest_pending_at':None,'oldest_pending_age_seconds':None,'pending_age_unknown':0,
                'last_successful_delivery_at':None,'last_poll_at':10000,'poll_age_seconds':1,
                'blocked_reason':None,'blocked_since':None}
        self.assertTrue(all(challenge_activity(health)['checks'].values()))
        queued=health|{'pending':1,'status':'backlogged','oldest_pending_at':9999,'oldest_pending_age_seconds':2}
        self.assertTrue(all(challenge_activity(queued)['checks'].values()))
        for changes in ({'oldest_pending_age_seconds':301},{'pending_age_unknown':1},{'poll_age_seconds':121},
                        {'status':'blocked','blocked_reason':'log_continuity'}):
            self.assertFalse(all(challenge_activity(queued|changes)['checks'].values()))
        for value in (None,health|{'player':'private'},health|{'blocked_reason':'private'},health|{'poll_age_seconds':float('nan')}):
            result=challenge_activity(value);self.assertIsNone(result['health']);self.assertFalse(all(result['checks'].values()))


if __name__ == '__main__':
    unittest.main()
