import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from hosting.network_watch import (Collector, changes, counter_delta, epoch, native_events,
                                   parse_metrics, parse_peers, parse_udp, pressure, read_only, watch)


PRIVATE = 'SYNTHETIC_PRIVATE_PLAYER'
UDP = ('Udp: InErrors RcvbufErrors SndbufErrors MemErrors\nUdp: 9 8 0 0\n'
       '7: 0100007F:1371 0100007F:ABCD 07 00000010:00000020 00:00000000 00000000 1000 0 123456 2 0000000000000000 6\n')


class NetworkWatchTests(unittest.TestCase):
    def test_udp_queues_drop_delta_reset_and_socket_disappearance(self):
        first = parse_udp(UDP)
        self.assertEqual((first['socket_count'], first['queue_tx_bytes'], first['queue_rx_bytes']), (1, 16, 32))
        changed = parse_udp(UDP.replace('9 8 0 0', '12 11 0 0').replace('00000020', '00000040').replace('0000000000000000 6', '0000000000000000 10'))
        delta = counter_delta(first['counters'], changed['counters'])
        self.assertTrue(delta['continuous'])
        self.assertEqual(delta['delta']['RcvbufErrors'], 3)
        self.assertEqual(delta['delta']['socket_drops'], 4)
        self.assertEqual(changed['queue_rx_bytes'], 64)
        gone = parse_udp('Udp: InErrors RcvbufErrors SndbufErrors MemErrors\nUdp: 12 11 0 0\n')
        lost = counter_delta(changed['counters'], gone['counters'])
        self.assertFalse(lost['continuous'])
        self.assertEqual(lost['disappeared'], ['socket_drops'])
        self.assertIsNone(lost['delta']['socket_drops'])
        reset = counter_delta(changed['counters'], first['counters'])
        self.assertFalse(reset['continuous'])
        self.assertIn('RcvbufErrors', reset['reset'])
        self.assertIsNone(reset['delta']['RcvbufErrors'])
        self.assertFalse(parse_udp('unavailable')['available'])

    def test_peer_paths_require_active_and_omit_all_identity_data(self):
        value = {'BackendState': 'Running', 'Peer': {
            PRIVATE: {'Online': True, 'Active': False, 'Relay': PRIVATE},
            'other': {'Online': True, 'Active': True, 'CurAddr': '203.0.113.99:1234', 'Relay': PRIVATE},
            'third': {'Online': True, 'Active': True, 'CurAddr': '', 'Relay': PRIVATE},
            'fourth': {'Online': False, 'Active': True}}}
        result = parse_peers(value)
        self.assertEqual(result, {'available': True, 'backend_running': True, 'online': 3,
                                 'active': 3, 'active_direct': 1, 'active_relay': 1, 'active_unknown': 1})
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotIn('203.0.113.99', json.dumps(result))
        self.assertFalse(parse_peers({'Peer': None})['available'])
        self.assertFalse(parse_peers({'Peer': {'private': 'malformed'}})['available'])

    def test_metrics_allowlist_direction_and_absence_are_explicit(self):
        raw = ('tailscaled_inbound_packets_total{path="derp"} 3\n'
               'tailscaled_outbound_packets_total{path="direct_ipv4"} 5\n'
               'tailscaled_inbound_dropped_packets_total{reason="acl"} 7\n'
               'tailscaled_outbound_dropped_packets_total{reason="acl"} 9\n'
               'tailscaled_outbound_dropped_packets_total{reason="multicast"} 12\n'
               'tailscaled_outbound_packets_total{path="direct_ipv4",peer="' + PRIVATE + '"} 999\n'
               'tailscaled_outbound_packets_total{path="' + PRIVATE + '"} 999\n'
               'private_' + PRIVATE + '{reason="error"} 999\n')
        result = parse_metrics(raw)
        self.assertTrue(result['available'])
        self.assertEqual(result['counters']['drop_in_acl'], 7)
        self.assertEqual(result['counters']['drop_out_acl'], 9)
        self.assertEqual(result['counters']['out_direct_ipv4'], 5)
        self.assertIsNone(result['counters']['in_direct_ipv4'])
        self.assertIn('drop_in_fragment', result['not_exported'])
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertFalse(parse_metrics('not available')['available'])
        gone = counter_delta(result['counters'], parse_metrics('')['counters'])
        self.assertFalse(gone['continuous'])
        self.assertIn('in_derp', gone['disappeared'])

    def test_native_timestamp_window_counts_hitches_not_quoted_timeouts(self):
        before, end = epoch('2026-01-01T12:00:00Z'), epoch('2026-01-01T12:00:05Z')
        raw = '\n'.join(('2026-01-01T12:00:00Z ^3Hitch warning: 200 msec frame time on main thread',
                         '2026-01-01T12:00:01.123456789Z \x1b[31m^3Hitch warning: 5282 msec frame time on main thread\x1b[0m',
                         '2026-01-01T12:00:02Z ^3Dropping client ' + PRIVATE + ':   EXE_TIMEDOUT',
                         '2026-01-01T12:00:03Z script runtime error: ' + PRIVATE,
                         '2026-01-01T12:00:04Z ' + PRIVATE + ': connection interrupted, timed out',
                         '2026-01-01T12:00:04Z ' + PRIVATE + ': unknown function or script runtime error',
                         '2026-01-01T12:00:04Z ' + PRIVATE + ': Hitch warning: 616 msec frame time on server thread',
                         '2026-01-01T12:00:04Z OUTLANDS_CHAT_V1|x|script runtime error timed out',
                         '2026-01-01T12:00:05Z ^3Hitch warning: 616 msec frame time on server thread',
                         '2026-01-01T12:00:06Z Dropping client ' + PRIVATE + ': EXE_TIMEDOUT',
                         'Dropping client ' + PRIVATE + ': EXE_TIMEDOUT'))
        result = native_events(raw, before, end)
        self.assertEqual(result['counts'], {'hitch': 2, 'timeout': 1, 'script_error': 1})
        self.assertEqual(result['hitch_max_ms'], 5282)
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotIn('EXE_TIMEDOUT', json.dumps(result))
        # The lower boundary is exclusive, so adjacent windows do not recount.
        self.assertEqual(native_events(raw, end, end + 2)['counts']['timeout'], 1)

    def test_native_detail_limit_and_pressure_are_bounded(self):
        raw = '\n'.join('2026-01-01T12:00:01Z script runtime error: ' + PRIVATE for _ in range(40))
        result = native_events(raw, epoch('2026-01-01T12:00:00Z'), epoch('2026-01-01T12:00:02Z'), limit=40)
        self.assertEqual(result['counts']['script_error'], 40)
        self.assertEqual(len(result['events']), 32)
        self.assertTrue(result['event_details_truncated'])
        self.assertTrue(result['log_tail_truncated'])
        self.assertEqual(pressure('some avg10=0.12 avg60=0.2 avg300=nan total=45 private=' + PRIVATE),
                         {'some': {'avg10': 0.12, 'avg60': 0.2, 'total': 45}})

    def test_lifecycle_disappearance_restart_and_identity_privacy(self):
        collector = Collector('synthetic-project')
        original = PRIVATE + ' true original-time 0\nother-private-id true original-time 0\n'
        collector.docker = Mock(side_effect=[original, None, original.replace('original-time', 'new-time')])
        first = collector.lifecycle()
        self.assertTrue(first['continuous'])
        missing = collector.lifecycle()
        self.assertFalse(missing['available'])
        self.assertFalse(missing['continuous'])
        self.assertFalse(collector.lifecycle()['continuous'])
        self.assertNotIn(PRIVATE, json.dumps(first))

    def test_socket_replacement_without_drop_decrease_is_discontinuous(self):
        collector = Collector('synthetic-project')
        current = [UDP]
        def raw(*args):
            if args[0] == 'inspect':
                return 'private-id true original 0\nother-id true original 0\n'
            if 'status' in args:
                return '{"Peer":{},"BackendState":"Running"}'
            if 'metrics' in args:
                return 'tailscaled_outbound_packets_total{path="derp"} 0'
            return current[0]
        collector.docker = Mock(side_effect=raw)
        with patch('hosting.network_watch.time.monotonic', return_value=0), patch('hosting.network_watch.host_snapshot', return_value={'available': True}):
            first = collector.sample('same', 'same')
            current[0] = UDP.replace('123456', '987654')
            second = collector.sample('same', 'same')
        self.assertTrue(first['udp']['socket_continuous'])
        self.assertFalse(second['udp']['socket_continuous'])
        self.assertNotIn('987654', json.dumps(second))

    def test_cached_metrics_are_unknown_delta_not_fresh_zero(self):
        sample = {'udp': parse_udp(UDP), 'host': {'oom_kill': 2},
                  'tailnet': {'at': 'old', 'metrics': parse_metrics('tailscaled_outbound_packets_total{path="derp"} 2')}}
        result = changes(sample, copy.deepcopy(sample))
        self.assertFalse(result['tailnet']['refreshed'])
        self.assertIsNone(result['tailnet']['delta']['out_derp'])
        later = copy.deepcopy(sample); later['tailnet']['at'] = 'new'
        result = changes(sample, later)
        self.assertTrue(result['tailnet']['refreshed'])
        self.assertEqual(result['tailnet']['delta']['out_derp'], 0)

    @unittest.skipUnless(os.name == 'posix', 'Linux observer process-group boundary')
    def test_timeout_kills_wrapper_and_grandchild_without_hanging_pipes(self):
        code = ('import subprocess,sys,time; '
                'subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
                'time.sleep(30)')
        started = time.monotonic()
        self.assertIsNone(read_only([sys.executable, '-c', code], timeout=0.1))
        self.assertLess(time.monotonic() - started, 3)

    def test_interrupt_cleans_up_process_group_before_propagating(self):
        process = Mock(pid=12345)
        process.communicate.side_effect = [KeyboardInterrupt(), ('', '')]
        with patch('hosting.network_watch.subprocess.Popen', return_value=process), patch('hosting.network_watch.os.killpg', create=True) as kill:
            with self.assertRaises(KeyboardInterrupt):
                read_only(['synthetic-read-only-command'])
        kill.assert_called_once_with(12345, signal.SIGKILL)

    def test_bounded_watch_uses_private_aggregate_and_final_refresh(self):
        clock = [0]
        baseline = {'at': '', 'lifecycle': {'available': True, 'continuous': True, 'game_running': True, 'tailnet_running': True},
                    'udp': parse_udp(UDP), 'native': {'available': True, 'counts': {'hitch': 0, 'timeout': 0, 'script_error': 0}, 'events': []},
                    'host': {'available': True, 'oom_kill': 4},
                    'tailnet': {'peers': {'available': True}, 'metrics': parse_metrics('tailscaled_outbound_packets_total{path="derp"} 0')}}
        class Fake:
            calls = []
            def sample(self, start, end, force_slow=False):
                self.calls.append(force_slow)
                result = copy.deepcopy(baseline); result['at'] = end
                return result
        fake = Fake()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
        with tempfile.TemporaryDirectory() as temporary, patch('hosting.network_watch.time.monotonic', side_effect=lambda: clock[0]), \
                patch('hosting.network_watch.time.sleep', side_effect=lambda value: clock.__setitem__(0, clock[0] + value)), \
                patch('hosting.network_watch.stamp', side_effect=lambda: datetime.fromtimestamp(base + clock[0], timezone.utc).isoformat()):
            report = watch(fake, 30, 5, Path(temporary))
            raw = (Path(temporary) / 'samples.jsonl').read_text()
            self.assertTrue(report['collection_available'])
            self.assertTrue(report['lifecycle_and_counters_continuous'])
            self.assertEqual(report['samples'], 7)
            self.assertTrue(fake.calls[-1])
            self.assertFalse(report['services_modified'])
            self.assertFalse(report['external_client_connection_verified'])
            self.assertEqual((Path(temporary) / 'samples.jsonl').stat().st_mode & 0o777, 0o600)
            self.assertNotIn(PRIVATE, raw)
            self.assertNotIn('0100007F', raw)


if __name__ == '__main__':
    unittest.main()
