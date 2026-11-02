import unittest
from hosting.human_verify import assess_loadouts
from hosting.backend_verify import config_for,Case

def fixture():
    lines=[]
    for slot in range(16):
        lines.append(f'OUTLANDS_LOADOUT_BUILD_V1|0|{slot}|0|WEAPON_A|WEAPON_A,WEAPON_B')
        lines.append(f'OUTLANDS_LOADOUT_BUILD_V1|0|{slot}|1|WEAPON_B|WEAPON_A,WEAPON_B')
        lines.append(f'OUTLANDS_LOADOUT_EQUIP_V1|0|{slot}|1|custom0|gun{slot}_mp+reflex+grip|gun{slot}_mp+grip+reflex|1')
    return '\n'.join(lines)

class LoadoutEvidenceTests(unittest.TestCase):
    def test_native_choice_replay_and_carried_attachment_sets(self):
        r=assess_loadouts(fixture());self.assertTrue(r['passed'],r['reasons']);self.assertEqual(r['distinct_carried_guns'],16)
    def test_duplicate_primary_is_rejected_when_a_fresh_choice_existed(self):
        self.assertFalse(assess_loadouts(fixture().replace('|1|WEAPON_B|','|1|WEAPON_A|'))['passed'])
    def test_exhausted_small_native_pool_can_fall_back_without_inventing_unlocks(self):
        text=fixture()+'\nOUTLANDS_LOADOUT_BUILD_V1|0|0|2|WEAPON_A|WEAPON_A,WEAPON_B'
        self.assertTrue(assess_loadouts(text)['passed'])
    def test_missing_primary_and_wrong_actual_attachments_fail(self):
        for bad in (fixture().replace('+grip+reflex|1','+grip|1'),fixture().replace('|1\n','|0\n'),fixture().replace('|gun0_mp+grip+reflex|','|unknown_mp+grip+reflex|')):
            self.assertFalse(assess_loadouts(bad)['passed'])
    def test_missing_or_chat_prefixed_receipts_cannot_claim_variety(self):
        for text in ('', 'Player: '+fixture().replace('\n','\nPlayer: ')):
            self.assertFalse(assess_loadouts(text)['passed'])
    def test_new_feature_is_opt_in(self):
        self.assertIn('set outlands_bot_loadout_variety 0\n',config_for(Case('mp_raid','tdm'),150,False,False))
        self.assertIn('set outlands_bot_loadout_variety 1\n',config_for(Case('mp_raid','tdm'),150,False,False,loadouts=True))
