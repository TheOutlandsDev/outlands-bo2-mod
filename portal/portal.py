#!/usr/bin/env python3
"""Read-only Tailscale portal and a separate, least-privilege snapshot exporter."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
MARKER = 'OUTLANDS_PORTAL_V1|'
MODES = {'tdm': 'Team Deathmatch', 'dm': 'Free-for-All', 'conf': 'Kill Confirmed',
         'dom': 'Domination', 'koth': 'Hardpoint', 'hq': 'Headquarters',
         'ctf': 'Capture the Flag', 'dem': 'Demolition'}
KINDS = {'team_eliminations': 'Team eliminations', 'combined_score': 'Combined score',
         'team_points': 'Match points', 'none': 'Awaiting contract'}
ROLES = {'rusher', 'assault', 'objective', 'support', 'marksman'}
MAX_BYTES = 524288
FRESH_SECONDS = 20


def integer(raw, low, high):
    if not isinstance(raw, str) or not re.fullmatch(r'0|[1-9][0-9]{0,9}', raw):
        raise ValueError('invalid integer')
    number = int(raw)
    if not low <= number <= high:
        raise ValueError('integer out of range')
    return number


def parse_snapshot(line, maps):
    """Accept only an entire native aggregate record; never embedded chat text."""
    if len(line) > 1024:
        return None
    clean = ANSI.sub('', line).strip('\r\n')
    if not clean.startswith(MARKER):
        return None
    fields = clean[len(MARKER):].split('|')
    if len(fields) != 19:
        return None
    map_id, mode, state = fields[:3]
    if map_id not in maps or mode not in MODES or state not in ('playing', 'waiting', 'ended'):
        return None
    try:
        clock = integer(fields[3], 0, 2147483647)
        humans, bots, allies, axis = [integer(x, 0, 18) for x in fields[4:8]]
        if humans + bots > 18 or allies + axis > humans + bots:
            return None
        scores = [integer(x, 0, 100000000) for x in fields[8:10]]
        seconds = integer(fields[10], 0, 300)
        contracts = []
        for offset, team in ((11, 'allies'), (15, 'axis')):
            kind = fields[offset]
            if kind not in KINDS:
                return None
            goal, progress = [integer(x, 0, 100000000) for x in fields[offset+1:offset+3]]
            complete = integer(fields[offset+3], 0, 1)
            if (kind == 'none' and (goal or progress or complete)) or (kind != 'none' and goal < 1):
                return None
            contracts.append({'team': team, 'kind': kind, 'label': KINDS[kind],
                              'goal': goal, 'progress': progress, 'complete': bool(complete)})
    except ValueError:
        return None
    return {'map': map_id, 'map_name': maps[map_id], 'mode': mode, 'mode_name': MODES[mode],
            'state': state, 'clock': clock, 'humans': humans, 'bots': bots,
            'teams': [{'id': 'allies', 'name': 'Allies', 'players': allies, 'score': scores[0]},
                      {'id': 'axis', 'name': 'Axis', 'players': axis, 'score': scores[1]}],
            'contract_seconds': seconds, 'contracts': contracts}


def load_json(path, limit=MAX_BYTES):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('invalid data file')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('oversized data file')
    return json.loads(raw)


def rival_view(state, profiles):
    """Export fictional aliases and bounded aggregate counters, never sessions."""
    if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('careers'), dict):
        return []
    result = []
    for alias, profile in profiles.items():
        if not re.fullmatch(r'[A-Za-z0-9 ._~-]{1,24}', alias):
            continue
        record = state['careers'].get(alias)
        if not isinstance(record, dict):
            continue
        values = {k: record.get(k) for k in ('xp', 'kills', 'deaths', 'observed_rounds')}
        if any(type(v) is not int or not 0 <= v <= 1000000000 for v in values.values()):
            continue
        step = min(values['xp'], 11*55*5000-1)//5000
        role = record.get('role', profile.get('role', 'assault'))
        if role not in ROLES:
            role = 'assault'
        result.append({'alias': alias, 'role': role, 'level': step % 55+1,
                       'prestige': min(10, step//55), 'kills': values['kills'],
                       'deaths': values['deaths'], 'rounds': values['observed_rounds']})
    return sorted(result, key=lambda r: (-r['prestige'], -r['level'], r['alias']))[:64]


class LogFollower:
    """Start at EOF. Old log contents cannot become new live telemetry."""
    def __init__(self, path):
        self.path, self.identity, self.offset, self.partial = Path(path), None, 0, b''
        self.first = True

    def poll(self):
        try:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if self.first:
                self.first = False
                self.identity, self.offset = identity, stat.st_size
                return []
            if identity != self.identity or stat.st_size < self.offset:
                self.identity, self.offset, self.partial = identity, 0, b''
            with self.path.open('rb') as stream:
                if stat.st_size-self.offset > MAX_BYTES:
                    self.offset, self.partial = stat.st_size-MAX_BYTES, b''
                    stream.seek(self.offset)
                    stream.readline()  # discard a partial leading line
                else:
                    stream.seek(self.offset)
                raw = stream.read(MAX_BYTES)
                self.offset = stream.tell()
            lines = (self.partial+raw).split(b'\n')
            self.partial = lines.pop()[-4096:]
            return [x.decode('utf-8', 'replace') for x in lines if len(x) <= 1024]
        except OSError:
            self.first = False
            return []


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(',', ':'), allow_nan=False).encode()
    if len(raw) > MAX_BYTES:
        raise ValueError('snapshot too large')
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.snapshot-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def export_loop():
    catalog = load_json(ROOT/'maps.json')['maps']
    maps = {key: value['name'] for key, value in catalog.items()}
    profiles = load_json(ROOT/'personalities.json')['profiles']
    follower = LogFollower(Path(os.environ.get('PORTAL_LOG', '/data/plutonium/console.log')))
    destination = Path(os.environ.get('PORTAL_SNAPSHOT', '/public/status.json'))
    endpoint = os.environ.get('PORTAL_JOIN', '')
    if not re.fullmatch(r'[a-zA-Z0-9.:-]{1,255}:[0-9]{1,5}', endpoint):
        raise ValueError('PORTAL_JOIN must contain the private host and game port')
    latest, observed = None, None
    while True:
        for line in follower.poll():
            sample = parse_snapshot(line, maps)
            if sample:
                latest, observed = sample, time.time()
        try:
            rivals = rival_view(load_json(Path('/rivals/careers.json')), profiles)
        except (OSError, ValueError, TypeError):
            rivals = []
        now = time.time()
        live = observed is not None and 0 <= now-observed <= FRESH_SECONDS
        atomic_json(destination, {'schema': 1, 'generated_at': now,
                    'observed_at': observed, 'live': live, 'match': latest if live else None,
                    'join_command': 'connect '+endpoint, 'rivals': rivals,
                    'rivals_scope': 'Persistent fictional AI careers; not a live player roster'})
        time.sleep(2)


class PortalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, *args, **kwargs):
        self.slots = threading.BoundedSemaphore(24)
        super().__init__(*args, **kwargs)
    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'Outlands'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(3)
    def log_message(self, *args):
        pass  # No client addresses, request paths or browser identities in logs.
    def respond(self, status, raw, content_type='application/json; charset=utf-8', head=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.end_headers()
        if not head:
            self.wfile.write(raw)
    def get(self, head=False):
        path = self.path.split('?', 1)[0]
        if path == '/healthz':
            return self.respond(200, b'{"service":"outlands-portal","read_only":true}', head=head)
        if path == '/api/status':
            try:
                data = load_json(Path(os.environ.get('PORTAL_SNAPSHOT', '/public/status.json')))
                stamp = data.get('generated_at')
                if data.get('schema') != 1 or type(stamp) not in (float, int) or not math.isfinite(stamp) or not 0 <= time.time()-stamp <= FRESH_SECONDS:
                    raise ValueError('stale export')
                return self.respond(200, json.dumps(data, allow_nan=False).encode(), head=head)
            except (OSError, ValueError, TypeError, AttributeError):
                return self.respond(503, b'{"live":false,"error":"Snapshot unavailable"}', head=head)
        files = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.css': ('app.css', 'text/css; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
        if path not in files:
            return self.respond(404, b'{"error":"Not found"}', head=head)
        name, kind = files[path]
        return self.respond(200, (ROOT/'web'/name).read_bytes(), kind, head=head)
    def do_GET(self):
        self.get()
    def do_HEAD(self):
        self.get(True)
    def do_POST(self):
        self.respond(405, b'{"error":"Read only"}')
    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


def serve():
    bind = os.environ.get('PORTAL_BIND', '')
    address = ipaddress.ip_address(bind)
    allowed = ipaddress.ip_network((0x64400000, 10))
    if address.version != 4 or not (address.is_loopback or address in allowed):
        raise ValueError('PORTAL_BIND must be an explicit Tailscale IPv4 or loopback address')
    port = int(os.environ.get('PORTAL_PORT', '8085'))
    if not 1024 <= port <= 65535:
        raise ValueError('Invalid unprivileged port')
    server = PortalServer((bind, port), Handler)
    print('Outlands read-only portal ready', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['serve', 'export'])
    args = parser.parse_args()
    export_loop() if args.mode == 'export' else serve()
