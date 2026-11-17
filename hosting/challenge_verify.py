#!/usr/bin/env python3
"""Disposable native challenge exclusion/transport check. Never invents humans."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hosting.backend_verify import (Docker, ROOT, LABEL, FAILURE, NATIVE_FAILURE, ANSI,
                                    Case, config_for, parse_samples, assess,
                                    require_map_asset, cleanup_resources)


def assess_guards(text):
    rows = []
    bad = 0
    for line in ANSI.sub('', text).splitlines():
        if not line.startswith('OUTLANDS_CHALLENGE_GUARD_V1|'):
            continue
        fields = line.split('|')[1:]
        if len(fields) != 6 or any(not re.fullmatch(r'[0-9]{1,9}', x) for x in fields):
            bad += 1; continue
        values = list(map(int, fields))
        if rows and (values[1] < rows[-1][1] or values[2] < rows[-1][2]):
            bad += 1
        rows.append(values)
    settled = [row for row in rows if row[5] == 16]
    passed = (not bad and len(settled) >= 2 and rows[-1][1] > 0
              and all(registered == 1 and deaths == rejected and emitted == 0 and base == 1
                      and 0 <= excluded <= 16 and (deaths == 0 or excluded == 16)
                      for registered, deaths, rejected, emitted, base, excluded in rows))
    return {'passed': passed, 'observations': len(rows), 'real_native_deaths': rows[-1][1] if rows else 0,
            'human_awards_verified': False, 'real_client_acceptance': 'pending',
            'reason': None if passed else 'Incomplete native callback/bot-exclusion evidence'}


def run(image, worker_image, case, seconds, directory, accounts=False):
    docker = Docker(ROOT / 'hosting/docker.sh')
    require_map_asset(docker, image, case)
    resource = 'outlands-challenge-' + uuid.uuid4().hex
    volume, ledger = resource + '-state', resource + '-ledger'
    container = worker = logs = ''
    volumes = []
    report = {'passed': False, 'network_mode': 'none', 'live_state': False,
              'human_clients': False, 'published_ports': False}
    try:
        for name in (volume, ledger):
            docker.call('volume', 'create', '--label', LABEL + '=1', name); volumes.append(name)
        token = secrets.token_hex(32)
        cfg = config_for(case, seconds, False, False)
        cfg += '\nset outlands_challenges 1\nset outlands_challenge_token "' + token + '"\n'
        cfg += 'set outlands_challenge_accounts ' + str(int(accounts)) + '\n'
        payload = {'cfg': cfg, 'token': token,
                   'server_credential': secrets.token_urlsafe(32),
                   'files': {'outlands_backend_verification.gsc': (ROOT/'hosting/verification.gsc').read_text(),
                             'outlands_challenge_preview.gsc': (ROOT/'hosting/challenge_adapter.gsc').read_text(),
                             'outlands_challenge_probe.gsc': (ROOT/'hosting/challenge_probe.gsc').read_text()}}
        report['injected_source_sha256'] = {name: hashlib.sha256(value.encode()).hexdigest()
                                             for name, value in payload['files'].items()}
        seed = """import json,sys
from pathlib import Path
x=json.load(sys.stdin);p=Path('/data/plutonium/storage/t6');(p/'scripts/mp').mkdir(parents=True)
(p/'outlands_t6.cfg').write_text(x['cfg'])
for name,value in x['files'].items():(p/'scripts/mp'/name).write_text(value)
private=Path('/data/private');private.mkdir(mode=0o700)
key=private/'challenge_token';key.write_text(x['token']);key.chmod(0o600)
server=private/'challenge_server_credential';server.write_text(x['server_credential']);server.chmod(0o600)
"""
        docker.call('run', '--rm', '-i', '--network', 'none', '--cap-drop', 'ALL',
                    '-v', volume+':/data', '--entrypoint', 'python3', image, '-c', seed,
                    input_text=json.dumps(payload))
        container = docker.call('run', '-d', '--name', resource, '--label', LABEL+'=1',
                                '--network', 'none', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                                '--cpus', '2', '--memory', '2g', '-e', 'T6_MODE=lan', '-e', 'T6_BIND_IP=127.0.0.1',
                                '-e', 'T6_PORT=14977', '-e', 'T6_ACCOUNTS_ENABLED='+str(int(accounts)), '-v', volume+':/data', image)
        command = ['/opt/outlands-chat/challenge_native.py', '--run']
        if accounts:
            command = ['/opt/outlands-chat/challenge_delivery.py', '--run',
                       '--account-api', 'http://127.0.0.1:8087', '--account-origin', 'https://accounts.example.invalid',
                       '--server-credential', '/data/private/challenge_server_credential', '--port', '14977']
        worker = docker.call('run', '-d', '--name', resource+'-worker', '--label', LABEL+'=1',
                             '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                             '--security-opt', 'no-new-privileges:true', '--memory', '128m',
                             '-v', volume+':/data:ro', '-v', ledger+':/challenges',
                             '--entrypoint', 'python3', worker_image, *command)
        for name in (container, worker):
            detail = json.loads(docker.call('inspect', name))[0]
            if detail['HostConfig']['NetworkMode'] != 'none' or detail['HostConfig'].get('PortBindings'):
                raise RuntimeError('Challenge test isolation failed')
        report['game_image'] = json.loads(docker.call('inspect', container))[0]['Image']
        report['worker_image'] = json.loads(docker.call('inspect', worker))[0]['Image']
        code = "import hashlib,json;from pathlib import Path;print(json.dumps({n:hashlib.sha256(Path('/opt/outlands-chat',n).read_bytes()).hexdigest() for n in ('challenge_native.py','camo_challenge.py','challenge_delivery.py')}))"
        actual = json.loads(docker.call('exec', worker, 'python3', '-c', code))
        report['worker_code_matches_source'] = all(value == hashlib.sha256((ROOT/'ai'/name).read_bytes()).hexdigest()
                                                   for name, value in actual.items())
        start = time.monotonic()
        canary_sent = False
        while time.monotonic()-start < 180+seconds:
            logs = docker.call('logs', container, check=False)
            if accounts and not canary_sent and 'OUTLANDS_CHALLENGE_READY_V1' in logs:
                script = """import socket
from pathlib import Path
secret=Path('/data/private/outlands_rcon_password').read_text().strip()
value='canary_challenge_request|0|synthetic_session_001|'+'a'*64+'|120'
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
 sock.sendto(b'\\xff\\xff\\xff\\xffrcon '+secret.encode()+b' set outlands_challenge_grant "'+value.encode()+b'"',('127.0.0.1',14977))
"""
                docker.call('exec', container, 'python3', '-c', script)
                canary_sent = True
            if FAILURE.search(logs) or NATIVE_FAILURE.search(logs): break
            if any(row['kind'] == 'complete' for row in parse_samples(logs)): break
            if docker.call('inspect', '--format', '{{.State.Running}}', container) != 'true': break
            time.sleep(2)
        report['native_gameplay'] = assess(parse_samples(logs), case, False)
        report['guards'] = assess_guards(logs)
        worker_logs = docker.call('logs', worker, check=False)
        marker = 'Outlands account challenge follower ready; durable native events only' if accounts else 'Outlands challenge follower ready; native human sessions only'
        report['worker_ready'] = (marker in worker_logs
                                  and 'Traceback' not in worker_logs)
        script = "from pathlib import Path;print(Path('/challenges/progress.json').exists())"
        report['no_bot_reward_ledger'] = docker.call('exec', worker, 'python3', '-c', script) == 'False'
        docker.call('restart', '-t', '5', worker)
        time.sleep(2)
        report['no_bot_reward_after_worker_restart'] = docker.call('exec', worker, 'python3', '-c', script) == 'False'
        report['account_mode'] = accounts
        if accounts:
            values = re.findall(r'(?m)^OUTLANDS_CHALLENGE_ACCOUNT_GUARD_V1\|([0-9]+)\|([0-9]+)\|([0-9]+)\|([0-9]+)\s*$', ANSI.sub('', logs))
            report['account_guards'] = bool(values) and all(row == ('6','0','0','0') for row in values)
            report['grant_canary_consumed_without_owner'] = 'OUTLANDS_CHALLENGE_BIND_ACK_V1|canary_challenge_request' in logs
            script = "import sqlite3,json;db=sqlite3.connect('/challenges/delivery.sqlite3');print(json.dumps(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]))"
            report['no_bot_events_staged'] = docker.call('exec', worker, 'python3', '-c', script) == '0'
            health = json.loads(docker.call('exec',worker,'python3','/opt/outlands-chat/challenge_delivery.py','--health'))
            report['delivery_health_recovered'] = (health.get('scope') == 'operator_aggregate'
                and health.get('status') == 'idle' and health.get('pending') == 0
                and health.get('blocked_reason') is None and health.get('poll_age_seconds') is not None
                and 0 <= health['poll_age_seconds'] <= 120)
        report['script_error'] = bool(FAILURE.search(logs) or NATIVE_FAILURE.search(logs))
        report['passed'] = all((report['native_gameplay']['passed'], report['guards']['passed'],
                                report['worker_code_matches_source'],
                                report['worker_ready'], report['no_bot_reward_ledger'],
                                report['no_bot_reward_after_worker_restart'], not report['script_error']))
        if accounts:
            report['passed'] = report['passed'] and all(report[k] for k in ('account_guards','grant_canary_consumed_without_owner','no_bot_events_staged','delivery_health_recovered'))
        return report
    finally:
        (directory/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        cleanup_resources(docker, case, directory, logs, container, worker, volumes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--accounts-preview', action='store_true')
    parser.add_argument('--image', required=True)
    parser.add_argument('--worker-image', required=True)
    parser.add_argument('--case', default='mp_raid:tdm')
    parser.add_argument('--seconds', type=int, default=90)
    parser.add_argument('--report-dir', type=Path)
    args = parser.parse_args()
    if not 60 <= args.seconds <= 180 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]{0,180}', x)
                                           for x in (args.image, args.worker_image)):
        parser.error('Expected safe local images and 60-180 seconds')
    case = Case.parse(args.case)
    if not args.run:
        print('Plan: network none, disposable state, native bot exclusions only; human awards pending')
        return 0
    directory = (args.report_dir or ROOT/'hosting/logs'/('challenge-'+uuid.uuid4().hex)).absolute()
    if directory.exists() or any(p.is_symlink() for p in (directory, *directory.parents)):
        parser.error('Choose a fresh private report directory')
    directory.mkdir(parents=True, mode=0o700)
    result = run(args.image, args.worker_image, case, args.seconds, directory, args.accounts_preview)
    print('PASS: native challenge guards; human acceptance pending' if result['passed'] else 'FAIL: inspect private report')
    return 0 if result['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
