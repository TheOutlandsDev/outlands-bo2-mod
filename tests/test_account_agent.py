"""Synthetic worker protocol, fixed mailbox and offline provisioning boundaries."""
import json
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from accounts import agent
from accounts.agent import parse_event,api_url,deliver,submit
from accounts.admin import configure_files,enroll_file
from accounts.google_login import Config,GoogleLogin
from accounts.service import AccountServer,SESSION_COOKIE
from accounts.store import AccountStore,Refused
from portal.portal import LogFollower

LINE='OUTLANDS_ACCOUNT_V1|synthetic_session_001|1|link|3|a123b456|1234|2|0'

class WorkerTests(unittest.TestCase):
    def test_exact_native_protocol_and_bounded_stats(self):
        event=parse_event(LINE)
        self.assertEqual(event['stats'],{'rank_xp':1234,'rank_level':2,'prestige':0})
        self.assertEqual(parse_event(LINE.replace('|1234|2|0','|-1|-1|-1'))['stats'],{})
        for line in ('chat '+LINE,LINE+'|extra',LINE.replace('|3|','|18|'),LINE.replace('|2|0','|0|0'),LINE.replace('a123b456','0'),LINE.replace('link','arbitrary'),LINE.replace('|1|link','|0|link')):
            self.assertIsNone(parse_event(line))
    def test_fixed_pairing_mailbox_has_no_arbitrary_rcon(self):
        event=parse_event(LINE);sent=[]
        deliver(event,{'code':'A'*32},'synthetic_private_password',4977,lambda packet,address:sent.append((packet,address)))
        self.assertEqual(sent[0][1],('127.0.0.1',4977))
        self.assertTrue(sent[0][0].endswith(b'set outlands_account_response "synthetic_session_001_1|3|'+b'A'*32+b'"'))
        for code in ('a'*32,'A'*31,'A'*32+';quit'):
            with self.assertRaises(ValueError):deliver(event,{'code':code},'password',4977)
    def test_endpoint_and_submission_are_fixed_and_preserve_expected_host(self):
        for value in ('http://remote.invalid','https://user:pass@remote.invalid','https://remote.invalid/path','https://remote.invalid?code=x'):
            with self.assertRaises(ValueError):api_url(value)
        self.assertEqual(api_url('http://127.0.0.1:8087'),'http://127.0.0.1:8087/internal/native')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return b'{"accepted":true}'
        class Opener:
            def open(self,request,timeout):
                self.request=request;self.timeout=timeout;return Response()
        opener=Opener();submit(opener,api_url('http://127.0.0.1:8087'),'synthetic_worker_credential',parse_event(LINE),'accounts.example.invalid')
        self.assertEqual(opener.request.get_header('Host'),'accounts.example.invalid')
        self.assertNotIn('slot',json.loads(opener.request.data));self.assertEqual(opener.timeout,5)
    def test_offline_bootstrap_preserves_existing_secrets_and_rolls_back_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);base.chmod(0o700);private=base/'private';source=base/'source.json'
            config=Config('https://accounts.example.invalid','synthetic-client.apps.googleusercontent.com','synthetic_secret_12345')
            source.write_text(json.dumps({'web':{'client_id':config.client_id,'client_secret':config.client_secret,'redirect_uris':[config.callback]}}))
            with patch('accounts.admin.secrets.token_bytes',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):configure_files(private,config.origin,source)
            self.assertFalse((private/'google-client.json').exists())
            configure_files(private,config.origin,source)
            key=(private/'identity.key').read_bytes();self.assertEqual(len(key),32)
            with self.assertRaises(ValueError):configure_files(private,config.origin,source)
            self.assertEqual((private/'identity.key').read_bytes(),key)
            store=AccountStore(base/'accounts.sqlite3',key);output=base/'worker.credential'
            with patch('accounts.admin.new_file',side_effect=OSError('fixture')):
                with self.assertRaises(OSError):enroll_file(store,'synthetic_server_001',output)
            enroll_file(store,'synthetic_server_001',output)
            with self.assertRaises(ValueError):enroll_file(store,'synthetic_server_001',output)
            with store.connection() as db:self.assertEqual(store.server(db,output.read_text()),'synthetic_server_001')

class WorkerTransportTests(unittest.TestCase):
    """Real follower/main loop, loopback HTTP and UDP with synthetic identities.

    Redirect only private fixture paths and the loop's wait/stop boundary. Do
    not mock HTTP submission, account transactions or mailbox delivery. This
    does not simulate a human in the native engine or authenticate Google users.
    """
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.root.chmod(0o700)
        self.store=AccountStore(self.root/'accounts.sqlite3',b'k'*32)
        self.origin='https://accounts.example.invalid'
        self.cookies=[]
        for subject in ('synthetic_owner_001','synthetic_other_002'):
            self.store.provision('https://accounts.google.com',subject,subject)
            self.cookies.append(self.store.start_browser_session('https://accounts.google.com',subject))
        self.credential=self.store.enroll_server('synthetic_server_001')
        self.password='synthetic_rcon_password'
        self.paths={}
        for expected,name,value in (('/run/outlands/server.credential','credential',self.credential),('/data/private/outlands_rcon_password','password',self.password)):
            path=self.root/name;path.write_text(value);path.chmod(0o600);self.paths[expected]=path
        self.log=self.root/'console.log';self.log.write_text(LINE+'\n');self.log.chmod(0o600)
        self.server=AccountServer(('127.0.0.1',0),self.store,GoogleLogin(Config(self.origin,'synthetic-client.apps.googleusercontent.com','synthetic_secret_12345')))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop_server)
        self.receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.receiver.bind(('127.0.0.1',0));self.receiver.settimeout(.3);self.addCleanup(self.receiver.close)
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def drive(self,lines,before_append=None):
        class StopLoop(Exception):pass
        ticks=[]
        def tick(seconds):
            ticks.append(seconds)
            if len(ticks)>1:raise StopLoop()
            if before_append:before_append()
            with self.log.open('a') as stream:stream.write('\n'.join(lines)+'\n')
        original_secret=agent.secret;output=io.StringIO()
        environment={'OUTLANDS_ACCOUNT_API':self.url,'OUTLANDS_ACCOUNT_ORIGIN':self.origin,'T6_PORT':str(self.receiver.getsockname()[1])}
        with patch.dict(os.environ,environment),patch.object(agent,'secret',side_effect=lambda path:original_secret(self.paths[path])),patch.object(agent,'LogFollower',side_effect=lambda path:LogFollower(self.log)),patch.object(agent,'time',SimpleNamespace(sleep=tick)),redirect_stdout(output):
            with self.assertRaises(StopLoop):agent.main()
        self.assertEqual(ticks,[1,1])
        return output.getvalue()
    def response_code(self,session,sequence):
        packet,address=self.receiver.recvfrom(2048)
        prefix=b'\xff\xff\xff\xffrcon '+self.password.encode()+b' set outlands_account_response "'+session.encode()+b'_'+str(sequence).encode()+b'|3|'
        self.assertTrue(packet.startswith(prefix));self.assertTrue(packet.endswith(b'"'))
        code=packet[len(prefix):-1].decode();self.assertRegex(code,r'^[0-9A-F]{32}$')
        return code
    def request(self,path,body=None,owner=0):
        headers={'Host':'accounts.example.invalid','Cookie':SESSION_COOKIE+'='+self.cookies[owner]}
        raw=None
        if body is not None:
            raw=json.dumps(body).encode();headers.update({'Content-Type':'application/json','Origin':self.origin,'X-Outlands-Request':'1'})
        try:return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(urllib.request.Request(self.url+path,data=raw,headers=headers),timeout=2)
        except urllib.error.HTTPError as error:return error
    def view(self,owner=0):
        with self.request('/api/me',owner=owner) as response:
            self.assertEqual(response.status,200);return json.load(response)
    def test_real_worker_transport_restart_reconnect_and_browser_ownership(self):
        session='synthetic_live_session_001'
        def no_old_sessions():
            with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        def line(sequence,kind,xp=1500,session_id=session):
            return f'OUTLANDS_ACCOUNT_V1|{session_id}|{sequence}|{kind}|3|a123b456|{xp}|3|1'
        output=self.drive(['public chat '+LINE,line(1,'hello'),line(2,'link')],no_old_sessions)
        code=self.response_code(session,2)
        for private in (code,self.credential,self.password):self.assertNotIn(private,output)
        self.assertEqual(self.view()['profiles'],[]);self.assertEqual(self.view(1)['profiles'],[])
        with self.request('/api/link',{'code':code}) as response:self.assertEqual(response.status,200)
        profile=self.view()['profiles'][0];self.assertTrue(profile['live']);self.assertEqual(profile['stats'],{'rank_xp':1500,'rank_level':3,'prestige':1})
        with self.request('/api/link',{'code':code},owner=1) as response:self.assertEqual(response.status,403)
        # A restarted worker starts at EOF and resumes from a fresh snapshot.
        self.drive([line(3,'snapshot',100),line(4,'link',100)])
        code=self.response_code(session,4)
        self.assertEqual(self.view()['profiles'][0]['stats']['rank_xp'],100)
        self.assertEqual(self.view(1)['profiles'],[])
        with self.request('/api/link',{'code':code},owner=1) as response:self.assertEqual(response.status,403)
        with self.request('/api/link',{'code':code}) as response:self.assertEqual(response.status,200)
        # A reconnect loses session confirmation; retained ownership cannot move.
        reconnect='synthetic_live_session_002'
        self.drive([line(1,'hello',2000,reconnect),line(2,'link',2000,reconnect)])
        code=self.response_code(reconnect,2)
        self.assertFalse(self.view()['profiles'][0]['live'])
        with self.request('/api/link',{'code':code},owner=1) as response:self.assertEqual(response.status,403)
        with self.request('/api/link',{'code':code}) as response:self.assertEqual(response.status,200)
        profile=self.view()['profiles'][0];self.assertTrue(profile['live']);self.assertEqual(profile['stats']['rank_xp'],2000)
        for private in (code,'a123b456',session,reconnect,self.credential,self.password):self.assertNotIn(private,json.dumps(self.view()))


if __name__=='__main__':unittest.main()
