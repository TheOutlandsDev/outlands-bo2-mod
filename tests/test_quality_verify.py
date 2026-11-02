import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import hosting.backend_verify as backend
from hosting.quality_verify import assess_quality,FIELDS
from hosting.backend_verify import config_for,Case

def fixture():
    rows=[]
    for tick in range(20,261,20):
        elapsed=tick*250
        for slot in range(16):
            n=tick//20
            d=dict(alive_ms=elapsed,moving_ms=elapsed//2,threat_ms=elapsed//3,visible_ms=elapsed//4,on_target_ms=elapsed//8,objective_ms=elapsed//10,idle_travel_ms=0,shots=n*2,hits=n,damage=n*25,first_shots=0,shot_latency_sum=0,first_hits=0,hit_latency_sum=0,distance_units=tick*2,crowded_ms=elapsed//20,goal_changes=n,kills=n//4,deaths=n//4)
            rows.append('OUTLANDS_QUALITY_V1|0|'+str(tick)+'|'+str(slot)+'|'+str(elapsed)+'|'+'|'.join(str(d[k]) for k in FIELDS))
    return '\n'.join(rows)

class QualityEvidenceTests(unittest.TestCase):
    def test_native_counters_with_limits(self):
        r=assess_quality(fixture());self.assertTrue(r['passed'],r['reasons']);self.assertEqual(r['moving_alive_fraction'],.5);self.assertFalse(r['hit_ratio_is_accuracy']);self.assertFalse(r['human_gameplay_accepted'])
    def test_no_evidence_or_chat_prefix_cannot_pass(self):
        for s in ('','Player: '+fixture().replace('\n','\nPlayer: ')):
            self.assertFalse(assess_quality(s)['passed'])
    def test_duplicate_reordered_and_impossible_counters_fail(self):
        s=fixture();first=s.splitlines()[0]
        for bad in (s+'\n'+first,'\n'.join(reversed(s.splitlines())),s.replace('|5000|2500|','|5000|9000|')):
            self.assertFalse(assess_quality(bad)['passed'])
    def test_latency_trace_and_context_counts_are_both_required(self):
        s=fixture().replace('|0|0|0|0|','|1|400|0|0|',1)
        self.assertFalse(assess_quality(s)['passed'])
    def test_probe_defaults_off(self):
        self.assertIn('set outlands_verify_quality 0\n',config_for(Case('mp_raid','conf'),120,False,False))
        self.assertIn('set outlands_verify_quality 1\n',config_for(Case('mp_raid','conf'),120,False,False,ai_quality=True))


    def test_latency_percentiles_are_bound_to_reported_sequences_and_sums(self):
        rows=[]
        for raw in fixture().splitlines():
            f=raw.split('|')
            if f[3]=='0':
                f[5+FIELDS.index('first_shots')]='1'
                f[5+FIELDS.index('shot_latency_sum')]='400'
            rows.append('|'.join(f))
        counters='\n'.join(rows)
        trace='OUTLANDS_QUALITY_LATENCY_V1|0|0|shot|400|1'
        good=counters+'\n'+trace
        self.assertTrue(assess_quality(good)['passed'])
        for bad in (counters,good.replace('|shot|400|1','|shot|700|1'),good+'\n'+trace):
            self.assertFalse(assess_quality(bad)['passed'])
        # A real trailing event after the last counter snapshot is outside this
        # window and cannot bias its latency percentiles.
        trailing=assess_quality(good+'\nOUTLANDS_QUALITY_LATENCY_V1|0|0|shot|9000|2')
        self.assertTrue(trailing['passed']);self.assertEqual(trailing['first_observed_shot_latency_ms']['median'],400)

class QualityRunnerWiringTests(unittest.TestCase):
    def test_requested_quality_probe_and_enable_flag_travel_together(self):
        class SeedCaptured(RuntimeError):pass
        class Capture:
            payload=None
            def call(self,*args,**kw):
                if kw.get('input_text'):
                    self.payload=json.loads(kw['input_text']);raise SeedCaptured()
                return ''
        for enabled in (False,True):
            docker=Capture()
            with tempfile.TemporaryDirectory() as d,patch.object(backend,'require_map_asset'):
                with self.assertRaises(SeedCaptured):
                    backend.run_case(docker,'unused-image',Case('mp_raid','conf'),120,False,Path(d),ai_quality=enabled)
            self.assertIn('set outlands_verify_quality '+str(int(enabled))+'\n',docker.payload['cfg'])
            self.assertEqual(bool(docker.payload['quality']),enabled)
