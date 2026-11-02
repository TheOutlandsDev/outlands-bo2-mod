"""Planner variety, native-data agreement and fictional-roster boundaries."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rivals import load_profiles, plan, hash_text, match_seed, generated_catalog, duty_score, position_cost, favorite_weight

ROOT = Path(__file__).resolve().parents[2]


class RivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = load_profiles()
        aliases = list(cls.profiles)
        cls.roster = [{"alias": alias, "slot": i, "team": "allies" if i < 8 else "axis"} for i, alias in enumerate(aliases[:16])]

    def test_roster_catalog_and_native_data_agree(self):
        names = {x.strip().rstrip(',') for x in (ROOT / 'storage/t6/bots.txt').read_text().splitlines() if x.strip()}
        self.assertEqual(names, set(self.profiles))
        personalities = json.loads((ROOT / 'ai/personalities.json').read_text())['profiles']
        self.assertEqual({k:v['role'] for k,v in self.profiles.items()}, {k:v.get('role', 'assault') for k,v in personalities.items()})
        self.assertEqual((ROOT / 'storage/t6/scripts/mp/outlands_rival_catalog.gsc').read_text(), generated_catalog(self.profiles))

    def test_same_observation_and_seed_replay_independent_of_input_order(self):
        first = plan(self.roster, 17, 'mp_raid', 'dom')
        self.assertEqual(first, plan(list(reversed(self.roster)), 17, 'mp_raid', 'dom'))
        self.assertEqual(first, plan(self.roster, 17, 'mp_raid', 'dom'))

    def test_many_seeds_change_tendencies_without_mutating_identities(self):
        seen = set()
        for seed in range(1, 257):
            result = plan(self.roster, seed, 'mp_raid', 'dom')
            seen.add(tuple((b['aggression'], b['teamwork'], b['route']) for b in result['bots']))
            for bot in result['bots']:
                profile = self.profiles[bot['alias']]
                self.assertEqual(bot['role'], profile['role'])
                self.assertEqual(bot['specialty'], profile['specialty'])
                self.assertLessEqual(abs(bot['aggression'] - profile['aggression']), 10)
                self.assertLessEqual(abs(bot['teamwork'] - profile['teamwork']), 10)
                self.assertTrue(12 <= bot['commit_seconds'] <= 20)
            for team in ('allies', 'axis'):
                stars = [b for b in result['bots'] if b['team'] == team and b['standout_active']]
                self.assertLessEqual(len(stars), 1)
        self.assertGreater(len(seen), 240)

    def test_map_and_mode_are_part_of_seed(self):
        self.assertEqual(len({match_seed(17, m, g) for m in ('mp_raid', 'mp_hijacked', 'mp_carrier') for g in ('dom', 'tdm', 'ctf')}), 9)

    def test_unknown_human_duplicate_slots_and_invalid_context_fail_closed(self):
        bad = []
        for key, value in [('alias', 'Unlisted human'), ('slot', True), ('slot', 18), ('team', 'spectator')]:
            roster = copy.deepcopy(self.roster); roster[0][key] = value; bad.append(roster)
        roster = copy.deepcopy(self.roster); roster[1]['slot'] = roster[0]['slot'];bad.append(roster)
        roster = copy.deepcopy(self.roster); roster[1]['alias'] = roster[0]['alias'];bad.append(roster)
        bad.extend(([], self.roster * 2))
        for roster in bad:
            with self.subTest(roster=roster), self.assertRaises(ValueError): plan(roster, 17, 'mp_raid', 'dom')
        for seed, name, mode in [(0,'mp_raid','dom'),(True,'mp_raid','dom'),(65521,'mp_raid','dom'),(1,'../bad','dom'),(1,'mp_raid','unknown')]:
            with self.assertRaises(ValueError): plan(self.roster, seed, name, mode)

    def test_fewer_bot_slots_never_adds_humans_or_invents_roster(self):
        for count in range(1, 17):
            result = plan(self.roster[:count], 88, 'mp_carrier', 'ctf')
            self.assertEqual(len(result['bots']), count)
            self.assertEqual({b['alias'] for b in result['bots']}, {b['alias'] for b in self.roster[:count]})

    def test_assignment_scores_favor_roles_and_respect_commitment(self):
        base = {'role':'objective', 'aggression':60, 'teamwork':60, 'standout_active':False}
        support = dict(base, role='support')
        self.assertGreater(duty_score(base,'attack'), duty_score(support,'attack'))
        self.assertGreater(duty_score(support,'defend'), duty_score(base,'defend'))
        self.assertGreater(duty_score(support,'attack',True,True), duty_score(base,'attack'))
        self.assertLess(duty_score(base,'attack',False,True), duty_score(support,'attack'))

    def test_malformed_or_unsafe_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.json'
            data={'schema_version':1,'profiles':copy.deepcopy(self.profiles)}
            alias=next(iter(data['profiles']));data['profiles'][alias]['aggression']=True
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_profiles(path)

    def test_hash_stays_within_native_safe_arithmetic(self):
        for seed in (0, 1, 65520):
            self.assertTrue(0 <= hash_text('NightLedger:class:18', seed) < 65521)
        with self.assertRaises(ValueError):hash_text('a;quit')

    def test_spacing_and_expiring_danger_are_soft_position_costs(self):
        baseline=position_cost(100000,100000,1,0,0)
        self.assertGreater(position_cost(100000,100000,1,1,0),baseline)
        self.assertGreater(position_cost(100000,100000,1,0,45),position_cost(100000,100000,1,0,10))
        self.assertGreater(position_cost(100000,100000,0,0,0),position_cost(100000,100000,2,0,0))
        for args in ((True,100,1,0,0),(100,100,3,0,0),(100,100,1,18,0),(100,100,1,0,46)):
            with self.assertRaises(ValueError):position_cost(*args)

    def test_ranked_favorites_normalize_attachments_and_reduce_duplicates(self):
        p=self.profiles['Trailblazer'];a,b,c=p['favorite_primaries']
        self.assertGreater(favorite_weight(p,a),favorite_weight(p,b))
        self.assertGreater(favorite_weight(p,b),favorite_weight(p,c))
        self.assertEqual(favorite_weight(p,a+'+reflex+extclip'),favorite_weight(p,a))
        self.assertLess(favorite_weight(p,a,2),favorite_weight(p,a,0))
        self.assertEqual(favorite_weight(p,a,17),1)
        self.assertEqual(favorite_weight(p,'hk416_mp'),4)
        for weapon,duplicates in [('bad;quit',0),(a,True),(a,18)]:
            with self.assertRaises(ValueError):favorite_weight(p,weapon,duplicates)


if __name__ == '__main__':unittest.main()
