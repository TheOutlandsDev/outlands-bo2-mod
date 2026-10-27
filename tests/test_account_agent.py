"""Synthetic worker protocol, fixed mailbox and offline provisioning boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from accounts.agent import parse_event,api_url,deliver,submit
from accounts.admin import configure_files,enroll_file
from accounts.google_login import Config
from accounts.store import AccountStore,Refused

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

if __name__=='__main__':unittest.main()
