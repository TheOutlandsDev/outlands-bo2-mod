#!/usr/bin/env python3
"""Bounded, read-only network evidence; no player data or background service."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
UDP_FIELDS = ('InErrors', 'RcvbufErrors', 'SndbufErrors', 'MemErrors')
PATHS = ('direct_ipv4', 'direct_ipv6', 'derp', 'peer_relay_ipv4', 'peer_relay_ipv6')
REASONS = ('acl', 'multicast', 'link_local_unicast', 'too_short', 'fragment', 'unknown_protocol', 'error')
METRICS = {'tailscaled_inbound_packets_total': ('in', 'path', PATHS),
           'tailscaled_outbound_packets_total': ('out', 'path', PATHS),
           'tailscaled_inbound_dropped_packets_total': ('drop_in', 'reason', REASONS),
           'tailscaled_outbound_dropped_packets_total': ('drop_out', 'reason', REASONS)}
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
HITCH = re.compile(r'^hitch warning:\s*([0-9]+)\s*msec frame[^\r\n]{0,160}\b(main|server) thread\s*$', re.I)
SCRIPT = re.compile(r'^(?:\*+\s*)?(?:error:\s*)?(?:script(?:\s+(?:runtime|compile|execution))?\s+error|unknown function|unresolved external|critical exception)\b', re.I)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def epoch(text):
    try:
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return value.timestamp() if value.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def parse_udp(text, socket_ids=None):
    lines, counters, sockets = text.splitlines(), {}, []
    for i, line in enumerate(lines):
        if line.startswith('Udp:') and i + 1 < len(lines) and lines[i + 1].startswith('Udp:'):
            try:
                counters = dict(zip(line.split()[1:], map(int, lines[i + 1].split()[1:])))
            except ValueError:
                pass
        fields = line.split()
        if len(fields) >= 13 and fields[0].endswith(':'):
            try:
                if int(fields[1].split(':')[1], 16) == 4977:
                    tx, rx = (int(x, 16) for x in fields[4].split(':'))
                    sockets.append((tx, rx, int(fields[-1])))
                    if socket_ids is not None:
                        socket_ids.add(fields[9])
            except (ValueError, IndexError):
                pass
    return {'available': all(k in counters for k in UDP_FIELDS), 'socket_count': len(sockets),
            'queue_tx_bytes': sum(s[0] for s in sockets) if sockets else None,
            'queue_rx_bytes': sum(s[1] for s in sockets) if sockets else None,
            'counters': {**{k: counters.get(k) for k in UDP_FIELDS},
                         'socket_drops': sum(s[2] for s in sockets) if sockets else None}}


def parse_peers(value):
    if not isinstance(value, dict) or not isinstance(value.get('Peer'), dict):
        return {'available': False}
    result = dict.fromkeys(('online', 'active', 'active_direct', 'active_relay', 'active_unknown'), 0)
    for peer in value['Peer'].values():
        if not isinstance(peer, dict):
            return {'available': False}
        result['online'] += peer.get('Online') is True
        if peer.get('Active') is not True:
            continue
        result['active'] += 1
        if isinstance(peer.get('CurAddr'), str) and peer['CurAddr']:
            result['active_direct'] += 1
        elif isinstance(peer.get('Relay'), str) and peer['Relay']:
            result['active_relay'] += 1
        else:
            result['active_unknown'] += 1
    return {'available': True, 'backend_running': value.get('BackendState') == 'Running', **result}


def parse_metrics(text):
    result = {prefix + '_' + label: None for prefix, _, labels in METRICS.values() for label in labels}
    for line in text.splitlines():
        match = re.fullmatch(r'([a-z_]+)\{([a-z_]+)="([a-z0-9_]+)"\}\s+([0-9]+)(?:\.0+)?', line)
        if not match or match[1] not in METRICS:
            continue
        prefix, key, labels = METRICS[match[1]]
        if match[2] == key and match[3] in labels:
            result[prefix + '_' + match[3]] = int(match[4])
    return {'available': any(v is not None for v in result.values()), 'counters': result,
            'not_exported': sorted(k for k, v in result.items() if v is None)}


def native_events(text, start, end, limit=2000):
    counts = dict.fromkeys(('hitch', 'timeout', 'script_error'), 0)
    events, hitch_max, lines = [], 0, text.splitlines()
    for raw in lines:
        token, separator, body = re.sub(r'\^[0-9]', '', ANSI.sub('', raw)).partition(' ')
        when = epoch(token)
        if not separator or when is None or not start < when <= end:
            continue
        if body.startswith('OUTLANDS_'):
            continue
        hitch = HITCH.fullmatch(body)
        kind = ('hitch' if hitch else 'timeout' if re.fullmatch(r'Dropping client [^\r\n|]{1,100}:\s*EXE_TIMEDOUT\s*', body)
                else 'script_error' if SCRIPT.search(body) else None)
        if kind:
            counts[kind] += 1
            event = {'at': datetime.fromtimestamp(when, timezone.utc).isoformat(), 'kind': kind}
            if hitch:
                event['ms'] = int(hitch[1]); hitch_max = max(hitch_max, event['ms'])
            if len(events) < 32:
                events.append(event)
    return {'available': end >= start, 'counts': counts, 'hitch_max_ms': hitch_max,
            'events': events, 'event_details_truncated': sum(counts.values()) > len(events),
            'log_tail_truncated': len(lines) >= limit}


def counter_delta(before, after):
    """Missing counters stay unknown; disappearance/reset cannot look like zero."""
    delta, lost, resets = {}, [], []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        if type(a) is not int or type(b) is not int:
            delta[key] = None
            if type(a) is int and type(b) is not int:
                lost.append(key)
        elif b < a:
            delta[key] = None; resets.append(key)
        else:
            delta[key] = b - a
    return {'delta': delta, 'disappeared': lost, 'reset': resets,
            'continuous': not lost and not resets}


def pressure(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] in ('some', 'full'):
            row = {}
            for pair in fields[1:]:
                key, _, raw = pair.partition('=')
                if key in ('avg10', 'avg60', 'avg300', 'total'):
                    try:
                        value = int(raw) if key == 'total' else float(raw)
                        if math.isfinite(value) and value >= 0:
                            row[key] = value
                    except ValueError:
                        pass
            result[fields[0]] = row
    return result


def host_snapshot():
    try:
        memory = dict((k, int(v) * 1024) for k, v in re.findall(
            r'^(MemAvailable|SwapFree):\s+(\d+) kB', Path('/proc/meminfo').read_text(), re.M))
        oom = re.search(r'(?m)^oom_kill (\d+)$', Path('/proc/vmstat').read_text())
        return {'available': bool(oom) and set(memory) == {'MemAvailable', 'SwapFree'}, **memory, 'oom_kill': int(oom[1]) if oom else None,
                'pressure': {k: pressure(Path('/proc/pressure', k).read_text()) for k in ('cpu', 'memory', 'io')}}
    except OSError:
        return {'available': False, 'oom_kill': None}


def read_only(args, merge_stderr=False, timeout=5):
    """Bound the wrapper and its descendants, including an sg/docker child."""
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        def cleanup():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.stdout.close(); process.stderr.close()
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            cleanup()
            return None
        except BaseException:
            cleanup()
            raise
        return stdout + (stderr if merge_stderr else '') if process.returncode == 0 else None
    except OSError:
        return None


class Collector:
    def __init__(self, project):
        self.project, self.initial, self.life, self.tailnet = project, None, None, None
        self.next_slow = 0
        self.socket_ids = None

    def docker(self, *args):
        return read_only(['bash', str(ROOT / 'hosting/docker.sh'), *args])

    def lifecycle(self):
        raw = self.docker('inspect', '--format', '{{.Id}} {{.State.Running}} {{.State.StartedAt}} {{.RestartCount}}',
                          self.project + '-t6-1', self.project + '-tailscale-1')
        rows = [line.split() for line in (raw or '').splitlines()]
        if len(rows) != 2 or any(len(row) != 4 for row in rows):
            return {'available': False, 'continuous': False}
        if self.initial is None:
            self.initial = rows
        return {'available': True, 'continuous': rows == self.initial,
                'game_running': rows[0][1] == 'true', 'tailnet_running': rows[1][1] == 'true'}

    def sample(self, start, end, force_slow=False):
        clock = time.monotonic()
        if force_slow or clock >= self.next_slow:
            self.life = self.lifecycle()
            raw = self.docker('exec', self.project + '-tailscale-1', 'tailscale', 'status', '--json')
            try:
                peers = parse_peers(json.loads(raw)) if raw is not None else {'available': False}
            except ValueError:
                peers = {'available': False}
            metrics = self.docker('exec', self.project + '-tailscale-1', 'tailscale', 'metrics', 'print')
            self.tailnet = {'at': end, 'peers': peers, 'metrics': parse_metrics(metrics or '')}
            self.next_slow = clock + 5
        raw = self.docker('exec', self.project + '-t6-1', 'cat', '/proc/net/snmp', '/proc/net/udp', '/proc/net/udp6')
        identities = set()
        udp = parse_udp(raw or '', socket_ids=identities)
        if self.socket_ids is None and identities:
            self.socket_ids = identities
        udp['socket_continuous'] = bool(identities) and identities == self.socket_ids
        native = {'available': True, 'counts': {'hitch': 0, 'timeout': 0, 'script_error': 0}, 'events': [], 'hitch_max_ms': 0,
                  'event_details_truncated': False, 'log_tail_truncated': False}
        if start != end:
            command = ['bash', str(ROOT / 'hosting/docker.sh'), 'logs', '--timestamps', '--since', start,
                       '--until', end, '--tail', '2000', self.project + '-t6-1']
            raw = read_only(command, merge_stderr=True)
            native = native_events(raw, epoch(start), epoch(end)) if raw is not None else {'available': False}
        return {'at': end, 'lifecycle': dict(self.life), 'udp': udp, 'native': native,
                'host': host_snapshot(), 'tailnet': self.tailnet}


def changes(before, after):
    refreshed = before['tailnet'].get('at') != after['tailnet'].get('at')
    metrics = counter_delta(before['tailnet']['metrics']['counters'], after['tailnet']['metrics']['counters'])
    metrics['refreshed'] = refreshed
    if not refreshed:
        metrics['delta'] = dict.fromkeys(metrics['delta'], None)
    return {'udp': counter_delta(before['udp']['counters'], after['udp']['counters']),
            'host_oom': counter_delta({'oom_kill': before['host'].get('oom_kill')}, {'oom_kill': after['host'].get('oom_kill')}),
            'tailnet': metrics}


def watch(collector, seconds, interval, directory):
    first, samples, begun = stamp(), [], time.monotonic()
    deadline = begun + seconds
    previous_time = first
    with (directory / 'samples.jsonl').open('x') as output:
        os.chmod(output.name, 0o600)
        while True:
            now = first if not samples else stamp()
            clock = time.monotonic()
            forced = bool(samples) and clock >= deadline
            sample = collector.sample(previous_time, now, force_slow=forced)
            sample['elapsed_seconds'] = round(clock - begun, 3)
            sample['collection_seconds'] = round(time.monotonic() - clock, 3)
            sample['wall_clock_continuous'] = not samples or epoch(now) > epoch(previous_time)
            if samples:
                sample['changes'] = changes(samples[-1], sample)
            samples.append(sample)
            output.write(json.dumps(sample, separators=(',', ':')) + '\n'); output.flush()
            previous_time = now
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if forced:
                    break
                continue
            time.sleep(min(interval, remaining))
    available = all(s['lifecycle']['available'] and s['udp']['available'] and s['udp']['socket_count'] > 0
                    and s['native']['available'] and not s['native'].get('log_tail_truncated')
                    and s['host']['available'] and s['wall_clock_continuous'] and s['tailnet']['peers']['available']
                    and s['tailnet']['metrics']['available'] for s in samples)
    continuous = all(s['lifecycle']['continuous'] and s['udp'].get('socket_continuous', True) for s in samples) and all(
        group['continuous'] for s in samples[1:] for group in s['changes'].values())
    return {'schema': 1, 'scope': 'bounded_readonly_backend', 'start': first, 'end': samples[-1]['at'],
            'requested_seconds': seconds, 'interval_seconds': interval, 'samples': len(samples),
            'collection_available': available, 'lifecycle_and_counters_continuous': continuous,
            'total_changes': changes(samples[0], samples[-1]),
            'native_window_complete': all(s['native']['available'] and not s['native'].get('log_tail_truncated') for s in samples),
            'observed_native_counts': {k: sum(s['native'].get('counts', {}).get(k, 0) for s in samples) for k in ('hitch', 'timeout', 'script_error')},
            'services_modified': False, 'external_client_connection_verified': False,
            'warnings': ['Peer paths are active-status hints; packet counters cover the whole tailnet node.',
                         'Absent metric series are not exported, not zero. This is not an external-client connection test.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--interval', type=int, default=2)
    parser.add_argument('--project', default='outlands-t6')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if not args.run or not 30 <= args.seconds <= 900 or not 1 <= args.interval <= 5 or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,60}', args.project):
        parser.error('Use explicit --run, 30–900 seconds, 1–5 second intervals and a safe Compose project.')
    directory = args.report_dir.absolute()
    if directory.exists() or any(p.is_symlink() for p in (directory, *directory.parents)):
        parser.error('Choose a fresh private report directory.')
    os.umask(0o077); directory.mkdir(parents=True, mode=0o700)
    print('Starting bounded read-only network watch; no services will change.', flush=True)
    try:
        report = watch(Collector(args.project), args.seconds, args.interval, directory)
    except (OSError, ValueError, KeyError, KeyboardInterrupt):
        report = {'collection_available': False, 'error': 'Observation incomplete; no services were changed.'}
    path = directory / 'report.json'
    path.write_text(json.dumps(report, indent=2) + '\n'); path.chmod(0o600)
    print(json.dumps({'collection_available': report['collection_available'], 'report': str(path)}, indent=2))
    return 0 if report['collection_available'] and report.get('lifecycle_and_counters_continuous') else 1


if __name__ == '__main__':
    raise SystemExit(main())
