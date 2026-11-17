import unittest
from hosting.challenge_verify import assess_guards


class ChallengeGuardTests(unittest.TestCase):
    def test_requires_real_deaths_and_no_bot_rewards(self):
        rows = ['OUTLANDS_CHALLENGE_GUARD_V1|1|2|2|0|1|16',
                'OUTLANDS_CHALLENGE_GUARD_V1|1|8|8|0|1|16']
        self.assertTrue(assess_guards('\n'.join(rows))['passed'])
        self.assertTrue(assess_guards('OUTLANDS_CHALLENGE_GUARD_V1|1|0|0|0|1|8\n'+'\n'.join(rows))['passed'])
        for bad in ('1|8|7|0|1|16', '1|8|8|1|1|16', '0|8|8|0|1|16', '1|8|8|0|1|15'):
            self.assertFalse(assess_guards(rows[0]+'\nOUTLANDS_CHALLENGE_GUARD_V1|'+bad)['passed'])
        self.assertFalse(assess_guards(rows[0])['passed'])
        self.assertFalse(assess_guards('chat: '+rows[0])['passed'])


if __name__ == '__main__': unittest.main()
