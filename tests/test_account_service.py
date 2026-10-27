"""Private account HTTP contract with synthetic trusted login and native fixtures."""
from http.cookies import SimpleCookie
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from accounts.google_login import Config,GoogleLogin
from accounts.service import AccountServer,SESSION_COOKIE,LOGIN_COOKIE
from accounts.store import AccountStore

ORIGIN='https://accounts.example.invalid';HOST='accounts.example.invalid'
ISSUER='https://accounts.google.com';SUBJECT='123456789'


class AccountHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.directory.chmod(0o700)
        self.store=AccountStore(self.directory/'accounts.sqlite3',b'k'*32)
        self.account=self.store.provision(ISSUER,SUBJECT,'SyntheticPlayer')
        self.cookie=self.store.start_browser_session(ISSUER,SUBJECT)
        config=Config(ORIGIN,'synthetic-client.apps.googleusercontent.com','synthetic_secret_12345')
        self.login=GoogleLogin(config,exchanger=lambda *args:'fixture.token',verifier=lambda *args:{})
        self.server=AccountServer(('127.0.0.1',0),self.store,self.login)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body=None,auth=True,headers=None):
        actual={'Host':HOST}
        if auth:actual['Cookie']=SESSION_COOKIE+'='+self.cookie
        raw=None
        if body is not None:
            raw=json.dumps(body).encode();actual.update({'Origin':ORIGIN,'X-Outlands-Request':'1','Content-Type':'application/json'})
        actual.update(headers or {})
        request=urllib.request.Request(self.url+path,data=raw,headers=actual)
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        try:return urllib.request.build_opener(NoRedirect()).open(request,timeout=2)
        except urllib.error.HTTPError as error:return error
    def test_anonymous_personal_data_refused_and_owner_scoped(self):
        with self.request('/api/me',auth=False) as response:self.assertEqual(response.status,401)
        with self.request('/api/me') as response:
            self.assertEqual(response.status,200);self.assertEqual(json.load(response)['id'],self.account['id'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        for path in ('/api/player/123','/accounts.sqlite3','/../store.py','/internal/stats'):
            with self.request(path) as response:self.assertEqual(response.status,404)
    def test_cross_origin_wrong_host_and_mutating_identity_payloads_refused(self):
        for headers in ({'Origin':'https://other.invalid'},{'X-Outlands-Request':''}):
            with self.request('/api/profile',{'display_name':'Changed','revision':1},headers=headers) as response:self.assertEqual(response.status,403)
        with self.request('/api/me',headers={'Host':'other.invalid'}) as response:self.assertEqual(response.status,421)
        with self.request('/api/profile',{'display_name':'Changed','revision':1,'account_id':'another'}) as response:self.assertEqual(response.status,403)
        with self.request('/api/profile',{'display_name':'Changed','revision':1}) as response:self.assertEqual(response.status,200)
    def test_native_pairing_and_private_stats_then_logout(self):
        credential=self.store.enroll_server('synthetic_server_001')
        self.store.open_session(credential,'synthetic_session_001','a12b34')
        self.store.ingest(credential,'synthetic_session_001',1,{'rank_xp':5000})
        code=self.store.challenge(credential,'synthetic_session_001')['code']
        with self.request('/api/link',{'code':code}) as response:self.assertEqual(response.status,200)
        with self.request('/api/me') as response:self.assertEqual(json.load(response)['profiles'][0]['stats'],{'rank_xp':5000})
        with self.request('/api/logout',{}) as response:
            self.assertEqual(response.status,200);cookie=response.headers['Set-Cookie']
            for attribute in ('Secure','HttpOnly','SameSite=Lax','Path=/','Max-Age=0'):self.assertIn(attribute,cookie)
        with self.request('/api/me') as response:self.assertEqual(response.status,401)
    def test_google_redirect_scope_cookie_and_callback_nonce(self):
        with self.request('/auth/google/start',auth=False) as response:
            self.assertEqual(response.status,302);self.assertTrue(response.headers['Location'].startswith('https://accounts.google.com/'))
            cookie=SimpleCookie(response.headers['Set-Cookie'])[LOGIN_COOKIE].value
        state,entry=next(iter(self.login.pending.items()))
        self.login.verify=lambda *args:{'iss':ISSUER,'aud':self.login.config.client_id,'sub':SUBJECT,'nonce':entry['nonce']}
        with self.request('/auth/google/callback?state='+state+'&code=fixture-code&scope=openid&authuser=0',auth=False,headers={'Cookie':LOGIN_COOKIE+'='+cookie}) as response:
            self.assertEqual(response.status,303);self.assertEqual(response.headers['Location'],'/')
            cookies=response.headers.get_all('Set-Cookie');self.assertTrue(any(SESSION_COOKIE in value and 'Secure' in value for value in cookies))
        with self.request('/auth/google/callback?state='+state+'&code=fixture-code',auth=False) as response:self.assertEqual(response.status,400)
    def test_static_account_ui_and_loopback_only_binding(self):
        for path in ('/','/account.js','/app.css'):
            with self.request(path,auth=False) as response:self.assertEqual(response.status,200)
        with self.assertRaises(ValueError):AccountServer(('0.0.0.0',8087),self.store,self.login)

    def test_native_ingress_requires_enrolled_worker_not_browser_cookie(self):
        event={'session':'synthetic_session_001','sequence':1,'kind':'link','profile_reference':'a12b34','stats':{'rank_xp':5000}}
        for headers in ({},{'Authorization':'Bearer invalid_credential'}):
            with self.request('/internal/native',event,headers=headers) as response:self.assertEqual(response.status,403)
        credential=self.store.enroll_server('synthetic_server_001')
        with self.request('/internal/native',event,auth=False,headers={'Authorization':'Bearer '+credential,'Origin':''}) as response:
            self.assertEqual(response.status,200);code=json.load(response)['code']
        with self.request('/api/link',{'code':code}) as response:self.assertEqual(response.status,200)
        with self.request('/api/me') as response:self.assertEqual(json.load(response)['profiles'][0]['stats'],{'rank_xp':5000})
        with self.request('/api/profile',{'rank_xp':999999}) as response:self.assertEqual(response.status,403)


if __name__=='__main__':unittest.main()
