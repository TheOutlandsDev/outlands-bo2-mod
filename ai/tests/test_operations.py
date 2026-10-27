"""Synthetic human observations; never native saves or live player data."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from operations import OperationEvent, OperationStore, MARKER, response_value
import bridge


def sample(sequence=1, kind='hello', **kw):
    event = OperationEvent('synthetic_session',sequence,kind,3,'a12b34',0,0,0,'none')
    return replace(event,**kw)


def wire(e):
    return MARKER+'|'.join(map(str,(e.session,e.sequence,e.kind,e.slot,e.identity,e.kills,e.objective,e.support,e.track)))


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'operations.json'
        self.store=OperationStore(self.path)

    def test_progress_survives_restart_reconnect_and_map_sessions_without_duplicate_awards(self):
        hello=sample(kills=10)
        self.assertEqual(self.store.apply(hello)['assault'],0)
        earned=sample(2,'snapshot',kills=35,objective=3,support=3)
        profile=self.store.apply(earned)
        self.assertEqual(profile,{'assault':25,'objective':3,'support':3,'selected':'assault','operation':1})
        restarted=OperationStore(self.path)
        self.assertEqual(restarted.apply(earned),profile)
        self.assertIsNone(restarted.apply(replace(earned,kills=36)))
        self.assertIsNone(restarted.apply(hello))
        self.assertEqual(restarted.apply(sample(session='new_map',kills=99)),profile)
        self.assertEqual(restarted.apply(sample(2,'snapshot',session='new_map',kills=100))['assault'],26)

    def test_retry_rebase_and_partial_reset_are_conservative(self):
        self.store.apply(sample(kills=10))
        self.assertEqual(self.store.apply(sample(2,'hello',kills=12))['assault'],0)
        self.assertEqual(self.store.apply(sample(3,'snapshot',kills=13,objective=1))['assault'],1)
        result=self.store.apply(sample(4,'snapshot',kills=0,objective=2))
        self.assertEqual((result['assault'],result['objective']),(1,2))
        self.assertEqual(self.store.apply(sample(5,'snapshot',kills=999,objective=3))['objective'],2)
        self.assertEqual(self.store.apply(sample(6,'snapshot',kills=1000,objective=4))['objective'],3)

    def test_selection_persists_and_unseen_snapshots_cannot_create_careers(self):
        self.assertIsNone(self.store.apply(sample(2,'snapshot',kills=50)))
        self.assertFalse(self.path.exists())
        self.store.apply(sample())
        chosen=self.store.apply(sample(2,'select',track='objective'))
        self.assertEqual(chosen['selected'],'objective')
        self.assertEqual(OperationStore(self.path).apply(sample(3,'show'))['selected'],'objective')
        self.assertIsNone(self.store.apply(sample(4,'snapshot',identity='b12a')))
        self.assertIsNone(self.store.apply(sample(4,'snapshot',slot=4)))

    def test_state_has_only_salted_identifiers_and_numeric_progress(self):
        self.store.apply(sample())
        raw=self.path.read_text()
        for secret in ('a12b34','synthetic_session','SyntheticPlayer','OUTLANDS_OP'):
            self.assertNotIn(secret,raw)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        other=OperationStore(Path(self.temp.name)/'other.json');other.apply(sample())
        self.assertNotEqual(set(other.state['players']),set(self.store.state['players']))

    def test_corruption_public_permissions_and_symlinks_fail_closed(self):
        self.store.apply(sample());original=self.path.read_bytes()
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):OperationStore(self.path)
        self.path.chmod(0o600);self.path.write_text('{}')
        with self.assertRaises(ValueError):OperationStore(self.path)
        self.path.write_bytes(original)
        link=self.path.parent/'link.json';link.symlink_to(self.path)
        with self.assertRaises((ValueError,OSError)):OperationStore(link)

    def test_failed_atomic_write_does_not_advance_in_memory_or_disk(self):
        self.store.apply(sample());before=self.path.read_bytes()
        with patch('operations.os.replace',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):self.store.apply(sample(2,'snapshot',kills=1))
        self.assertEqual(before,self.path.read_bytes())
        self.assertEqual(self.store.apply(sample(2,'snapshot',kills=1))['assault'],1)
        self.assertEqual(list(self.path.parent.glob('.operations-*')),[])

    def test_transport_rejects_malformed_identity_commands_and_counts(self):
        valid=wire(sample());self.assertEqual(OperationEvent.parse(valid),sample())
        for bad in ('Player: '+valid,valid+'|extra',valid.replace('|a12b34|','|0|'),valid.replace('|a12b34|','|a;quit|'),valid.replace('|hello|','|grant|'),valid.replace('|3|','|18|'),valid.replace('|0|0|0|','|-1|0|0|'),wire(sample(kind='select')),wire(sample(track='support'))):
            self.assertIsNone(OperationEvent.parse(bad),bad)
        profile=self.store.apply(sample())
        self.assertEqual(response_value(sample(),profile),'synthetic_session_1|3|0|0|0|assault|0')
        with self.assertRaises(ValueError):response_value(sample(),profile|{'selected':'assault;quit'})

    def test_worker_operations_run_independently_of_model_and_bot_careers(self):
        sent=[]
        class Sink:
            def send_operation(self,e,p):sent.append((e.request_id,p))
        worker=bridge.Worker(bridge.Config(operations_enabled=True),None,Sink(),None,operations=self.store)
        worker.ingest([wire(sample()),wire(sample(2,'snapshot',kills=5))],100)
        self.assertEqual(sent[-1][1]['assault'],5)
        self.assertEqual(len(worker.queue),0)
        worker=bridge.Worker(bridge.Config(),None,Sink(),None,operations=self.store)
        worker.ingest([wire(sample(3,'snapshot',kills=6))],101)
        self.assertEqual(len(sent),2)

    def test_environment_switch_must_be_explicit(self):
        cfg=Path(bridge.__file__).parent/'config.example.json'
        with patch.dict(os.environ,{'T6_OPERATIONS_ENABLED':'1'},clear=True):
            self.assertTrue(bridge.Config.load(cfg).operations_enabled)
        with patch.dict(os.environ,{'T6_OPERATIONS_ENABLED':'yes'},clear=True):
            with self.assertRaises(ValueError):bridge.Config.load(cfg)


if __name__=='__main__':unittest.main()
