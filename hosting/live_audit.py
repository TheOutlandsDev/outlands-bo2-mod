#!/usr/bin/env python3
"""Read-only, aggregate Outlands service audit. Raw logs and identities stay local.

Optional services are inspected only when installed. Historical lifecycle flags
are warnings; current health and changes during the observation window decide
health. This does not prove another device can connect through Tailscale.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from portal.portal import parse_snapshot
from tools.build_release import public_files

SERVICES = ('t6', 'tailscale', 'chat', 'ollama', 'accounts', 'account-agent', 'portal', 'portal-export', 'challenge-worker')
MODES = frozenset(('tdm', 'dm', 'dom', 'conf', 'ctf', 'dem', 'hq', 'koth'))
GAME_PROBE = r'''
import json,re,time
from pathlib import Path
p=Path('/data/plutonium/console.log')
with p.open('rb') as stream:
 stream.seek(max(0,p.stat().st_size-4194304)); raw=stream.read(4194304).decode('utf-8','replace')
text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',raw); lines=text.splitlines()
portal=[x for x in lines if x.startswith('OUTLANDS_PORTAL_V1|')]
cfg=Path('/data/plutonium/storage/t6/outlands_t6.cfg').read_text()
settings={m.group(1):int(m.group(2)) for m in re.finditer(r'(?m)^set\s+(outlands_[a-z0-9_]+)\s+"?([0-9]+)"?\s*$',cfg)}
catalog=json.loads(Path('/data/plutonium/storage/t6/outlands_rotation.json').read_text())
installed=[m for m in catalog['maps'] if Path('/opt/t6/game/zone/all',m+'.ff').is_file()]
state=json.loads(Path('/data/private/rotation.json').read_text())
print(json.dumps({'log_age_seconds':max(0,time.time()-p.stat().st_mtime),
 'native_errors':len(re.findall(r'(?:terminal\s+)?script(?:\s+(?:compile|runtime))?\s+error|unknown function|unresolved external|critical exception|Exception Code',text,re.I)),
 'portal':portal[-1] if portal else '', 'settings':settings,
 'chat_deliveries':sum(x.startswith('OUTLANDS_CHAT_ACK_V1|') for x in lines),
 'rotation_acks':sum(x.startswith('OUTLANDS_ROTATION_ACK_V1|') for x in lines),
 'catalog':catalog,'installed_maps':installed,
 'history':state['map_history'][-30:],'mode_history':state['mode_history'][-30:], 'pending':state['pending']}))
'''


def lifecycle(details):
    return {name: {'running': d['State']['Running'],
                   'health': d['State'].get('Health', {}).get('Status'),
                   'restarts': d['RestartCount'], 'started_at': d['State']['StartedAt'],
                   'historical_oom_flag': d['State'].get('OOMKilled', False)}
            for name, d in details.items()}


def assess(first, last, before, after, worker=None, chat_mode=None):
    """Pure health policy, separate from collection and historical warnings."""
    excluded = {'ollama': 'chat_mode_fallback'} if chat_mode == 'fallback' else {}
    checks = {name + '_running': row['running'] for name, row in after.items()
              if name not in excluded}
    checks.update({name + '_healthy': row['health'] == 'healthy'
                   for name, row in after.items()
                   if row['health'] is not None and name not in excluded})
    if chat_mode == 'ollama':
        checks['ollama_running'] = bool(after.get('ollama', {}).get('running'))
        checks['ollama_healthy'] = after.get('ollama', {}).get('health') == 'healthy'
    if chat_mode is not None:
        checks['chat_mode_valid'] = chat_mode in ('ollama', 'fallback')
    checks['no_restarts_during_observation'] = set(before) == set(after) and all(
        name in before and (row['restarts'], row['started_at']) ==
        (before[name]['restarts'], before[name]['started_at']) for name, row in after.items())
    checks['no_native_errors_in_log_window'] = last['native_errors'] == 0
    checks['fresh_native_telemetry'] = bool(last['match']) and last['log_age_seconds'] < 30
    a, b = first['match'], last['match']
    checks['match_advancing'] = bool(a and b and any(a[key] != b[key] for key in ('clock', 'map', 'mode')))
    if b:
        settings = last['settings']
        target = settings.get('outlands_bot_fill', 16) if b['humans'] else settings.get('outlands_bot_idle_fill', 0)
        checks['configured_population'] = b['humans'] + b['bots'] == max(b['humans'], target)
        if b['mode'] != 'dm':
            checks['teams_balanced'] = abs(b['teams'][0]['players'] - b['teams'][1]['players']) <= 1
    enabled = {k for k, v in last['catalog']['modes'].items() if v > 0}
    checks['supported_modes_only'] = bool(enabled) and enabled <= MODES
    checks['rotation_ready'] = bool(last['installed_maps'] and last['pending'] and last['rotation_acks'])
    if worker is not None:
        # A model fallback is a successful worker result. Startup messages can
        # scroll outside a bounded log tail, and are not current liveness proof.
        checks['chat_worker_no_traceback'] = worker['tracebacks'] == 0
        checks['chat_recent_submissions'] = worker['model_submissions'] + worker['fallback_submissions'] > 0
        checks['native_chat_delivered'] = worker.get('native_deliveries', 0) > 0
    warnings = []
    for name, row in after.items():
        if row['restarts']:
            warnings.append(name + ': historical restart count; inspect lifecycle history for cause')
        if row['historical_oom_flag']:
            warnings.append(name + ': historical OOM flag; not evidence of a new memory kill')
    missing = sorted(set(last['catalog']['maps']) - set(last['installed_maps']))
    return {'checks': checks, 'warnings': warnings, 'excluded_optional_services': excluded,
            'excluded_uninstalled_maps': missing,
            'chat_deliveries_observed_in_window': max(0, last['chat_deliveries'] - first['chat_deliveries']),
            'passed': all(checks.values())}


class Docker:
    def call(self, *args):
        result = subprocess.run(['bash', str(ROOT / 'hosting/docker.sh'), *args],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Read-only container operation unavailable: ' + args[0])
        return result.stdout


def inspect_services(docker, project):
    result = {}
    for name in SERVICES:
        try:
            result[name] = json.loads(docker.call('inspect', project + '-' + name + '-1'))[0]
        except RuntimeError:
            if name in ('t6', 'tailscale'):
                raise
    return result


def worker_activity(text):
    return {'model_submissions': text.count('Bot response submitted (ollama)'),
            'fallback_submissions': text.count('Bot response submitted (fallback)'),
            'tracebacks': text.count('Traceback (most recent call last)')}


def native_chat_activity(text, now=None):
    """Count recent native receipts; discard timestamps and all receipt fields.

    Input is Docker's bounded, timestamped log window. An anchored marker keeps
    quoted player messages out; a timestamp check cannot credit an old receipt
    carried into a fixture or log response. The short observation-window delta
    remains informational because valid chat can be quieter than that window.
    """
    now = time.time() if now is None else now
    deliveries = 0
    for raw in text.splitlines():
        line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', raw)
        timestamp, separator, payload = line.partition(' ')
        if (not separator or not payload.startswith('OUTLANDS_CHAT_ACK_V1|')
                or len(payload) > 192 or len(payload.split('|')) != 5
                or any(not field for field in payload.split('|')[1:])):
            continue
        try:
            observed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if observed.tzinfo is None or not 0 <= now - observed.timestamp() <= 1800:
                continue
        except (ValueError, OverflowError):
            continue
        deliveries += 1
    return {'native_deliveries': deliveries}


def model_memory_events(docker, details):
    """Read only aggregate counters, never container environment or process data."""
    if not details or not details['State']['Running']:
        return None
    try:
        text = docker.call('exec', details['Id'], 'sh', '-c',
                           'cat /sys/fs/cgroup/memory.events')
        rows = [line.split() for line in text.splitlines()]
        if (not rows or any(len(row) != 2 or
                not re.fullmatch(r'[a-z_]+', row[0]) or
                not re.fullmatch(r'[0-9]+', row[1]) for row in rows)):
            return None
        values = {key: int(value) for key, value in rows}
        fields = ('max', 'oom', 'oom_kill')
        if len(values) != len(rows) or not set(fields) <= values.keys():
            return None
        return {key: values[key] for key in fields}
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        return None


def assess_model_memory(before, after):
    """A healthy model container can still have killed its inference child."""
    result = {'checks': {}, 'warnings': [],
              'health': {'before': before, 'after': after, 'delta': None}}
    if before is None or after is None:
        result['warnings'].append('ollama: cgroup memory-event counters unavailable for the observation window')
        return result
    delta = {key: after[key] - before[key] for key in ('max', 'oom', 'oom_kill')}
    result['health']['delta'] = delta
    continuous = all(value >= 0 for value in delta.values())
    result['checks']['ollama_memory_counters_continuous'] = continuous
    result['checks']['ollama_no_new_oom_kills'] = continuous and delta['oom_kill'] == 0
    if before['oom_kill']:
        result['warnings'].append('ollama: historical cgroup OOM kills precede this observation window')
    if not continuous:
        result['warnings'].append('ollama: cgroup memory-event counters reset during observation')
    elif delta['oom_kill']:
        result['warnings'].append('ollama: new cgroup OOM kills during observation; container health alone is insufficient')
    elif delta['oom'] or delta['max']:
        result['warnings'].append('ollama: new cgroup memory-limit pressure during observation; review headroom')
    return result


def http_ok(url, anonymous=False):
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(url, timeout=8) as response:
            return response.status == 200 and not anonymous
    except HTTPError as error:
        return anonymous and error.code == 401
    except OSError:
        return False


def challenge_activity(value):
    """Validate an operator aggregate before including it in a private audit."""
    fields = {'schema','scope','status','pending','acknowledged','oldest_pending_at',
              'oldest_pending_age_seconds','pending_age_unknown','last_successful_delivery_at',
              'last_poll_at','poll_age_seconds','blocked_reason','blocked_since'}
    valid = isinstance(value,dict) and set(value) == fields
    if valid:
        valid = (value['schema'] == 1 and value['scope'] == 'operator_aggregate'
                 and value['status'] in ('starting','blocked','backlogged','idle')
                 and value['blocked_reason'] in (None,'log_continuity','log_unavailable','state_unavailable')
                 and all(type(value[k]) is int and value[k] >= 0 for k in ('pending','acknowledged','pending_age_unknown'))
                 and value['pending_age_unknown'] <= value['pending'])
        for key in ('oldest_pending_at','oldest_pending_age_seconds','last_successful_delivery_at','last_poll_at','poll_age_seconds','blocked_since'):
            number=value[key]
            valid = valid and (number is None or type(number) in (float,int) and math.isfinite(number) and number >= 0)
    if not valid:
        return {'checks':{'challenge_delivery_available':False},'warnings':['challenge: aggregate health unavailable'],'health':None}
    checks={'challenge_delivery_available':True,
            'challenge_ingestion_fresh':value['poll_age_seconds'] is not None and value['poll_age_seconds'] <= 120,
            'challenge_log_continuity':value['blocked_reason'] is None and value['status'] != 'blocked',
            'challenge_delivery_within_window':not value['pending'] or value['pending_age_unknown'] == 0 and value['oldest_pending_age_seconds'] is not None and value['oldest_pending_age_seconds'] <= 300}
    warnings=[]
    if value['pending']:warnings.append('challenge: pending deliveries; inspect age and account-service availability')
    if value['pending_age_unknown']:warnings.append('challenge: historical pending age is unknown; inspect retained state')
    return {'checks':checks,'warnings':warnings,'health':dict(value)}


def collect(docker, project, interval):
    start = inspect_services(docker, project)
    memory_before = model_memory_events(docker, start.get('ollama'))
    def sample():
        value = json.loads(docker.call('exec', start['t6']['Id'], 'python3', '-c', GAME_PROBE))
        names = {k: v['name'] for k, v in value['catalog']['maps'].items()}
        value['match'] = parse_snapshot(value.pop('portal'), names)
        return value
    first = sample()
    time.sleep(interval)
    last = sample()
    end = inspect_services(docker, project)
    memory_after = model_memory_events(docker, end.get('ollama'))
    chat_mode = None
    if 'chat' in end:
        # Read only this allowlisted setting; never copy the environment into
        # the report. The worker's default generation mode is ollama.
        modes = [entry.split('=', 1)[1] for entry in end['chat']['Config']['Env']
                 if entry.startswith('T6_CHAT_MODE=')]
        chat_mode = modes[-1] if modes else 'ollama'
        if chat_mode not in ('ollama', 'fallback'):
            chat_mode = 'invalid'
    worker = None
    if 'chat' in end:
        # Docker logs includes application stderr. Do not return raw log text.
        result = subprocess.run(['bash', str(ROOT / 'hosting/docker.sh'), 'logs', '--timestamps', '--since', '30m',
                                 '--tail', '5000', end['chat']['Id']], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Read-only worker log check unavailable')
        worker = worker_activity(result.stdout + result.stderr)
        result = subprocess.run(['bash', str(ROOT / 'hosting/docker.sh'), 'logs', '--timestamps', '--since', '30m',
                                 '--tail', '5000', end['t6']['Id']], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('Read-only native receipt log check unavailable')
        worker.update(native_chat_activity(result.stdout + result.stderr))
    result = assess(first, last, lifecycle(start), lifecycle(end), worker, chat_mode)
    checks = result['checks']
    if (start.get('ollama', {}).get('State', {}).get('Running') or
            end.get('ollama', {}).get('State', {}).get('Running')):
        memory = assess_model_memory(memory_before, memory_after)
        checks.update(memory['checks'])
        result['warnings'].extend(memory['warnings'])
        result['model_memory_events'] = memory['health']
    else:
        result['model_memory_events'] = {'status': 'not_running'}
    all_running = json.loads(docker.call('inspect', *docker.call('ps', '-q').split()))
    checks['one_hosted_game_instance'] = sum(
        d['HostConfig'].get('NetworkMode') == 'container:' + end['tailscale']['Id'] and
        any(e == 'T6_MODE=lan' for e in d['Config']['Env']) for d in all_running) == 1
    paths = {p.relative_to(ROOT).as_posix(): '/opt/t6/mod/' + p.relative_to(ROOT).as_posix()
             for p in public_files() if p.relative_to(ROOT).parts[0] == 'storage'}
    paths['hosting/entrypoint.py'] = '/opt/t6/entrypoint.py'
    expected = {k: hashlib.sha256((ROOT / k).read_bytes()).hexdigest() for k in paths}
    hash_code = ('import hashlib,json;from pathlib import Path;p=' + repr(paths) +
                 ';print(json.dumps({k:hashlib.sha256(Path(v).read_bytes()).hexdigest() if Path(v).is_file() else None for k,v in p.items()}))')
    actual = json.loads(docker.call('exec', end['t6']['Id'], 'python3', '-c', hash_code))
    operator = {'storage/t6/outlands_t6.cfg', 'storage/t6/outlands_rotation.json'}
    differences = [k for k in paths if expected[k] != actual.get(k)]
    checks['immutable_game_code_matches_source'] = not set(differences) - operator
    result['operator_template_differences'] = sorted(set(differences) & operator)
    installed = {k: '/data/plutonium/' + k for k in paths if k.startswith('storage/') and k not in operator}
    hash_code = hash_code.replace(repr(paths), repr(installed), 1)
    actual = json.loads(docker.call('exec', end['t6']['Id'], 'python3', '-c', hash_code))
    checks['installed_game_code_matches_source'] = all(actual.get(k) == expected[k] for k in installed)
    if 'accounts' in end:
        env = dict(x.split('=', 1) for x in end['accounts']['Config']['Env'] if '=' in x)
        origin = env.get('OUTLANDS_ACCOUNT_ORIGIN', '')
        if not origin and 'account-agent' in end:
            env = dict(x.split('=', 1) for x in end['account-agent']['Config']['Env'] if '=' in x)
            origin = env.get('OUTLANDS_ACCOUNT_ORIGIN', '')
        checks['account_https_health'] = origin.startswith('https://') and http_ok(origin + '/healthz')
        checks['account_anonymous_rejected'] = origin.startswith('https://') and http_ok(origin + '/api/me', True)
    if end.get('ollama', {}).get('State', {}).get('Running'):
        try:
            stats = json.loads(docker.call('stats', '--no-stream', '--format', '{{json .}}', end['ollama']['Id']))
            percent = stats.get('MemPerc', '')
            if not re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]+)?%', percent):
                raise ValueError('Unavailable resource measurement')
            result['model_memory_percent'] = float(percent[:-1])
            if result['model_memory_percent'] >= 90:
                result['warnings'].append('ollama: current memory usage is at least 90 percent of its limit; review headroom')
        except (ValueError, RuntimeError):
            result['warnings'].append('ollama: current memory measurement unavailable')
    if 'challenge-worker' in end:
        try:
            raw = json.loads(docker.call('exec',end['challenge-worker']['Id'],'python3','/opt/outlands-chat/challenge_delivery.py','--health'))
        except (RuntimeError,ValueError):raw=None
        challenge = challenge_activity(raw)
        checks.update(challenge['checks']);result['warnings'].extend(challenge['warnings'])
        result['challenge_delivery'] = challenge['health']
    else:
        result['challenge_delivery'] = {'status':'not_installed','scope':'operator_aggregate'}
    result.update({'passed': all(checks.values()), 'scope': 'live_readonly',
                   'created_utc': datetime.now(timezone.utc).isoformat(),
                   'services': lifecycle(end), 'worker_recent_activity': worker,
                   'chat_mode': chat_mode,
                   'match': last['match'], 'recent_maps': last['catalog']['recent_maps'],
                   'installed_map_count': len(last['installed_maps']),
                   'enabled_modes': sorted(k for k, v in last['catalog']['modes'].items() if v > 0),
                   'map_history': last['history'], 'mode_history': last['mode_history'],
                   'external_client_connection_verified': False,
                   'game_state_modified': False, 'live_server_restarted': False})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='outlands-t6')
    parser.add_argument('--seconds', type=int, default=15)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,60}', args.project) or not 5 <= args.seconds <= 30:
        parser.error('Expected safe Compose project and a 5-30 second window')
    directory = args.report_dir.absolute()
    if directory.exists() or any(p.is_symlink() for p in (directory, *directory.parents)):
        parser.error('Choose a fresh private report directory')
    directory.mkdir(parents=True, mode=0o700)
    try:
        result = collect(Docker(), args.project, args.seconds)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        result = {'passed': False, 'error': 'Audit unavailable; no live state was changed'}
    path = directory / 'report.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    path.chmod(0o600)
    print(json.dumps({'passed': result['passed'], 'checks': result.get('checks', {}),
                      'warnings': result.get('warnings', []), 'report': str(path)}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
