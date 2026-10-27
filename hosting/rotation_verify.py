#!/usr/bin/env python3
"""Verify native weighted map transitions in disposable, offline server state.

Uses locally owned game files. No live state, human identities, public ports,
game assets or raw logs enter the public source package. TDM-only short matches
are an explicit test override; production mode weights and limits are unchanged.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import uuid

try:
    from backend_verify import Docker, ROOT, LABEL, FAILURE, NATIVE_FAILURE, ANSI, Case, cleanup_resources
except ModuleNotFoundError:
    from hosting.backend_verify import Docker, ROOT, LABEL, FAILURE, NATIVE_FAILURE, ANSI, Case, cleanup_resources

ACK = re.compile(r'OUTLANDS_ROTATION_ACK_V1\|([A-Za-z0-9_]{1,60})\|(mp_[a-z0-9_]{1,40})\|(tdm|dom|conf|ctf|dem|hq|koth|dm)\Z')
PROBE = '''main()
{
    if ( !isdedicated() || getdvar( "outlands_rotation_verification" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" )
        return;
    setgametypesetting( "prematchperiod", 0 );
    setgametypesetting( "preroundperiod", 0 );
    setgametypesetting( "scorelimit", 40 );
    setgametypesetting( "timelimit", 2 );
}
init()
{
    if ( getdvar( "outlands_rotation_verification" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" )
        return;
    level waittill( "game_ended" );
    println( "OUTLANDS_ROTATION_END_V1|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) );
}
'''


def receipts(text):
    result = []
    seen = set()
    for line in ANSI.sub('', text).splitlines():
        match = ACK.fullmatch(line.strip())
        if match and match[1] not in seen:
            seen.add(match[1])
            result.append(match.groups())
    return result


def run(image, steps, directory):
    docker = Docker(ROOT / 'hosting/docker.sh')
    resource = 'outlands-rotation-' + uuid.uuid4().hex
    volume = resource + '-state'
    container, created, logs = '', False, ''
    report = {'passed': False, 'network_mode': 'none', 'published_ports': False,
              'human_clients': False, 'live_state': False, 'forced_transitions': 0,
              'natural_transition': False, 'process_restart': False, 'maps': []}
    try:
        docker.call('volume', 'create', '--label', LABEL + '=1', volume)
        created = True
        cfg = (ROOT / 'storage/t6/outlands_t6.cfg').read_text()
        cfg += '\nset outlands_rotation 1\nset outlands_rotation_verification 1\nset outlands_bot_idle_fill 16\n'
        catalog = json.loads((ROOT / 'storage/t6/outlands_rotation.json').read_text())
        catalog['modes'] = {'tdm': 1}
        seed = """import json,sys
from pathlib import Path
x=json.load(sys.stdin);p=Path('/data/plutonium/storage/t6');p.mkdir(parents=True)
(p/'scripts/mp').mkdir(parents=True)
(p/'outlands_t6.cfg').write_text(x['cfg']);(p/'outlands_rotation.json').write_text(json.dumps(x['catalog']))
(p/'scripts/mp/outlands_rotation_verification.gsc').write_text(x['probe'])
"""
        docker.call('run', '--rm', '-i', '--network', 'none', '--cap-drop', 'ALL', '-v', volume + ':/data',
                    '--entrypoint', 'python3', image, '-c', seed,
                    input_text=json.dumps({'cfg': cfg, 'catalog': catalog, 'probe': PROBE}))
        container = docker.call('run', '-d', '--name', resource, '--label', LABEL + '=1', '--network', 'none',
                                '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                                '-e', 'T6_MODE=lan', '-e', 'T6_BIND_IP=127.0.0.1', '-e', 'T6_PORT=14977',
                                '-v', volume + ':/data', image)
        if not re.fullmatch(r'[a-f0-9]{64}', container):
            raise RuntimeError('Invalid disposable container')
        details = json.loads(docker.call('inspect', container))[0]
        if details['HostConfig']['NetworkMode'] != 'none' or details['HostConfig'].get('PortBindings'):
            raise RuntimeError('Rotation test isolation failed')
        report['game_image'] = details['Image']
        def wait_count(count, timeout):
            nonlocal logs
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                logs = docker.call('logs', container, check=False)
                if FAILURE.search(logs) or NATIVE_FAILURE.search(logs):
                    raise RuntimeError('Native rotation test failed')
                if len(receipts(logs)) >= count:
                    return receipts(logs)
                if docker.call('inspect', '--format', '{{.State.Status}}', container) in ('exited', 'dead'):
                    raise RuntimeError('Disposable rotation server exited')
                time.sleep(2)
            raise RuntimeError('Native next-map receipt timed out')
        state_code = "from pathlib import Path;print(Path('/data/private/rotation.json').read_text())"
        def state():
            return json.loads(docker.call('exec', container, 'python3', '-c', state_code))
        first = wait_count(1, 180)
        initial = state()
        report['maps'].append(initial['map_history'][-1])
        # Wait for an actual normal match end and native automatic rotation.
        wait_count(2, 240)
        if 'OUTLANDS_ROTATION_END_V1|' not in logs:
            raise RuntimeError('Normal native match end was not observed')
        report['natural_transition'] = True
        current = state()
        if current['map_history'][-1] != first[-1][1]:
            raise RuntimeError('Native transition differs from the acknowledged next map')
        report['maps'].append(current['map_history'][-1])
        for count in range(3, steps + 1):
            expected = current['pending'][0]
            # Allow normal asset initialization and bot respawning between
            # forced native map_rotate calls; no script-level fake transition.
            time.sleep(10)
            command = """import socket
from pathlib import Path
secret=Path('/data/private/outlands_rcon_password').read_text().strip()
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
 s.sendto(b'\\xff\\xff\\xff\\xffrcon '+secret.encode()+b' map_rotate\\n',('127.0.0.1',14977))
"""
            docker.call('exec', container, 'python3', '-c', command)
            wait_count(count, 120)
            current = state()
            if current['map_history'][-1] != expected:
                raise RuntimeError('Forced transition differs from the acknowledged next map')
            report['maps'].append(current['map_history'][-1])
            report['forced_transitions'] += 1
            print('PASS: native rotation loaded ' + current['map_history'][-1], flush=True)
        if len(set(report['maps'])) != steps:
            raise RuntimeError('Equal-weight deck repeated a map before coverage')
        before = current
        docker.call('restart', '-t', '15', container)
        wait_count(steps + 1, 180)
        after = state()
        if after['map_history'][:-1] != before['map_history'] or after['map_history'][-1] != before['pending'][0]:
            raise RuntimeError('Rotation history or pending selection did not survive process restart')
        report['process_restart'] = True
        report['passed'] = True
        return report
    finally:
        (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        cleanup_resources(docker, Case('mp_rotation', 'tdm'), directory, logs, container, '', [volume] if created else [])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--image', default='outlands-t6:rotation-chat-dev')
    parser.add_argument('--steps', type=int, default=15)
    parser.add_argument('--report-dir', type=Path)
    args = parser.parse_args()
    if not 2 <= args.steps <= 31 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]{0,180}', args.image):
        parser.error('Expected safe local image and 2-31 installed-map steps')
    if not args.run:
        print(json.dumps({'network_mode': 'none', 'live_state': False, 'steps': args.steps,
                          'natural_match_end': True, 'forced_native_rotations': args.steps - 2,
                          'process_restart': True, 'test_mode': 'tdm'}))
        return 0
    directory = (args.report_dir or ROOT / 'hosting/logs' / ('rotation-' + uuid.uuid4().hex)).absolute()
    if directory.exists() or any(p.is_symlink() for p in (directory, *directory.parents)):
        parser.error('Choose a fresh private report directory')
    directory.mkdir(mode=0o700, parents=True)
    try:
        result = run(args.image, args.steps, directory)
        print('PASS: native map deck, natural end and process-restart history' if result['passed'] else 'FAIL: native rotation')
        return 0 if result['passed'] else 1
    except (OSError, ValueError, RuntimeError):
        print('FAIL: native rotation verification; inspect private report and logs')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
