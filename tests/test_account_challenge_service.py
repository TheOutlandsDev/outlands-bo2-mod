"""Real loopback HTTP transport with synthetic confirmed accounts only."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from accounts.store import AccountStore
from accounts.service import AccountServer, SESSION_COOKIE
from accounts.google_login import Config, GoogleLogin
from ai.challenge_delivery import AccountTransport, DeliveryStore, ArchiveReader, deliver

ORIGIN='https://accounts.example.invalid'
ISSUER='https://accounts.google.com'
SESSION='synthetic_session_001'


class AccountChallengeHttpTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.root.chmod(0o700)
        self.store=AccountStore(self.root/'accounts.sqlite3',b'k'*32)
        self.store.provision(ISSUER,'subject_1','PlayerOne')
        self.store.provision(ISSUER,'subject_2','PlayerTwo')
        self.cookie=self.store.start_browser_session(ISSUER,'subject_1')
        self.other=self.store.start_browser_session(ISSUER,'subject_2')
        login=GoogleLogin(Config(ORIGIN,'synthetic.apps.googleusercontent.com','synthetic_client_secret'))
        self.server=AccountServer(('127.0.0.1',0),self.store,login,challenge_preview=True)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def stop():self.server.shutdown();self.server.server_close();thread.join()
        self.addCleanup(stop)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.credential=self.store.enroll_server('synthetic_server_001')
        self.transport=AccountTransport(self.url,ORIGIN,self.credential)
        self.binding={'kind':'bind','session':SESSION,'profile_reference':'abc123'}

    def request(self,path,payload=None,cookie=None):
        headers={'Host':'accounts.example.invalid'}
        if cookie:headers['Cookie']=SESSION_COOKIE+'='+cookie
        raw=None
        if payload is not None:
            raw=json.dumps(payload).encode();headers.update({'Content-Type':'application/json','Origin':ORIGIN,'X-Outlands-Request':'1'})
        request=Request(self.url+path,data=raw,headers=headers)
        try:return build_opener(ProxyHandler({})).open(request,timeout=3)
        except HTTPError as error:return error

    def link(self):
        self.store.open_session(self.credential,SESSION,'abc123')
        self.store.ingest(self.credential,SESSION,1,{'rank_xp':123})
        code=self.store.challenge(self.credential,SESSION)['code']
        with self.request('/api/link',{'code':code},self.cookie) as response:
            self.assertEqual(response.status,200)

    def test_browser_cannot_award_or_enable_and_default_service_route_is_off(self):
        for path in ('/internal/challenges','/api/challenges'):
            with self.request(path,self.binding,self.cookie) as response:
                self.assertEqual(response.status,403 if path.startswith('/internal') else 404)
        self.link()
        with self.assertRaises(OSError):self.transport.post(self.binding)
        self.server.challenges.enable_server('synthetic_server_001')
        grant=self.transport.post(self.binding)
        self.assertEqual(len(grant['grant']),64)
        self.server.challenges=None
        with self.request('/internal/challenges',self.binding,self.cookie) as response:self.assertEqual(response.status,404)

    @unittest.skipIf(os.name == 'nt', 'Linux server log and private outbox fixture')
    def test_outage_rotation_lost_response_and_private_account_progress_over_http(self):
        self.link();self.server.challenges.enable_server('synthetic_server_001')
        grant=self.transport.post(self.binding)['grant']
        game=self.root/'game';game.mkdir();(game/'logs').mkdir()
        private=self.root/'outbox';private.mkdir(mode=0o700)
        db=DeliveryStore(private/'delivery.sqlite3','b'*64)
        log=game/'console.log';token='a'*64
        def line(seq):return 'OUTLANDS_CHALLENGE_KILL_V2|'+'|'.join((token,grant,SESSION,'match1','event_session1',str(seq),'an94_mp','1','1','1','1'))+'\n'
        log.write_text(line(1));reader=ArchiveReader(log,db,token);reader.poll()
        transport=self.transport
        class LostReply:
            def post(self,event):transport.post(event);raise OSError('synthetic lost response after HTTP commit')
        deliver(db,LostReply(),10000)
        with log.open('a') as stream:stream.write(line(2))
        log.rename(game/'logs/console-0001.log');log.write_text(line(3))
        reopened=DeliveryStore(private/'delivery.sqlite3','b'*64)
        ArchiveReader(log,reopened,token).poll();deliver(reopened,transport,10003)
        self.assertEqual(reopened.summary()['pending'],0)
        with self.request('/api/me',cookie=self.cookie) as response:
            first=json.load(response);self.assertEqual(first['custom_challenges'][0]['progress'],3)
            self.assertFalse(first['native_save_sync']);self.assertEqual(first['profiles'][0]['stats']['rank_xp'],123)
            self.assertNotIn(grant,json.dumps(first));self.assertNotIn(SESSION,json.dumps(first))
        with self.request('/api/me',cookie=self.other) as response:
            self.assertEqual(json.load(response)['custom_challenges'][0]['progress'],0)
        with self.request('/api/me') as response:self.assertEqual(response.status,401)


if __name__=='__main__':unittest.main()
