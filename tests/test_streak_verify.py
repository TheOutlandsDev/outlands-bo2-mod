import unittest
from hosting.human_verify import assess_streaks
from hosting.backend_verify import config_for,Case

GOOD='''OUTLANDS_STREAK_USE_RADIUS_V1|4096
OUTLANDS_STREAK_FIXTURE_V1|grant|2
OUTLANDS_STREAK_SUPPLY_V1|2|1|0|12000
OUTLANDS_STREAK_FIXTURE_V1|landed|2
OUTLANDS_STREAK_RETRIEVE_V1|2|65536
OUTLANDS_STREAK_FIXTURE_V1|captured|1'''

class StreakProofTests(unittest.TestCase):
    def test_real_native_chain_is_functional_not_organic_earning_acceptance(self):
        r=assess_streaks(GOOD);self.assertTrue(r['passed'],r['reasons']);self.assertFalse(r['organic_earning_accepted'])
    def test_missing_or_wrong_owner_cannot_pass(self):
        for bad in (GOOD.replace('landed|2','landed|3'),GOOD.replace('captured|1','captured|0'),GOOD.replace('grant|2','grant|3'),GOOD.replace('OUTLANDS_STREAK_RETRIEVE_V1|2|65536','')):
            self.assertFalse(assess_streaks(bad)['passed'])
    def test_charge_must_be_used_after_spawn_window_and_goal_beyond_use_range(self):
        for bad in (GOOD.replace('|1|0|12000','|1|1|12000'),GOOD.replace('|1|0|12000','|1|0|3000'),GOOD.replace('|2|65536','|2|1024'),GOOD.replace('4096','not-a-radius')):
            self.assertFalse(assess_streaks(bad)['passed'])
    def test_chat_prefixed_forged_or_duplicate_evidence_is_rejected(self):
        for bad in ('Player: '+GOOD.replace('\n','\nPlayer: '),GOOD+'\nOUTLANDS_STREAK_SUPPLY_V1|2|0|1|12000',GOOD+'\nOUTLANDS_STREAK_FIXTURE_V1|grant|2'):
            self.assertFalse(assess_streaks(bad)['passed'])
    def test_fixture_stays_opt_in_and_isolated_config_uses_set(self):
        base=config_for(Case('mp_raid','tdm'),120,False,False)
        self.assertIn('set outlands_verify_streaks 0\n',base)
        candidate=config_for(Case('mp_raid','tdm'),120,False,False,streaks=True)
        self.assertIn('set outlands_verify_streaks 1\n',candidate)
        self.assertIn('set outlands_bot_streaks 1\n',candidate)
