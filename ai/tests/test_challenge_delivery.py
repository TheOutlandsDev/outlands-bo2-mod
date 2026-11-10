"""Durability under actual local file rotation and synthetic trusted events."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from challenge_delivery import (DeliveryStore, ArchiveReader, Binding, ContinuityError,
                                parse_native, deliver, AccountTransport, grant_packet)
from accounts.store import AccountStore
from accounts.challenges import AccountChallenges

TOKEN = 'a'*64
DESTINATION = 'b'*64
SESSION = 'synthetic_session_001'


@unittest.skipIf(os.name == 'nt', 'Private challenge worker runs on Linux')
class DeliveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.root.chmod(0o700)
        for name in ('game', 'state', 'accounts'):
            (self.root/name).mkdir(mode=0o700)
        self.game = self.root/'game'; (self.game/'logs').mkdir()
        self.log = self.game/'console.log'
        self.path = self.root/'state/delivery.sqlite3'
        self.db = DeliveryStore(self.path, DESTINATION)
        self.accounts = AccountStore(self.root/'accounts/accounts.sqlite3', b'k'*32, lambda:10000)
        self.accounts.provision('https://accounts.google.com', 'synthetic_subject', 'SyntheticPlayer')
        self.credential = self.accounts.enroll_server('synthetic_server_001')
        self.core = AccountChallenges(self.accounts); self.core.enable_server('synthetic_server_001')
        self.accounts.open_session(self.credential, SESSION, 'abc123')
        self.accounts.ingest(self.credential, SESSION, 1, {'rank_xp':100})
        code = self.accounts.challenge(self.credential, SESSION)['code']
        self.accounts.confirm('https://accounts.google.com', 'synthetic_subject', code)
        self.grant = self.core.bind(self.credential, {'kind':'bind', 'session':SESSION, 'profile_reference':'abc123'})['grant']
        self.reader = ArchiveReader(self.log, self.db, TOKEN)

    def line(self, seq=1, **changes):
        fields = {'token':TOKEN, 'grant':self.grant, 'session':SESSION, 'match':'match1',
                  'event_session':'challenge1', 'sequence':seq, 'weapon':'an94_mp',
                  'human':1,'enemy':1,'headshot':1,'confirmed':1}
        fields.update(changes)
        return 'OUTLANDS_CHALLENGE_KILL_V2|'+'|'.join(map(str,fields.values()))+'\n'

    def remote(self):
        core, credential = self.core, self.credential
        class Remote:
            def post(self,event): return core.handle(credential,event)
        return Remote()

    def count(self):
        return self.core.dashboard('https://accounts.google.com','synthetic_subject')[0]['progress']

    def test_outage_across_multiple_rotations_then_restart_delivers_every_event_once(self):
        self.log.write_text(self.line(1)); self.reader.poll()
        with self.log.open('a') as stream: stream.write(self.line(2))
        self.log.rename(self.game/'logs/console-0001.log')
        self.log.write_text(self.line(3)); self.log.rename(self.game/'logs/console-0002.log')
        self.log.write_text(self.line(4))
        db = DeliveryStore(self.path,DESTINATION); reader = ArchiveReader(self.log,db,TOKEN)
        reader.poll(); self.assertEqual(db.summary()['pending'],4)
        deliver(db,self.remote(),10000)
        self.assertEqual(self.count(),4)
        self.assertEqual(db.summary()['pending'],0)
        reader.poll();deliver(db,self.remote(),10001)
        self.assertEqual(self.count(),4)
        self.assertEqual(db.summary()['acknowledged'],4)
        with db.connection() as connection:
            self.assertTrue(all(row['payload'] is None for row in connection.execute('SELECT payload FROM outbox')))

    def test_cursor_and_event_staging_roll_back_together(self):
        self.log.write_text(self.line())
        with patch.object(self.db,'checkpoint',side_effect=OSError('synthetic crash')):
            with self.assertRaises(OSError):self.reader.poll()
        self.assertEqual(self.db.summary(),{'pending':0,'acknowledged':0,'files':0})
        self.reader.poll();deliver(self.db,self.remote(),10000)
        self.assertEqual(self.count(),1)

    def test_remote_commit_before_lost_response_is_retried_without_double_credit(self):
        self.log.write_text(self.line());self.reader.poll()
        remote=self.remote()
        class LostResponse:
            def post(self,event):remote.post(event);raise OSError('synthetic lost reply')
        deliver(self.db,LostResponse(),10000)
        self.assertEqual(self.count(),1);self.assertEqual(self.db.summary()['pending'],1)
        reopened=DeliveryStore(self.path,DESTINATION)
        deliver(reopened,remote,10003)
        self.assertEqual(self.count(),1);self.assertEqual(reopened.summary()['pending'],0)

    def test_partial_lines_and_large_ignored_records_survive_reader_restart(self):
        line=self.line();self.log.write_text('x'*70000+'\n'+line[:70])
        self.reader.poll();self.reader.poll()
        self.assertEqual(self.db.summary()['pending'],0)
        with self.log.open('a') as stream:stream.write(line[70:])
        reopened=ArchiveReader(self.log,DeliveryStore(self.path,DESTINATION),TOKEN)
        reopened.poll();deliver(self.db,self.remote(),10000)
        self.assertEqual(self.count(),1)

    def test_removed_unsealed_log_rewrite_and_conflicting_replay_fail_closed(self):
        self.log.write_text(self.line());self.reader.poll();before=self.db.summary()
        self.log.write_text('rewritten')
        with self.assertRaises(ContinuityError):self.reader.poll()
        self.log.unlink()
        with self.assertRaises(ContinuityError):self.reader.poll()
        self.assertEqual(self.db.summary(),before)

    def test_conflicting_native_replay_does_not_advance_cursor(self):
        self.log.write_text(self.line());self.reader.poll()
        with self.log.open('a') as stream:stream.write(self.line(match='other_match'))
        with self.assertRaises(ContinuityError):self.reader.poll()
        self.assertEqual(self.db.summary()['pending'],1)

    def test_private_destination_is_bound_and_noneligible_or_spoofed_records_ignored(self):
        with self.assertRaises(ValueError):DeliveryStore(self.path,'c'*64)
        self.log.write_text('player: '+self.line()+self.line(token='d'*64)+self.line(human=0)+self.line(weapon='mp7_mp')+self.line(headshot=0))
        self.reader.poll();self.assertEqual(self.db.summary()['pending'],0)
        self.assertIsNone(parse_native('OUTLANDS_CHALLENGE_KILL_V2|\ufffd|bad',TOKEN))
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)

    def test_fixed_mailbox_and_https_transport_have_no_arbitrary_command_path(self):
        binding=Binding('synthetic_request',0,SESSION,'abc123')
        packet=grant_packet(binding,{'grant':self.grant,'valid_seconds':120},'synthetic_rcon_password_001')
        self.assertIn(b'set outlands_challenge_grant "',packet)
        for changes in ({'grant':'bad;quit'}, {'valid_seconds':True}, {'valid_seconds':21601}):
            with self.assertRaises(ValueError):grant_packet(binding,{'grant':self.grant,'valid_seconds':120}|changes,'synthetic_rcon_password_001')
        for api in ('http://remote.invalid','https://user:password@example.invalid','https://example.invalid/other'):
            with self.assertRaises(ValueError):AccountTransport(api,'https://accounts.example.invalid','synthetic_credential_001')

    def test_malformed_remote_acknowledgment_keeps_event_pending(self):
        self.log.write_text(self.line());self.reader.poll()
        class Malformed:
            def __init__(self,value):self.value=value
            def post(self,event):return self.value
        for index,value in enumerate(([], {'progress':[]}, {'accepted':True,'duplicate':False,'progress':{}})):
            deliver(self.db,Malformed(value),10000+index*100)
            self.assertEqual(self.db.summary()['pending'],1)
        deliver(self.db,self.remote(),11000)
        self.assertEqual(self.count(),1);self.assertEqual(self.db.summary()['pending'],0)


if __name__=='__main__':unittest.main()
