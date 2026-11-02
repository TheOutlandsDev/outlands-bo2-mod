import copy,json,tempfile,unittest
from pathlib import Path
from ai.bot_settings import load_settings,generated_catalog,NATIVE,selected_preset
from ai.rivals import combat_tuning
from hosting.backend_verify import config_for,Case

class PresetTests(unittest.TestCase):
    def validate(self,data):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'settings.json';p.write_text(json.dumps(data));return load_settings(p)
    def test_checked_in_catalog_matches_strict_source(self):
        self.assertEqual(NATIVE.read_text(),generated_catalog(load_settings()))
    def test_all_presets_keep_four_actual_skill_tiers(self):
        for name,preset in load_settings()['presets'].items():
            rows=[combat_tuning(t,name) for t in ('developing','regular','experienced','standout')]
            self.assertEqual({p['difficulty'] for p in rows},{'easy','normal','hard'})
            self.assertTrue(all(a['converge_ms']>b['converge_ms'] and a['aim_error']>b['aim_error'] for a,b in zip(rows,rows[1:])))
            self.assertIn('set outlands_ai_preset '+name+'\n',config_for(Case('mp_raid','tdm'),60,False,False,ai_preset=name))
        self.assertGreater(combat_tuning('regular','relaxed')['smooth_ms'],combat_tuning('regular','competitive')['smooth_ms'])
    def test_schema_rejects_unsafe_or_unknown_fields(self):
        cases=[('engine','yaw_speed',True),('engine','yaw_speed',1.4),('engine','reaction_min_ms',2001),('engine','reaction_max_ms',500),('guard','hold_min_ms',0),('guard','hold_max_ms',100),('guard','travel_timeout_ms',-1),('guard','min_step_units',999)]
        for group,key,value in cases:
            d=copy.deepcopy(load_settings());d['presets']['mixed'][group][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.validate(d)
        d=load_settings();d['presets']['mixed']['combat']['regular']['difficulty']='fu'
        with self.assertRaises(ValueError):self.validate(d)
        for bad in ('missing','mixed\nset bad 1',True,None):
            with self.assertRaises(ValueError):selected_preset(bad)
    def test_import_rejects_duplicate_nonfinite_and_symlink_sources(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.json'
            for raw in ('{"schema_version":1,"schema_version":1}', '{"yaw_speed":NaN}'):
                p.write_text(raw)
                with self.assertRaises(ValueError):load_settings(p)
            link=Path(d)/'link';link.symlink_to(p)
            with self.assertRaises(ValueError):load_settings(link)
    def test_exports_round_trip_and_reject_unknown_schema(self):
        d=load_settings();name='relaxed';d['presets']={name:d['presets'][name]};d['default_preset']=name
        self.assertEqual(self.validate(d),d)
        d['unknown']=1
        with self.assertRaises(ValueError):self.validate(d)
