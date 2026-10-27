"""Synthetic protocol/worker integration tests; no humans or native game data."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import armory as a
import armory_native as n


def request(kind="hello", sequence=1, revision=0, spawn=3, identity="abcd12", session="session1", refs=None):
    refs = refs or ("rifle", "pistol", "fast", "tough", "aware", "frag", "flash")
    return n.NativeRequest(session, sequence, kind, 2, identity, "epoch1", spawn, 10,
                           10000, refs, n.FIELDS, "1111111", True, revision)


def wire(event):
    return n.MARKER + "|".join(map(str, (event.session,event.sequence,event.kind,event.slot,event.identity,event.epoch,
        event.spawn,event.allocation,event.clock,",".join(event.refs),",".join(event.groups),event.unlocked,
        int(event.can_customize),event.revision,"base1")))


class ProtocolTests(unittest.TestCase):
    def test_strict_parser_accepts_native_metadata_but_not_chat_prefix(self):
        value = request()
        self.assertEqual(n.NativeRequest.parse(wire(value)),value)
        for bad in ("Player: "+wire(value),wire(value)+"|extra",wire(value).replace("|base1","|base2"),
                    wire(value).replace("|1|hello","|01|hello"), wire(value).replace("session1","session;quit"),
                    wire(value).replace("abcd12","0"),wire(value).replace("1111111","111111"),
                    wire(value).replace("rifle,","rifle\",",1),wire(value).replace("10000","-1")):
            self.assertIsNone(n.NativeRequest.parse(bad))

    def test_context_only_selected_items_and_fresh_native_feature_unlock(self):
        event=request("save",2)
        catalog,observed,loadout=event.context()
        self.assertEqual(a.validate(loadout,catalog,observed,event.clock).points,7)
        for change in ({"unlocked":"0111111"},{"can_customize":False},{"allocation":6},
                       {"groups":("secondary",)+n.FIELDS[1:]}):
            bad=replace(event,**change);cat,obs,load=bad.context()
            with self.assertRaises(a.Rejected):a.validate(load,cat,obs,bad.clock)

    def test_none_and_advanced_schema_are_not_silently_truncated(self):
        event=replace(request(),refs=("none",)*7,groups=("none",)*7,unlocked="0000000")
        self.assertEqual(n.NativeRequest.parse(wire(event)),event)
        cat,obs,load=event.context()
        self.assertEqual(a.validate(load,cat,obs,10000).points,0)
        advanced=load|{"primary_attachments":["optic"]}
        with self.assertRaisesRegex(a.Rejected,"native_base_subset"):n.native_refs(advanced)
        self.assertIsNone(n.NativeRequest.parse(wire(event).replace("0000000","1000000")))

    def test_mailbox_response_is_bounded_and_fixed(self):
        event=request()
        self.assertEqual(n.response(event,"empty"),"session1_1|2|empty|0|none,none,none,none,none,none,none")
        for status in ("quit","queued\";quit","applied|1"):
            with self.assertRaises(a.Rejected):n.response(event,status)
        from bridge import RconSink
        sink=RconSink("127.0.0.1",14977,Path("unused"))
        with patch("bridge.read_secret",return_value="a"*32),patch.object(sink,"_send") as send:
            sink.send_armory(n.response(event,"empty"))
            self.assertIn(b"set outlands_armory_response",send.call_args.args[0])
            for bad in ('x";quit',"x\ny","x ","a"*701):
                with self.assertRaises(ValueError):sink.send_armory(bad)

    def test_feature_flag_has_no_model_or_career_dependency(self):
        from bridge import Config
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"config.json";p.write_text('{}')
            with patch.dict(os.environ,{"T6_ARMORY_ENABLED":"1"},clear=True):
                config=Config.load(p)
                self.assertTrue(config.armory_enabled)
                self.assertFalse(config.enabled)
                self.assertFalse(config.careers_enabled)
            with patch.dict(os.environ,{"T6_ARMORY_ENABLED":"yes"},clear=True):
                with self.assertRaises(ValueError):Config.load(p)


@unittest.skipIf(os.name=="nt","Private state is hosted on Linux")
class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.root.chmod(0o700)
        self.path=self.root/"armory.json"
        self.store=a.ArmoryStore(self.path)
        self.service=n.NativeArmory(self.store)

    def handshake_save(self):
        self.assertIn("|empty|",self.service.handle(request()))
        event=request("save",2)
        value=self.service.handle(event)
        self.assertIn("|queued|1|",value)
        return event,value

    def test_save_queue_claim_native_ack_and_restart_restoration(self):
        self.handshake_save()
        claimed=request("claim",3,1,4)
        self.assertIn("|armed|1|",self.service.handle(claimed))
        self.assertIn("|applied|1|",self.service.handle(request("applied",4,1,4)))
        reopened=n.NativeArmory(a.ArmoryStore(self.path))
        hello=request(session="reconnect")
        self.assertIn("|saved|1|",reopened.handle(hello))
        self.assertIn("|queued|1|",reopened.handle(replace(hello,kind="equip",sequence=2,revision=1)))
        self.assertIn("|armed|1|",reopened.handle(replace(hello,kind="claim",sequence=3,revision=1,spawn=4)))

    def test_two_players_keep_distinct_classes_sessions_and_queues(self):
        self.handshake_save()
        other=request(identity="fff2",session="second")
        self.service.handle(other)
        changed=("smg",)+other.refs[1:]
        self.assertIn("|queued|1|",self.service.handle(replace(other,kind="save",sequence=2,refs=changed)))
        first=self.service.handle(request("claim",3,1,4))
        second=self.service.handle(replace(other,kind="claim",sequence=3,revision=1,spawn=4,refs=changed))
        self.assertIn("|rifle,",first)
        self.assertIn("|smg,",second)
        self.assertEqual(len(self.store.state["players"]),2)

    def test_duplicate_and_changed_request_cannot_rewrite_or_reclaim(self):
        event,value=self.handshake_save()
        original=self.path.read_bytes()
        self.assertEqual(self.service.handle(event),value)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertIsNone(self.service.handle(replace(event,refs=("smg",)+event.refs[1:])))
        claimed=request("claim",3,1,4)
        first=self.service.handle(claimed)
        self.assertEqual(self.service.handle(claimed),first)
        self.assertIn("|rejected|",self.service.handle(replace(claimed,sequence=4)))

    def test_lost_response_and_worker_restart_do_not_silently_replay_consumed_claim(self):
        self.handshake_save()
        self.service.handle(request("claim",3,1,4))
        reopened=n.NativeArmory(a.ArmoryStore(self.path))
        self.assertIn("|rejected|",reopened.handle(request("claim",4,1,4)))
        reopened.handle(request(sequence=5))
        self.assertIn("|rejected|",reopened.handle(request("equip",6,1,4)))

    def test_relocked_items_and_wrong_revision_reject_before_native_arm(self):
        self.handshake_save()
        self.assertIn("|rejected|",self.service.handle(replace(request("claim",3,1,4),unlocked="0111111")))
        self.assertIsNone(self.store.read("abcd12")["claim"])
        self.assertIn("|rejected|",self.service.handle(request("equip",4,2)))
        self.assertEqual(self.store.read("abcd12")["revision"],1)

    def test_native_equipment_ack_must_match_claimed_spawn_and_class(self):
        self.handshake_save()
        self.service.handle(request("claim",3,1,4))
        self.assertIn("|rejected|",self.service.handle(request("applied",4,1,5)))
        self.assertIn("|rejected|",self.service.handle(replace(request("applied",5,1,4),refs=("smg",)+request().refs[1:])))
        self.assertIn("|applied|",self.service.handle(request("applied",6,1,4)))

    def test_identity_slot_spoof_and_old_sequence_are_rejected(self):
        self.handshake_save()
        for change in ({"identity":"fff1"},{"slot":3},{"sequence":1}):
            self.assertIsNone(self.service.handle(replace(request("claim",3,1,4),**change)))

    def test_cancel_and_unconfirmed_application_have_no_false_equipped_ack(self):
        self.handshake_save()
        self.assertIn("|cancelled|",self.service.handle(request("cancel",3,1)))
        self.assertIn("|rejected|",self.service.handle(request("claim",4,1,4)))
        self.assertIn("|queued|",self.service.handle(request("equip",5,1,4)))
        self.assertIn("|armed|",self.service.handle(request("claim",6,1,5)))
        self.assertIn("|unconfirmed|",self.service.handle(request("failed",7,1,5)))

    def test_native_record_storage_contains_no_raw_identity_session_or_chat(self):
        self.handshake_save()
        raw=self.path.read_text()
        for private in ("abcd12","session1","epoch1"):
            self.assertNotIn(private,raw)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)


if __name__=="__main__":unittest.main()
