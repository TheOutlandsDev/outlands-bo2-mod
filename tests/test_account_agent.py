"""Synthetic worker protocol, fixed mailbox and offline provisioning boundaries."""
import json
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
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

class PairingDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now=0.;self.sent=[]
        self.delivery=agent.PairingDelivery(lambda packet,address:self.sent.append((packet,address)),lambda:self.now)
        self.event=parse_event(LINE);self.result={'code':'A'*32};self.password='synthetic_private_password'
    def add(self,event=None):self.delivery.add(event or self.event,self.result,self.password,4977)
    def ack(self,event=None):return 'OUTLANDS_ACCOUNT_ACK_V1|'+agent.request_key(event or self.event)
    def test_loss_of_packet_and_ack_retries_same_code_and_stops_after_ack(self):
        self.add();self.delivery.service();self.assertEqual(len(self.sent),1)
        self.now=.5;self.delivery.service();self.assertEqual(len(self.sent),1)
        self.now=.8;self.delivery.service();self.assertEqual(len(self.sent),2) # first packet lost
        self.now=1.6;self.delivery.service();self.assertEqual(len(self.sent),3) # first ACK lost
        self.assertTrue(all(p==self.sent[0] for p in self.sent))
        self.assertTrue(self.delivery.acknowledge(self.ack()))
        self.now=3.;self.delivery.service();self.assertEqual(len(self.sent),3)
    def test_only_one_mailbox_writer_and_wrong_or_duplicate_ack_cannot_advance(self):
        other={**self.event,'slot':4,'session':'synthetic_other_session_002'}
        self.add();self.add(other);self.delivery.service()
        self.assertEqual(len(self.sent),1);self.assertIn(b'|3|',self.sent[0][0])
        self.assertFalse(self.delivery.acknowledge(self.ack(other)))
        self.assertFalse(self.delivery.acknowledge('chat '+self.ack()))
        self.assertTrue(self.delivery.acknowledge(self.ack()));self.delivery.service()
        self.assertEqual(len(self.sent),2);self.assertIn(b'|4|',self.sent[1][0])
        self.assertFalse(self.delivery.acknowledge(self.ack()))
        self.assertTrue(self.delivery.acknowledge(self.ack(other)))
    def test_expiry_retry_limit_and_reconnect_cancel_without_replaying_codes(self):
        self.add();self.delivery.service();self.now=8
        self.assertFalse(self.delivery.acknowledge(self.ack()));self.delivery.service()
        self.assertEqual(len(self.sent),1);self.assertEqual(self.delivery.expired,1)
        self.add()
        for _ in range(8):self.delivery.service();self.now+=1
        self.assertEqual(len(self.sent),1+self.delivery.MAX_ATTEMPTS)
        self.now=20;self.add();self.delivery.service()
        self.delivery.observe({**self.event,'kind':'hello','session':'synthetic_reconnect_002'})
        before=len(self.sent);self.now+=1;self.delivery.service();self.assertEqual(len(self.sent),before)
        self.add();self.delivery.clear();self.now+=1;self.delivery.service();self.assertEqual(len(self.sent),before)
    def test_superseding_code_cancels_old_request_and_late_queued_item_expires(self):
        self.add();new={**self.event,'sequence':2};self.add(new);self.delivery.service()
        self.assertIn(b'_2|3|',self.sent[0][0]);self.assertFalse(self.delivery.acknowledge(self.ack()))
        self.assertTrue(self.delivery.acknowledge(self.ack(new)))
        self.delivery.add(self.event,self.result,self.password,4977,received=-9);self.delivery.service()
        self.assertEqual(len(self.sent),1)
    def test_transport_errors_are_bounded_and_invalid_fields_never_reach_socket(self):
        def unavailable(*args):raise OSError('fixture')
        self.delivery.sender=unavailable;self.add()
        for _ in range(10):self.delivery.service();self.now+=1
        self.assertEqual(self.delivery.attempts,self.delivery.MAX_ATTEMPTS)
        for event in ({**self.event,'session':'bad;quit'},{**self.event,'slot':True},{**self.event,'sequence':0}):
            with self.assertRaises(ValueError):self.add(event)

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
        with patch.dict(os.environ,environment),patch.object(agent,'secret',side_effect=lambda path:original_secret(self.paths[path])),patch.object(agent,'LogFollower',side_effect=lambda path:LogFollower(self.log)),patch.object(agent,'time',SimpleNamespace(sleep=tick,monotonic=time.monotonic)),redirect_stdout(output):
            with self.assertRaises(StopLoop):agent.main()
        self.assertEqual(ticks,[.25,.25])
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

    def test_main_loop_recovers_udp_losses_and_serializes_two_profile_codes(self):
        class StopLoop(Exception):pass
        first='synthetic_simultaneous_001';second='synthetic_simultaneous_002'
        now=[0.];ticks=[0];packets=[];codes={};output=io.StringIO()
        def append(lines):
            with self.log.open('a') as stream:stream.write('\n'.join(lines)+'\n')
        def receive(session):
            packet,_=self.receiver.recvfrom(2048);packets.append(packet)
            value=packet.split(b' set outlands_account_response "',1)[1][:-1].decode()
            request,slot,code=value.split('|');self.assertEqual(request,session+'_2');codes[session]=code
            return packet
        def tick(seconds):
            ticks[0]+=1;now[0]+=1
            if ticks[0]==1:
                append([f'OUTLANDS_ACCOUNT_V1|{s}|{q}|{kind}|{slot}|{guid}|{xp}|3|0'
                        for s,slot,guid,xp in ((first,3,'a123b456',1500),(second,4,'b123b456',2500))
                        for q,kind in ((1,'hello'),(2,'link'))])
            elif ticks[0]==2:receive(first) # discard first packet
            elif ticks[0]==3:receive(first) # consume retry but discard ACK
            elif ticks[0]==4:
                receive(first);self.assertEqual(packets[0],packets[1]);self.assertEqual(packets[1],packets[2])
                append(['OUTLANDS_ACCOUNT_ACK_V1|'+first+'_2'])
            elif ticks[0]==5:
                receive(second);append(['OUTLANDS_ACCOUNT_ACK_V1|'+second+'_2'])
            else:raise StopLoop()
        original_secret=agent.secret
        environment={'OUTLANDS_ACCOUNT_API':self.url,'OUTLANDS_ACCOUNT_ORIGIN':self.origin,'T6_PORT':str(self.receiver.getsockname()[1])}
        with patch.dict(os.environ,environment),patch.object(agent,'secret',side_effect=lambda path:original_secret(self.paths[path])),patch.object(agent,'LogFollower',side_effect=lambda path:LogFollower(self.log)),patch.object(agent,'time',SimpleNamespace(sleep=tick,monotonic=lambda:now[0])),redirect_stdout(output):
            with self.assertRaises(StopLoop):agent.main()
        self.assertEqual(len(packets),4)
        with self.request('/api/link',{'code':codes[first]},owner=0) as response:self.assertEqual(response.status,200)
        with self.request('/api/link',{'code':codes[second]},owner=1) as response:self.assertEqual(response.status,200)
        self.assertEqual(self.view(0)['profiles'][0]['stats']['rank_xp'],1500)
        self.assertEqual(self.view(1)['profiles'][0]['stats']['rank_xp'],2500)
        for private in (*codes.values(),self.password,self.credential):self.assertNotIn(private,output.getvalue())


if __name__=='__main__':unittest.main()
