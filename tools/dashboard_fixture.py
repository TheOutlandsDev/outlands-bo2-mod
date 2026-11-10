#!/usr/bin/env python3
"""Loopback-only synthetic browser fixture. Never opens accounts or game state."""
import argparse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]/'accounts/web'
SCENARIOS = frozenset(('in-progress','complete','disabled','unlinked','expired','offline','guest'))


def snapshot(scenario):
    count = 25 if scenario == 'complete' else 12
    value = {'id':'synthetic_account_001','display_name':'SyntheticPlayer','revision':1,'native_save_sync':False,
             'profiles':[] if scenario == 'unlinked' else [{'server':'synthetic_server_001',
                'live':scenario != 'expired','observed_at':None,'stats':{'rank_xp':12345,'level':24}}],
             'fixture':True}
    if scenario != 'disabled':
        value['custom_challenges'] = [{'challenge':'outlands_dusk_an94_headshots','weapon':'an94_mp',
            'camo':'outlands_dusk','scope':'outlands_account','revision':1,'progress':count,
            'target':25,'completed':count == 25,'reward_ready':False}]
    return value


class Fixture(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,raw,kind='application/json',cookie=None):
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Outlands-Fixture','synthetic-only')
        # Only this synthetic fixture allows same-origin viewport framing.
        # The real account service retains frame-ancestors 'none'.
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-src 'self'; base-uri 'none'; frame-ancestors 'self'; form-action 'self'")
        if cookie:self.send_header('Set-Cookie','outlands_fixture='+cookie+'; Path=/; HttpOnly; SameSite=Strict')
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path == '/viewport':
            html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Synthetic 390px career viewport</title></head>
<body><p>Browser layout fixture / synthetic data only / 390px viewport</p>
<iframe src="/fixture/in-progress" width="390" height="900" title="Synthetic mobile career viewport"></iframe></body></html>'''
            return self.reply(200,html.encode(),'text/html; charset=utf-8')
        if self.path.startswith('/fixture/') and self.path[9:] in SCENARIOS:
            # Scenario choice changes only this fixture's non-sensitive cookie.
            return self.reply(200,(WEB/'index.html').read_bytes(),'text/html; charset=utf-8',self.path[9:])
        if self.path == '/api/me':
            try:cookie=SimpleCookie(self.headers.get('Cookie',''));scenario=cookie['outlands_fixture'].value if 'outlands_fixture' in cookie else 'in-progress'
            except Exception:scenario='guest'
            if scenario not in SCENARIOS:scenario='guest'
            if scenario in ('guest','offline'):
                return self.reply(401 if scenario == 'guest' else 503,json.dumps({'error':'Sign-in required' if scenario == 'guest' else 'Fixture unavailable'}).encode())
            return self.reply(200,json.dumps(snapshot(scenario)).encode())
        files={'/':('index.html','text/html'),'/career.js':('career.js','text/javascript'),
               '/account.js':('account.js','text/javascript'),'/app.css':('app.css','text/css')}
        if self.path in files:
            name,kind=files[self.path];return self.reply(200,(WEB/name).read_bytes(),kind+'; charset=utf-8')
        self.reply(404,b'{}')
    def do_POST(self):
        if self.path == '/api/logout':return self.reply(200,b'{"signed_out":true}',cookie='guest')
        self.reply(405,b'{"error":"Synthetic fixture is read-only"}')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',action='store_true')
    parser.add_argument('--port',type=int,default=18089);args=parser.parse_args()
    if not 1024 <= args.port <= 65535:parser.error('Choose an unprivileged loopback port')
    if not args.run:print('Plan: synthetic-only localhost browser fixture; no live accounts, OAuth or game access');return
    with ThreadingHTTPServer(('127.0.0.1',args.port),Fixture) as server:
        print('Synthetic dashboard fixture: http://127.0.0.1:'+str(args.port),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass


if __name__ == '__main__':main()
