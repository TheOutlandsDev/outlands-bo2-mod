"""Reject unsupported claims from missing, forged or inconsistent native receipts."""
import unittest
from ai.rivals import load_profiles,combat_tuning,aim_blend
from hosting.human_verify import assess_humanization,METRICS
from hosting.backend_verify import config_for,Case


class HumanizationEvidenceTests(unittest.TestCase):
    def fixture(self,enabled=True):
        lines=[]
        if enabled:
            lines.append('OUTLANDS_HUMAN_NATIVE_V1|0|85|650|1000')
            for slot,(alias,p) in enumerate(list(load_profiles().items())[:16]):
                t=combat_tuning(p['tier'])
                lines.append('|'.join(map(str,['OUTLANDS_HUMAN_PROFILE_V1',0,slot,alias,*t.values()])))
                if slot<4:
                    blend=aim_blend(50,t['smooth_ms'])
                    lines.append('|'.join(map(str,['OUTLANDS_HUMAN_AIM_V1',0,slot,50,t['smooth_ms'],int(blend*1000),100000,int(100000*blend*blend)])))
        for tick in range(20,31):
            fields=[0,tick,16,16 if enabled else 0,tick if enabled else 0,tick if enabled else 0,tick if enabled else 0,0,0,5,16,0,20]
            self.assertEqual(len(fields),len(METRICS))
            lines.append('OUTLANDS_HUMAN_METRICS_V1|'+'|'.join(map(str,fields)))
        return '\n'.join(lines)

    def test_native_combat_receipts_replay_and_keep_client_acceptance_pending(self):
        r=assess_humanization(self.fixture(),True,False,'tdm')
        self.assertTrue(r['passed'],r['reasons'])
        self.assertFalse(r['visual_aim_smoothness_accepted'])
        self.assertFalse(r['human_navigation_quality_accepted'])

    def test_combat_skill_is_bounded_and_independent_of_cosmetic_rank(self):
        rows=[combat_tuning(t) for t in ('developing','regular','experienced','standout')]
        self.assertEqual({r['difficulty'] for r in rows},{'easy','normal','hard'})
        self.assertTrue(all(a['converge_ms']>b['converge_ms'] and a['aim_error']>b['aim_error'] for a,b in zip(rows,rows[1:])))
        for tier in ('fu','55',True,None):
            with self.assertRaises(ValueError):combat_tuning(tier)

    def test_filter_timing_has_bounded_steps_and_rejects_bad_inputs(self):
        self.assertEqual(aim_blend(0,300),0.1)
        self.assertEqual(aim_blend(1000,300),0.75)
        for elapsed,smooth in [(True,300),(-1,300),(1001,300),(50,0),(50,True)]:
            with self.assertRaises(ValueError):aim_blend(elapsed,smooth)

    def test_missing_native_callbacks_or_false_control_values_cannot_pass(self):
        text=self.fixture()
        for missing in ('OUTLANDS_HUMAN_AIM_V1','OUTLANDS_HUMAN_NATIVE_V1','OUTLANDS_HUMAN_PROFILE_V1'):
            changed='\n'.join(x for x in text.splitlines() if not x.startswith(missing))
            self.assertFalse(assess_humanization(changed,True,False,'tdm')['passed'])
        self.assertFalse(assess_humanization(text.replace('|85|650|1000','|140|400|700'),True,False,'tdm')['passed'])

    def test_disabled_feature_observes_without_changing_combat(self):
        self.assertTrue(assess_humanization(self.fixture(False),False,False,'tdm')['passed'])
        self.assertFalse(assess_humanization(self.fixture(),False,False,'tdm')['passed'])

    def test_guard_relocation_needs_arrival_and_a_real_hold(self):
        text=self.fixture()+'\nOUTLANDS_HUMAN_ROAM_V1|0|65536|100000|1|4000'
        self.assertTrue(assess_humanization(text,True,True,'dom')['passed'])
        self.assertFalse(assess_humanization(text,True,False,'dom')['passed'])
        self.assertFalse(assess_humanization(text.replace('|1|4000','|2|0'),True,True,'dom')['passed'])
        self.assertFalse(assess_humanization(text.replace('|1|4000','|1|100'),True,True,'dom')['passed'])

    def test_hq_guard_override_must_preserve_accepted_native_patrol(self):
        text=self.fixture()
        self.assertFalse(assess_humanization(text,True,False,'hq')['passed'])
        self.assertTrue(assess_humanization(text+'\nOUTLANDS_HQ_PATROL_V1|0|1|1',True,False,'hq')['passed'])
        self.assertFalse(assess_humanization(text+'\nOUTLANDS_HQ_PATROL_V1|0|1|0',True,False,'hq')['passed'])

    def test_tampered_profile_filter_or_chat_prefixed_evidence_fails(self):
        text=self.fixture()
        for changed in (text.replace('|easy|2800','|fu|100'),text+'\nOUTLANDS_HUMAN_AIM_V1|0|0|50|360|999|100000|99999','\n'.join('Player: '+x for x in text.splitlines()),text+'\nOUTLANDS_HUMAN_METRICS_V1|invalid'):
            self.assertFalse(assess_humanization(changed,True,False,'tdm')['passed'])

    def test_reordered_or_duplicate_stage_ticks_are_not_replayable(self):
        text=self.fixture()+'\nOUTLANDS_HUMAN_METRICS_V1|0|1|16|16|1|1|1|0|0|1|16|0|10'
        self.assertFalse(assess_humanization(text,True,False,'tdm')['passed'])

    def test_native_config_creates_custom_dvars_and_baseline_stays_off(self):
        baseline=config_for(Case('mp_raid','dom'),90,False,False,human_metrics=True)
        self.assertIn('set outlands_bot_humanize 0\n',baseline)
        self.assertIn('set outlands_bot_objective_roam 0\n',baseline)
        candidate=config_for(Case('mp_raid','dom'),90,False,False,humanize=True,objective_roam=True)
        for key in ('outlands_bot_humanize','outlands_bot_objective_roam','outlands_human_metrics'):
            self.assertIn('set '+key+' 1\n',candidate)


if __name__=='__main__':unittest.main()
