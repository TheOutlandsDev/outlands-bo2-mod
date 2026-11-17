import copy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import Mock
from hosting.live_audit import (assess, worker_activity, challenge_activity,
                               model_memory_events, assess_model_memory,
                               native_chat_activity)


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
        worker['native_deliveries'] = 1
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

    def test_optional_service_disappearance_or_addition_breaks_continuity(self):
        for missing_from in ('before', 'after'):
            first, last, before, after, worker = self.fixtures()
            before['account-agent'] = copy.deepcopy(before['t6'])
            after['account-agent'] = copy.deepcopy(before['t6'])
            (before if missing_from == 'before' else after).pop('account-agent')
            result = assess(first, last, before, after, worker)
            self.assertFalse(result['checks']['no_restarts_during_observation'])
            self.assertFalse(result['passed'])

    def test_old_native_receipt_cannot_satisfy_recent_worker_delivery(self):
        first, last, before, after, worker = self.fixtures()
        first['chat_deliveries'] = last['chat_deliveries'] = 900
        worker['native_deliveries'] = 0
        result = assess(first, last, before, after, worker)
        self.assertTrue(result['checks']['chat_recent_submissions'])
        self.assertFalse(result['checks']['native_chat_delivered'])
        self.assertFalse(result['passed'])
        # Quiet 15-second samples are valid when the recent 30-minute window
        # has a receipt; no short-window delivery delta is required.
        worker['native_deliveries'] = 1
        result = assess(first, last, before, after, worker)
        self.assertTrue(result['passed'])
        self.assertEqual(result['chat_deliveries_observed_in_window'], 0)

    def test_native_receipts_require_recent_docker_time_and_anchored_marker(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp()
        private = 'SYNTHETIC_PRIVATE_ALIAS'
        receipt = 'OUTLANDS_CHAT_ACK_V1|synthetic-request|3|' + private + '|banter'
        recent = '2026-01-01T11:59:59.123456789Z '
        old = '2026-01-01T11:29:59Z '
        raw = '\n'.join((recent + '\x1b[38;2;255;255;255m' + receipt + '\x1b[0m',
                         '2026-01-01T11:30:00+00:00 ' + receipt,
                         old + receipt, receipt, recent + 'Player quoted ' + receipt,
                         'not-a-timestamp ' + receipt,
                         '2026-01-01T11:59:59 ' + receipt,
                         '2026-01-01T12:00:01Z ' + receipt,
                         recent + 'OUTLANDS_CHAT_ACK_V2|synthetic-request|3|' + private + '|banter',
                         recent + 'OUTLANDS_CHAT_ACK_V1|',
                         recent + receipt + ('x' * 192)))
        result = native_chat_activity(raw, now=now)
        self.assertEqual(result, {'native_deliveries': 2})
        self.assertNotIn(private, json.dumps(result))
        self.assertNotIn('synthetic-request', json.dumps(result))
        self.assertNotIn('2026-', json.dumps(result))

    def test_explicit_fallback_excludes_optional_model_but_not_worker_failures(self):
        first, last, before, after, worker = self.fixtures()
        after['ollama'].update(running=False, health='unhealthy')
        result = assess(first, last, before, after, worker, chat_mode='fallback')
        self.assertTrue(result['passed'])
        self.assertEqual(result['excluded_optional_services'], {'ollama': 'chat_mode_fallback'})
        self.assertNotIn('ollama_running', result['checks'])
        self.assertNotIn('ollama_healthy', result['checks'])
        worker['tracebacks'] = 1
        self.assertFalse(assess(first, last, before, after, worker, chat_mode='fallback')['passed'])
        worker['tracebacks'] = 0
        after['t6']['running'] = False
        self.assertFalse(assess(first, last, before, after, worker, chat_mode='fallback')['passed'])

    def test_ollama_mode_requires_model_and_unknown_mode_cannot_bypass_checks(self):
        first, last, before, after, worker = self.fixtures()
        for unavailable in ('absent', 'stopped', 'unhealthy'):
            current = copy.deepcopy(after)
            if unavailable == 'absent': current.pop('ollama')
            if unavailable == 'stopped': current['ollama']['running'] = False
            if unavailable == 'unhealthy': current['ollama']['health'] = 'unhealthy'
            result = assess(first, last, before, current, worker, chat_mode='ollama')
            self.assertFalse(result['passed'], unavailable)
            self.assertEqual(result['excluded_optional_services'], {})
        for mode in ('invalid', 'fallback-with-private-data'):
            result = assess(first, last, before, after, worker, chat_mode=mode)
            self.assertFalse(result['checks']['chat_mode_valid'])
            self.assertEqual(result['excluded_optional_services'], {})
        before.pop('ollama'); after.pop('ollama')
        result = assess(first, last, before, after, worker, chat_mode='fallback')
        self.assertTrue(result['passed'])
        self.assertIn('ollama', result['excluded_optional_services'])

    def test_memory_events_are_aggregate_and_fail_new_child_oom_kills(self):
        docker = Mock()
        details = {'Id': 'synthetic-container', 'State': {'Running': True}}
        docker.call.return_value = 'low 0\nhigh 0\nmax 123\noom 7\noom_kill 5\noom_group_kill 0\n'
        before = model_memory_events(docker, details)
        self.assertEqual(before, {'max': 123, 'oom': 7, 'oom_kill': 5})
        docker.call.assert_called_once_with('exec', 'synthetic-container', 'sh', '-c',
                                            'cat /sys/fs/cgroup/memory.events')
        unchanged = assess_model_memory(before, before)
        self.assertTrue(all(unchanged['checks'].values()))
        self.assertEqual(len(unchanged['warnings']), 1)
        self.assertIn('historical', unchanged['warnings'][0])
        after = {'max': 200, 'oom': 8, 'oom_kill': 6}
        current = assess_model_memory(before, after)
        self.assertFalse(current['checks']['ollama_no_new_oom_kills'])
        self.assertEqual(current['health']['delta'], {'max': 77, 'oom': 1, 'oom_kill': 1})
        self.assertTrue(any('new cgroup OOM kills' in warning for warning in current['warnings']))
        # Child kills do not need a container restart or unhealthy status.
        self.assertTrue(assess(*self.fixtures())['passed'])
        self.assertFalse(all((assess(*self.fixtures())['checks'] | current['checks']).values()))

    def test_memory_counter_pressure_reset_and_unavailable_are_distinct(self):
        counts = {'max': 10, 'oom': 0, 'oom_kill': 0}
        pressure = assess_model_memory(counts, counts | {'max': 11})
        self.assertTrue(all(pressure['checks'].values()))
        self.assertIn('memory-limit pressure', pressure['warnings'][0])
        reset = assess_model_memory(counts, counts | {'max': 0})
        self.assertFalse(reset['checks']['ollama_memory_counters_continuous'])
        self.assertIn('reset', reset['warnings'][0])
        unavailable = assess_model_memory(counts, None)
        self.assertEqual(unavailable['checks'], {})
        self.assertIn('unavailable', unavailable['warnings'][0])
        docker = Mock()
        self.assertIsNone(model_memory_events(docker, {'State': {'Running': False}}))
        docker.call.assert_not_called()
        details = {'Id': 'synthetic-container', 'State': {'Running': True}}
        for invalid in ('max 1\noom 0\n', 'max 1\noom 0\noom_kill private\n',
                        'max 1\noom 0\noom_kill 0\noom_kill 1\n'):
            docker.call.return_value = invalid
            self.assertIsNone(model_memory_events(docker, details))
        docker.call.side_effect = RuntimeError('Unavailable')
        self.assertIsNone(model_memory_events(docker, details))

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
