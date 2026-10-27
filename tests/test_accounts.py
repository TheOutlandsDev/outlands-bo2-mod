"""Account core isolation/transactions with synthetic principals and observations.

These fixtures do not authenticate Discord/Google users, launch clients or read
any real profile. Provider validation and native pairing delivery are later gates.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('outlands_accounts',Path(__file__).resolve().parents[1]/'accounts/store.py')
MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
AccountStore,Refused=MODULE.AccountStore,MODULE.Refused
ISSUER='https://accounts.google.com';SUBJECT='synthetic_subject_001';OTHER='synthetic_subject_002'
SERVER='synthetic_server_001';SECOND_SERVER='synthetic_server_002'
SESSION='synthetic_session_001';SECOND_SESSION='synthetic_session_002'
GUID='a123b456';SECOND_GUID='c987d654'
STATS={'rank_xp':9500,'rank_level':3,'prestige':0,'kills':10,'deaths':4,'wins':2,'losses':1}


class AccountsTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.directory=Path(self.temporary.name);self.directory.chmod(0o700)
        self.path=self.directory/'accounts.sqlite3';self.time=[10000]
        self.key=b'k'*32
        self.store=AccountStore(self.path,self.key,lambda:self.time[0])
        self.account=self.store.provision(ISSUER,SUBJECT,'SyntheticPlayer')
        self.other=self.store.provision(ISSUER,OTHER,'AnotherPlayer')
        self.credential=self.store.enroll_server(SERVER)
    def linked(self,session=SESSION,guid=GUID):
        self.store.open_session(self.credential,session,guid)
        self.store.ingest(self.credential,session,1,STATS)
        challenge=self.store.challenge(self.credential,session)
        self.assertEqual(self.store.confirm(ISSUER,SUBJECT,challenge['code']),{'linked':True})
        return challenge
    def view(self,subject=SUBJECT):return self.store.dashboard(ISSUER,subject)

    def test_native_worker_rehandshake_pairing_and_closed_replay(self):
        event={'session':SESSION,'sequence':1,'kind':'snapshot','profile_reference':GUID,'stats':STATS}
        self.store.native_event(self.credential,event)
        self.store.native_event(self.credential,event) # follower restart, same observation
        self.assertEqual(self.view()['profiles'],[])
        code=self.store.native_event(self.credential,event|{'sequence':2,'kind':'link'})['code']
        self.store.confirm(ISSUER,SUBJECT,code)
        self.assertEqual(self.view()['profiles'][0]['stats'],STATS)
        with self.assertRaises(Refused):self.store.native_event(self.credential,event|{'profile_reference':SECOND_GUID})
        with self.assertRaises(Refused):self.store.native_event('untrusted_credential',event)
        self.store.native_event(self.credential,event|{'sequence':3,'kind':'depart'})
        self.assertFalse(self.view()['profiles'][0]['live'])
        with self.assertRaises(Refused):self.store.native_event(self.credential,event|{'sequence':4})

    def test_account_is_stable_across_restart_and_display_name_changes(self):
        repeated=self.store.provision(ISSUER,SUBJECT,'ChangedIgnored')
        self.assertEqual(repeated,self.account)
        changed=self.store.rename(ISSUER,SUBJECT,'NewDisplayName',1)
        self.assertEqual(changed['id'],self.account['id']);self.assertEqual(changed['revision'],2)
        reopened=AccountStore(self.path,self.key,lambda:self.time[0])
        self.assertEqual(reopened.dashboard(ISSUER,SUBJECT)['display_name'],'NewDisplayName')
        with self.assertRaises(Refused):self.store.rename(ISSUER,SUBJECT,'RaceOverwrite',1)
        self.assertEqual(self.view(OTHER)['display_name'],'AnotherPlayer')

    def test_confirmed_personal_view_and_no_unlinked_player_exposure(self):
        self.store.open_session(self.credential,SESSION,GUID)
        self.store.ingest(self.credential,SESSION,1,STATS)
        self.assertEqual(self.view()['profiles'],[])
        code=self.store.challenge(self.credential,SESSION)['code']
        self.store.confirm(ISSUER,SUBJECT,code)
        profile=self.view()['profiles'][0]
        self.assertTrue(profile['live']);self.assertEqual(profile['stats'],STATS)
        self.assertFalse(self.view()['native_save_sync'])
        self.assertEqual(self.view(OTHER)['profiles'],[])
        for private in (GUID,SESSION,code,self.credential):self.assertNotIn(private,json.dumps(self.view()))

    def test_cannot_steal_previously_linked_profile_by_reusing_lan_identity(self):
        self.linked()
        self.store.open_session(self.credential,SECOND_SESSION,GUID)
        self.store.ingest(self.credential,SECOND_SESSION,1,{'rank_xp':99999999})
        code=self.store.challenge(self.credential,SECOND_SESSION)['code']
        with self.assertRaises(Refused):self.store.confirm(ISSUER,OTHER,code)
        profile=self.view()['profiles'][0]
        self.assertEqual(profile['stats'],STATS);self.assertFalse(profile['live'])
        self.assertEqual(self.view(OTHER)['profiles'],[])
        self.store.confirm(ISSUER,SUBJECT,code)
        self.assertEqual(self.view()['profiles'][0]['stats'],{'rank_xp':99999999})

    def test_same_account_multiple_servers_and_profiles_are_not_merged(self):
        self.linked()
        second=self.store.enroll_server(SECOND_SERVER)
        self.store.open_session(second,SECOND_SESSION,GUID)
        self.store.ingest(second,SECOND_SESSION,1,{'rank_xp':50,'rank_level':1})
        code=self.store.challenge(second,SECOND_SESSION)['code'];self.store.confirm(ISSUER,SUBJECT,code)
        profiles=self.view()['profiles'];self.assertEqual(len(profiles),2)
        self.assertEqual({row['stats']['rank_xp'] for row in profiles},{50,9500})
        self.assertEqual(len({row['profile_id'] for row in profiles}),2)
        with self.assertRaises(Refused):self.store.ingest(second,SESSION,2,STATS)

    def test_duplicate_snapshots_do_not_refresh_liveness_or_duplicate_progress(self):
        self.linked();self.time[0]+=31
        result=self.store.ingest(self.credential,SESSION,1,STATS)
        self.assertTrue(result['duplicate']);self.assertFalse(self.view()['profiles'][0]['live'])
        self.assertEqual(self.view()['profiles'][0]['observed_at'],10000)
        for seq,values in ((1,{'kills':11}),(0,STATS)):
            with self.assertRaises(Refused):self.store.ingest(self.credential,SESSION,seq,values)
        self.store.ingest(self.credential,SESSION,2,{'rank_xp':0,'rank_level':1,'prestige':1})
        profile=self.view()['profiles'][0]
        self.assertEqual(profile['stats']['rank_xp'],0);self.assertTrue(profile['live'])

    def test_closed_reconnect_requires_new_proof_and_retains_last_observed_stats(self):
        challenge=self.linked()
        self.store.close_session(self.credential,SESSION)
        profile=self.view()['profiles'][0];self.assertFalse(profile['live']);self.assertEqual(profile['stats'],STATS)
        with self.assertRaises(Refused):self.store.ingest(self.credential,SESSION,2,STATS)
        with self.assertRaises(Refused):self.store.open_session(self.credential,SESSION,GUID)
        self.store.open_session(self.credential,SECOND_SESSION,GUID)
        self.store.ingest(self.credential,SECOND_SESSION,1,{'kills':12})
        self.assertEqual(self.view()['profiles'][0]['stats'],STATS)
        with self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,challenge['code'])
        code=self.store.challenge(self.credential,SECOND_SESSION)['code'];self.store.confirm(ISSUER,SUBJECT,code)
        self.assertEqual(self.view()['profiles'][0]['stats'],{'kills':12})
        self.time[0]+=86401
        profile=self.view()['profiles'][0];self.assertFalse(profile['live']);self.assertEqual(profile['stats'],{'kills':12})

    def test_codes_expire_rotate_and_cannot_be_consumed_twice(self):
        self.store.open_session(self.credential,SESSION,GUID)
        first=self.store.challenge(self.credential,SESSION)['code']
        second=self.store.challenge(self.credential,SESSION)['code']
        with self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,first)
        self.time[0]+=180
        with self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,second)
        fresh=self.store.challenge(self.credential,SESSION)['code'];self.store.confirm(ISSUER,SUBJECT,fresh)
        with self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,fresh)

    def test_concurrent_claim_has_one_owner_and_one_success(self):
        self.store.open_session(self.credential,SESSION,GUID)
        code=self.store.challenge(self.credential,SESSION)['code']
        def claim(subject):
            try:return self.store.confirm(ISSUER,subject,code)['linked']
            except Refused:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,[SUBJECT,OTHER]))
        self.assertEqual(results.count(True),1)
        self.assertEqual(sum(len(self.view(subject)['profiles']) for subject in (SUBJECT,OTHER)),1)

    def test_pair_rate_limits_commit_on_failure_then_reset(self):
        for _ in range(5):
            with self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,'0'*32)
        self.store.open_session(self.credential,SESSION,GUID)
        code=self.store.challenge(self.credential,SESSION)['code']
        with self.assertRaisesRegex(Refused,'attempts exceeded'):self.store.confirm(ISSUER,SUBJECT,code)
        self.time[0]+=60;self.assertTrue(self.store.confirm(ISSUER,SUBJECT,code)['linked'])

    def test_invalid_fields_credentials_and_unverified_subjects_fail_closed(self):
        self.store.open_session(self.credential,SESSION,GUID)
        for values in ({},{'rank_xp':True},{'rank_level':56},{'prestige':12},{'kills':-1},
                       {'unlockall':1},{'native_file':'arbitrary'},{'chat':'text'}):
            with self.subTest(values=values),self.assertRaises(Refused):self.store.ingest(self.credential,SESSION,1,values)
        with self.assertRaises(Refused):self.store.ingest(self.account['id'],SESSION,1,STATS)
        with self.assertRaises(Refused):self.store.dashboard('https://untrusted.invalid',SUBJECT)
        with self.assertRaises(Refused):self.store.dashboard(ISSUER,'missing_subject')
        for value in ('<script>','Trailing ', 'Unicode\u2603','Line\nbreak'):
            with self.assertRaises(Refused):self.store.rename(ISSUER,SUBJECT,value,1)

    def test_private_storage_contains_no_raw_subject_guid_codes_or_worker_credential(self):
        challenge=self.linked()
        with closing(sqlite3.connect(self.path,isolation_level=None)) as db:
            dump='\n'.join(db.iterdump())
        for value in (SUBJECT,GUID,challenge['code'],self.credential):
            self.assertNotIn(value,dump)
        if os.name!='nt':self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        with self.assertRaises(Refused):AccountStore(self.path,b'x'*32)
        if os.name!='nt':
            self.path.chmod(0o644)
            with self.assertRaises(Refused):AccountStore(self.path,self.key)
            self.path.chmod(0o600)
            linked=self.directory/'link.sqlite3';linked.symlink_to(self.path)
            with self.assertRaises(Refused):AccountStore(linked,self.key)

    def test_clock_rollback_hides_future_values_and_expires_silent_sessions(self):
        self.linked();self.time[0]-=10
        profile=self.view()['profiles'][0];self.assertFalse(profile['live']);self.assertIsNone(profile['stats'])
        self.time[0]+=1811
        with self.assertRaises(Refused):self.store.ingest(self.credential,SESSION,2,STATS)
        self.assertFalse(self.view()['profiles'][0]['live'])

    def test_failed_link_transaction_does_not_half_assign_profile(self):
        self.store.open_session(self.credential,SESSION,GUID)
        code=self.store.challenge(self.credential,SESSION)['code']
        with closing(sqlite3.connect(self.path,isolation_level=None)) as db:
            db.execute("CREATE TRIGGER fail_confirmation BEFORE UPDATE OF confirmed ON sessions BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
        with self.assertRaises(sqlite3.DatabaseError):self.store.confirm(ISSUER,SUBJECT,code)
        self.assertEqual(self.view()['profiles'],[])
        with closing(sqlite3.connect(self.path,isolation_level=None)) as db:db.execute('DROP TRIGGER fail_confirmation')
        self.assertTrue(self.store.confirm(ISSUER,SUBJECT,code)['linked'])

    def test_browser_sessions_are_opaque_scoped_revocable_and_expiring(self):
        first=self.store.start_browser_session(ISSUER,SUBJECT)
        other=self.store.start_browser_session(ISSUER,OTHER)
        self.assertEqual(self.store.dashboard(MODULE.BROWSER,first)['id'],self.account['id'])
        self.assertEqual(self.store.dashboard(MODULE.BROWSER,other)['id'],self.other['id'])
        with closing(sqlite3.connect(self.path,isolation_level=None)) as db:self.assertNotIn(first,'\n'.join(db.iterdump()))
        with self.assertRaises(Refused):self.store.start_browser_session(MODULE.BROWSER,first)
        self.store.logout(first)
        with self.assertRaises(Refused):self.store.dashboard(MODULE.BROWSER,first)
        self.time[0]+=MODULE.BROWSER_SECONDS
        with self.assertRaises(Refused):self.store.dashboard(MODULE.BROWSER,other)

    def test_bounded_active_sessions_and_account_profiles(self):
        with patch.object(MODULE,'MAX_SESSIONS',1):
            self.store.open_session(self.credential,SESSION,GUID)
            with self.assertRaises(Refused):self.store.open_session(self.credential,SECOND_SESSION,SECOND_GUID)
        code=self.store.challenge(self.credential,SESSION)['code'];self.store.confirm(ISSUER,SUBJECT,code)
        self.store.close_session(self.credential,SESSION)
        self.store.open_session(self.credential,SECOND_SESSION,SECOND_GUID)
        code=self.store.challenge(self.credential,SECOND_SESSION)['code']
        with patch.object(MODULE,'MAX_PROFILES_PER_ACCOUNT',1),self.assertRaises(Refused):self.store.confirm(ISSUER,SUBJECT,code)
        self.assertEqual(len(self.view()['profiles']),1)


if __name__=='__main__':unittest.main()
