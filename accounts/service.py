#!/usr/bin/env python3
"""Loopback-only personal account service; deploy only behind trusted HTTPS."""
from http.cookies import SimpleCookie,CookieError
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs,urlsplit

try:
    from .store import AccountStore,Refused,BROWSER,BROWSER_SECONDS
    from .google_login import Config,GoogleLogin,LoginRefused,ISSUER
except ImportError:
    from store import AccountStore,Refused,BROWSER,BROWSER_SECONDS
    from google_login import Config,GoogleLogin,LoginRefused,ISSUER

ROOT=Path(__file__).resolve().parent
SESSION_COOKIE='__Host-outlands_session'
LOGIN_COOKIE='__Host-outlands_login'


class AccountServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,address,store,login):
        if address[0]!='127.0.0.1':raise ValueError('Account service requires trusted loopback HTTPS proxy')
        self.store=store;self.login=login;self.host=urlsplit(login.config.origin).netloc
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(address,Handler)
    def process_request(self,request,address):
        if not self.slots.acquire(False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version='Outlands'
    sys_version=''
    def setup(self):super().setup();self.connection.settimeout(5)
    def log_message(self,*args):pass
    def safe_host(self):
        # This backend listens only on loopback. Its HTTPS proxy must preserve
        # the configured Host and not expose a second untrusted ingress route.
        return self.headers.get('Host')==self.server.host
    def send(self,status,value=None,*,raw=None,kind='application/json; charset=utf-8',location=None,cookies=()):
        if raw is None:raw=json.dumps(value,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Strict-Transport-Security','max-age=31536000')
        if location:self.send_header('Location',location)
        for cookie in cookies:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def cookie(self,name):
        raw=self.headers.get('Cookie','')
        if len(raw)>4096:raise Refused('Sign-in required')
        try:jar=SimpleCookie(raw)
        except CookieError:raise Refused('Sign-in required') from None
        return jar[name].value if name in jar else ''
    def state_cookie(self,name,value,seconds):
        return f'{name}={value}; Path=/; Max-Age={seconds}; Secure; HttpOnly; SameSite=Lax'
    def browser(self):return self.cookie(SESSION_COOKIE)
    def payload(self, native=False):
        if not native and ( self.headers.get('Origin')!=self.server.login.config.origin or self.headers.get('X-Outlands-Request')!='1'):
            raise Refused('Same-origin account request required')
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type')!='application/json':raise Refused('JSON request required')
        length=self.headers.get('Content-Length','')
        if not length.isdecimal() or not 1<=int(length)<=2048:raise Refused('Invalid request size')
        value=json.loads(self.rfile.read(int(length)))
        if not isinstance(value,dict):raise Refused('Invalid account request')
        return value
    def do_GET(self):
        if not self.safe_host():return self.send(421,{'error':'Account host mismatch'})
        parsed=urlsplit(self.path);path=parsed.path
        try:
            if path=='/healthz':return self.send(200,{'service':'outlands-accounts','google_configured':True})
            if path=='/auth/google/start':
                pending=self.server.login.begin()
                return self.send(302,{},location=pending['url'],cookies=[self.state_cookie(LOGIN_COOKIE,pending['cookie'],300)])
            if path=='/auth/google/callback':
                query=parse_qs(parsed.query,keep_blank_values=True)
                if len(self.path)>4096 or not {'state','code'}<=set(query) or bool(set(query)-{'state','code','scope','authuser','prompt','hd','iss'}) or any(len(v)!=1 for v in query.values()):raise LoginRefused('Google sign-in could not be confirmed')
                # Google may identify the authorization-response issuer. Check
                # its exact fixed value before any confidential token exchange;
                # signed-token issuer/audience/nonce verification still follows.
                if 'iss' in query and query['iss']!=[ISSUER]:raise LoginRefused('Google sign-in could not be confirmed')
                identity=self.server.login.finish(query['state'][0],self.cookie(LOGIN_COOKIE),query['code'][0])
                self.server.store.provision(identity['issuer'],identity['subject'],'Outlander_'+secrets.token_hex(3))
                credential=self.server.store.start_browser_session(identity['issuer'],identity['subject'])
                return self.send(303,{},location='/',cookies=[self.state_cookie(SESSION_COOKIE,credential,BROWSER_SECONDS),self.state_cookie(LOGIN_COOKIE,'',0)])
            if path=='/api/me':return self.send(200,self.server.store.dashboard(BROWSER,self.browser()))
            files={'/':('index.html','text/html; charset=utf-8'),'/account.js':('account.js','text/javascript; charset=utf-8'),'/app.css':('app.css','text/css; charset=utf-8')}
            if path not in files:return self.send(404,{'error':'Not found'})
            filename,kind=files[path];return self.send(200,raw=(ROOT/'web'/filename).read_bytes(),kind=kind)
        except LoginRefused:return self.send(400,{'error':'Google sign-in could not be confirmed. Start again.'},cookies=[self.state_cookie(LOGIN_COOKIE,'',0)])
        except Refused:return self.send(401,{'error':'Sign-in required'})
        except (ValueError,KeyError,TypeError,OSError):return self.send(503,{'error':'Account service unavailable'})
    def do_POST(self):
        if not self.safe_host():return self.send(421,{'error':'Account host mismatch'})
        try:
            if self.path=='/internal/native':
                bearer=self.headers.get('Authorization','')
                if not bearer.startswith('Bearer ') or len(bearer)>160:raise Refused('Game worker authentication required')
                return self.send(200,self.server.store.native_event(bearer[7:],self.payload(native=True)))
            if self.path not in ('/api/profile','/api/link','/api/logout'):return self.send(404,{'error':'Not found'})
            body=self.payload();credential=self.browser()
            self.server.store.dashboard(BROWSER,credential) # authenticate before any mutation
            if self.path=='/api/profile':
                if set(body)!={'display_name','revision'}:raise Refused('Invalid profile request')
                return self.send(200,self.server.store.rename(BROWSER,credential,body['display_name'],body['revision']))
            if self.path=='/api/link':
                if set(body)!={'code'}:raise Refused('Invalid link request')
                return self.send(200,self.server.store.confirm(BROWSER,credential,body['code']))
            if body:raise Refused('Invalid logout request')
            self.server.store.logout(credential)
            return self.send(200,{'signed_out':True},cookies=[self.state_cookie(SESSION_COOKIE,'',0)])
        except Refused:return self.send(403,{'error':'Request refused. Check sign-in, current code and profile revision.'})
        except (ValueError,TypeError,OSError):return self.send(400,{'error':'Invalid account request'})
    def do_PUT(self):self.send(405,{'error':'Method not allowed'})
    do_PATCH=do_PUT
    do_DELETE=do_PUT


def main():
    config=Config.load(os.environ['OUTLANDS_ACCOUNT_ORIGIN'],Path('/run/outlands/google-client.json'))
    key_path=Path('/run/outlands/identity.key')
    if key_path.is_symlink() or not key_path.is_file() or key_path.stat().st_size!=32:raise ValueError('Private account key required')
    store=AccountStore(Path('/accounts/accounts.sqlite3'),key_path.read_bytes())
    AccountServer(('127.0.0.1',8087),store,GoogleLogin(config)).serve_forever()


if __name__=='__main__':main()
