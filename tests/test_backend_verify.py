"""Backend integration report boundaries, using synthetic records only."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = spec_from_file_location('outlands_backend_verify', Path(__file__).resolve().parents[1] / 'hosting/backend_verify.py')
verify = module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


def line(kind='complete', stage=0, **changes):
    values = dict(stage=stage, bots=16, humans=0, alive=14, playing=16, identities=16,
                  roles=16, careers=16, kills=8, deaths=8, score=800, moved=13,
                  prematch=0, invalid=0, pools=16, patrols=10, scorelimit=200)
    values.update(changes)
    return 'OUTLANDS_VERIFY_V1|' + kind + '|mp_raid|dom|' + '|'.join(str(values[k]) for k in verify.FIELDS)


def observed(stage=0, **changes):
    return line(kind='sample', stage=stage, kills=0, score=0, moved=0, pools=0, patrols=0) + '\n' + line(stage=stage, **changes)


def feature_line(kind='complete', stage=0, sequence=2, mode='dom', **changes):
    features = dict(sequence=sequence, squads_enabled=1, squad_assigned=16,
                    squad_attack=8, squad_defend=4, squad_support=4, squad_targeted=6,
                    squad_goal_calls=20, squad_goal_distinct=3, squad_invalid=0,
                    contracts_enabled=1, contract_active=2, contract_completed=2,
                    contract_commendations=2, contract_kill_progress=6,
                    contract_score_progress=600, contract_objective_progress=10,
                    contract_invalid=0, allies_bots=8, axis_bots=8)
    base = {k: value for k, value in changes.items() if k in verify.FIELDS}
    features.update({k: value for k, value in changes.items() if k in verify.FEATURE_FIELDS})
    prefix = line(kind, stage, **base).replace('OUTLANDS_VERIFY_V1|', 'OUTLANDS_VERIFY_V2|').replace('|dom|', '|'+mode+'|')
    return prefix + '|' + '|'.join(str(features[k]) for k in verify.FEATURE_FIELDS)


def feature_observed(stage=0, mode='dom', **changes):
    baseline = dict(kills=0, score=0, moved=0, pools=0, patrols=0,
                    squad_assigned=0, squad_attack=0, squad_defend=0,
                    squad_support=0, squad_targeted=0, squad_goal_calls=0,
                    squad_goal_distinct=0, contract_completed=0,
                    contract_commendations=0, contract_kill_progress=0,
                    contract_score_progress=0, contract_objective_progress=0)
    for key in ('squads_enabled', 'contracts_enabled'):
        if key in changes:
            baseline[key] = changes[key]
    return feature_line('sample', stage, 1, mode, **baseline) + '\n' + feature_line('complete', stage, 2, mode, **changes)


class ExpansionReportTests(unittest.TestCase):
    def test_native_crashes_are_distinct_from_gsc_compile_errors(self):
        for text in ("A critical exception occured!", "Exception Code: 0xC0000005", "Oops! Plutonium ran into a problem and must be closed."):
            self.assertIsNotNone(verify.NATIVE_FAILURE.search(text))
        self.assertIsNone(verify.NATIVE_FAILURE.search("OUTLANDS_EXPANSION_V1|pass"))

    def test_native_formatter_proof_requires_all_four_numbered_turns(self):
        prefix='OUTLANDS_DIALOGUE_FIXTURE_V1|OUTLANDS_CHAT_V3|'
        context='contract|allies|none|-1|none|combined_score|1|1000|1000|1|40'
        lines=['OUTLANDS_EXPANSION_V1|pass']
        names=('NightLedger','CopperWren','StaticBloom','RiftRunner')
        for turn,name in enumerate(names,1):
            request='fixture' if turn==1 else 'fixture_r'+str(turn)
            speaker='match' if turn==1 else names[turn-2]
            kind='banter' if turn==1 else 'bot_reply'
            lines.append(prefix+'|'.join((request,str(turn),name,kind,'mp_raid','dom',speaker,'Fair, same here.',context,str(turn),'4')))
        good='\n'.join(lines)
        self.assertTrue(verify.assess_expansion(good)['passed'])
        self.assertFalse(verify.assess_expansion('\n'.join(lines[:-1]))['passed'])
        self.assertFalse(verify.assess_expansion(good.replace('fixture_r3','fixture_r4'))['passed'])
        self.assertFalse(verify.assess_expansion('Player: '+good.replace('\n','\nPlayer: '))['passed'])
        self.assertFalse(verify.assess_expansion(good+'\nOUTLANDS_EXPANSION_V1|failed')['passed'])


class BackendReportTests(unittest.TestCase):
    def test_armory_editor_requires_full_native_grant_and_hud_receipt(self):
        good='OUTLANDS_ARMORY_EDITOR_V2|pass|7|25|6|2|0'
        result=verify.assess_armory_editor(good)
        self.assertTrue(result['passed'])
        self.assertFalse(result['actual_human_unlocks'])
        self.assertFalse(result['actual_human_worker_transport'])
        self.assertFalse(result['actual_client_rendering'])
        self.assertTrue(verify.assess_armory_editor(good+'\n'+good,True)['passed'])
        for bad in ('', 'Player: '+good,good+'\n'+good,good.replace('|25|','|23|'),good[:-1]+'1'):
            self.assertFalse(verify.assess_armory_editor(bad)['passed'])
        cfg=verify.config_for(verify.Case('mp_raid','dom'),90,False,False,armory_editor=True)
        self.assertIn('set outlands_verify_armory_editor 1',cfg)
        self.assertNotIn('set outlands_verify_armory_editor 1',verify.config_for(verify.Case('mp_raid','dom'),90,False,False))

    def test_armory_loopback_fixture_sender_is_fixed_bounded_and_deduplicated(self):
        class FakeDocker:
            def __init__(self):self.calls=[]
            def call(self,*args,**kwargs):self.calls.append((args,kwargs));return ''
        docker=FakeDocker()
        good='OUTLANDS_ARMORY_MAILBOX_V1|fixture_0|2|rifle,pistol,perk_1,perk_2,perk_3,frag,flash'
        sent=verify.service_armory_mailboxes(docker,'worker',good,set())
        self.assertEqual(sent,{'fixture_0'})
        self.assertEqual(len(docker.calls),1)
        self.assertIn('send_armory',docker.calls[0][0][-1])
        self.assertEqual(docker.calls[0][1]['input_text'],'fixture_0|2|cancelled|1|rifle,pistol,perk_1,perk_2,perk_3,frag,flash')
        verify.service_armory_mailboxes(docker,'worker',good,sent)
        for bad in ('Player: '+good,good.replace('|2|','|18|'),good.replace('rifle,','rifle;quit,'),good+',extra'):
            verify.service_armory_mailboxes(docker,'worker',bad,set())
        self.assertEqual(len(docker.calls),1)
    def test_armory_proof_requires_native_staging_and_next_spawn_but_not_humans(self):
        good = 'OUTLANDS_ARMORY_V1|pass|5|1|1|1|1|1'
        result = verify.assess_armory(good)
        self.assertTrue(result['passed'])
        self.assertFalse(result['actual_human_unlocks'])
        self.assertFalse(result['custom_class_materialization'])
        self.assertFalse(result['actual_client_editor'])
        self.assertTrue(verify.assess_armory(good+'\n'+good,restart=True)['passed'])
        for bad in ('', 'Player: '+good, good+'\n'+good, good+'\nOUTLANDS_ARMORY_V1|failed',
                    good.replace('|5|','|0|'), good[:-1]+'0', 'OUTLANDS_ARMORY_V1|pass'):
            self.assertFalse(verify.assess_armory(bad)['passed'])
        self.assertFalse(verify.assess_armory(good,restart=True)['passed'])
        cfg = verify.config_for(verify.Case('mp_raid','dom'),60,False,False,armory=True)
        self.assertIn('set outlands_verify_armory 1',cfg)

    def test_ui_requires_exact_native_allocation_cleanup_evidence_per_stage(self):
        good = 'OUTLANDS_UI_V1|pass|29|6|16|0'
        result = verify.assess_ui(good)
        self.assertTrue(result['passed'])
        self.assertFalse(result['actual_human_commands'])
        self.assertFalse(result['actual_client_rendering'])
        self.assertTrue(verify.assess_ui(good+'\n'+good, restart=True)['passed'])
        for bad in ('', 'Player: '+good, good+'\n'+good,
                    good.replace('|0','|1'), good+'\nOUTLANDS_UI_V1|failed',
                    'OUTLANDS_UI_V1|pass'):
            self.assertFalse(verify.assess_ui(bad)['passed'])
        self.assertFalse(verify.assess_ui(good, restart=True)['passed'])

    def test_ui_probe_switch_is_explicit_and_disposable(self):
        plain = verify.config_for(verify.Case('mp_raid','dom'),60,False,False)
        enabled = verify.config_for(verify.Case('mp_raid','dom'),60,False,False,ui=True)
        self.assertNotIn('set outlands_verify_ui 1',plain)
        self.assertIn('set outlands_ui 1\nset outlands_verify_ui 1',enabled)

    def test_restart_plan_names_full_reload_and_keeps_client_acceptance_separate(self):
        with patch('builtins.print') as output:
            self.assertEqual(verify.main(['--restart','--ui','--case','mp_slums:dm']),0)
        plan = json.loads(output.call_args.args[0])
        self.assertEqual(plan['native_restart_method'],'same_map_reload')
        self.assertTrue(plan['ui'])
        self.assertFalse(plan['human_clients'])
        self.assertFalse(plan['live_state'])

    def test_missing_map_preflight_fails_before_creating_state(self):
        class FakeDocker:
            def __init__(self, output):self.output=output;self.calls=[]
            def call(self,*args):self.calls.append(args);return self.output
        absent=FakeDocker('false')
        with self.assertRaisesRegex(ValueError,'main fastfile is missing'):
            verify.require_map_asset(absent,'synthetic-image',verify.Case('mp_standoff','koth'))
        self.assertEqual(len(absent.calls),1)
        self.assertIn('--network',absent.calls[0])
        self.assertNotIn('volume',absent.calls[0])
        present=FakeDocker('true')
        verify.require_map_asset(present,'synthetic-image',verify.Case('mp_village','koth'))

    def test_air_response_report_distinguishes_script_policy_from_aircraft_combat(self):
        marker = 'OUTLANDS_AIR_POLICY_V1|pass'
        result = verify.assess_air_response(marker)
        self.assertTrue(result['passed'])
        self.assertFalse(result['actual_aircraft_combat'])
        for bad in ('', 'Player: '+marker, marker+'\n'+marker,
                    marker+'\nOUTLANDS_AIR_POLICY_V1|failed'):
            self.assertFalse(verify.assess_air_response(bad)['passed'])

    def test_lobby_report_requires_ordered_native_repairs_and_count_policy(self):
        phases = [('baseline', (0,16,8,8)), ('deficit', (0,15,7,8)),
                  ('refilled', (0,16,8,8)), ('imbalanced', (0,16,9,7)),
                  ('rebalanced', (0,16,8,8)), ('disabled', (0,16,9,7)),
                  ('resumed', (0,16,8,8))]
        lines = ['OUTLANDS_LOBBY_V1|'+phase+'|'+'|'.join(map(str, values)) for phase, values in phases]
        good = 'OUTLANDS_PARTY_POLICY_V1|pass\nOUTLANDS_BALANCE_RESTORE_V1|pass\n'+'\n'.join(lines)
        self.assertTrue(verify.assess_lobby(good)['passed'])
        self.assertTrue(verify.assess_lobby(good.replace('|deficit|0|15|7|8', '|deficit|0|15|8|7'))['passed'])
        self.assertFalse(verify.assess_lobby(good)['human_join_acceptance'])
        bad_cases = [good+'\n'+lines[0], good.replace(lines[1]+'\n', ''),
                     good.replace(lines[0]+'\n'+lines[1], lines[1]+'\n'+lines[0]),
                     good.replace('|baseline|0|16', '|baseline|1|16'),
                     good.replace('|refilled|0|16|8|8', '|refilled|0|16|9|7'),
                     good.replace('OUTLANDS_LOBBY_V1|', 'Player: OUTLANDS_LOBBY_V1|'),
                     good.replace('OUTLANDS_PARTY_POLICY_V1|pass', 'OUTLANDS_PARTY_POLICY_V1|failed'),
                     good+'\nOUTLANDS_LOBBY_V1|baseline|invalid',
                     good+'\nOUTLANDS_PARTY_POLICY_V1|pass',
                     good.replace('OUTLANDS_BALANCE_RESTORE_V1|pass', 'OUTLANDS_BALANCE_RESTORE_V1|failed')]
        for bad in bad_cases:
            self.assertFalse(verify.assess_lobby(bad)['passed'], bad)
        self.assertTrue(verify.assess_lobby('\x1b[38;2;255;255;255m'+good)['passed'])

    def test_chat_context_requires_native_topics_guards_and_no_production_speech(self):
        prefix = 'OUTLANDS_CONTEXT_V1|3|Trailblazer|mp_raid|dom|'
        records = '\n'.join(prefix+topic+'|allies|attack|0|enemy|combined_score|1|100|1000|0|45' for topic in ('squad','objective','contract'))
        guards = '\nOUTLANDS_CHAT_GUARD_V1|rejected\nOUTLANDS_CHAT_GUARD_V1|context_disabled\nOUTLANDS_CHAT_GUARD_V1|team_binding\nOUTLANDS_CHAT_GUARD_V1|stale_assignment\nOUTLANDS_CHAT_PRIMITIVE_V1|sayall'
        good = records+guards
        case = verify.Case('mp_raid','dom')
        self.assertTrue(verify.assess_chat_context(good,case)['passed'])
        for bad in (guards, good.replace('|1000|','|0|'), good.replace('|dom|','|tdm|'), good.replace('|rejected','|failed'), good+'\nOUTLANDS_CHAT_ACK_V1|unexpected', good.replace('OUTLANDS_CHAT_PRIMITIVE_V1|sayall',''), good.replace('OUTLANDS_CHAT_GUARD_V1|team_binding',''), good.replace('OUTLANDS_CHAT_GUARD_V1|stale_assignment',''), good.replace('OUTLANDS_CONTEXT_V1|','Player: OUTLANDS_CONTEXT_V1|')):
            self.assertFalse(verify.assess_chat_context(bad,case)['passed'])

    def test_only_exact_bounded_native_sample_records_are_accepted(self):
        good = line()
        self.assertEqual(len(verify.parse_samples(good)), 1)
        self.assertEqual(len(verify.parse_samples('\x1b[38;2;255;255;255m'+good)), 1)
        for bad in ('Player: '+good, good+'|extra', good.replace('|dom|','|custom|'),
                    good.replace('|mp_raid|','|../../private|'), good.replace('|800|','|nan|'),
                    good.replace('|800|','|9999999999|')):
            self.assertEqual(verify.parse_samples(bad), [], bad)

    def test_native_gameplay_and_both_restart_stages_are_required(self):
        case = verify.Case.parse('mp_raid:dom')
        first = verify.parse_samples(observed())
        self.assertTrue(verify.assess(first, case, False)['passed'])
        self.assertFalse(verify.assess(first, case, True)['passed'])
        frozen = verify.parse_samples(line(kind='sample')+'\n'+line())
        self.assertFalse(verify.assess(frozen, case, False)['passed'])
        decline = verify.parse_samples(line(kind='sample',kills=20,score=2000)+'\n'+line())
        self.assertFalse(verify.assess(decline, case, False)['passed'])
        both = verify.parse_samples(observed()+'\n'+observed(stage=1))
        self.assertTrue(verify.assess(both, case, True)['passed'])
        for change in ({'prematch':1}, {'kills':0}, {'score':0}, {'moved':2},
                       {'bots':15}, {'identities':15}, {'roles':15}, {'humans':1}, {'invalid':1}, {'pools':0}, {'patrols':0}, {'scorelimit':0}):
            with self.subTest(change=change):
                self.assertFalse(verify.assess(verify.parse_samples(observed(**change)), case, False)['passed'])
        no_careers = verify.parse_samples(observed(careers=0))
        self.assertTrue(verify.assess(no_careers, case, False)['passed'])
        self.assertFalse(verify.assess(no_careers, case, False, careers=True)['passed'])

    def test_partial_or_wrong_case_records_cannot_establish_completion(self):
        case = verify.Case.parse('mp_raid:dom')
        self.assertFalse(verify.assess(verify.parse_samples(line(kind='sample')), case, False)['passed'])
        other = verify.Case.parse('mp_slums:conf')
        self.assertFalse(verify.assess(verify.parse_samples(line()), other, False)['passed'])

    def test_native_script_error_spellings_fail_closed(self):
        for message in ('Terminal script error', 'script error: unknown field',
                        '**** 1 script error(s):', 'Script runtime error', 'Script compile error'):
            self.assertIsNotNone(verify.FAILURE.search(message), message)
        self.assertIsNone(verify.FAILURE.search('Outlands profiles active; native scripts initialized.'))

    def test_v2_is_required_for_requested_features_and_old_evidence_stays_readable(self):
        case = verify.Case('mp_raid', 'dom')
        old = verify.parse_samples(observed())
        self.assertTrue(verify.assess(old, case, False)['passed'])
        self.assertFalse(verify.assess(old, case, False, squads=True)['passed'])
        self.assertFalse(verify.assess(old, case, False, contracts=True)['passed'])
        new = verify.parse_samples(feature_observed())
        self.assertTrue(verify.assess(new, case, False, squads=True, contracts=True)['passed'])
        self.assertFalse(verify.assess(new, case, True, squads=True, contracts=True)['passed'])
        both = verify.parse_samples(feature_observed()+'\n'+feature_observed(stage=1))
        self.assertTrue(verify.assess(both, case, True, squads=True, contracts=True)['passed'])

    def test_v2_rejects_invalid_counts_sequences_and_metadata(self):
        for changes in ({'squad_assigned':17}, {'bots':-1}, {'humans':17}, {'sequence':0},
                        {'squads_enabled':2}, {'contract_invalid':-1}, {'stage':9}):
            self.assertEqual(verify.parse_samples(feature_line(**changes)), [], changes)
        case = verify.Case('mp_raid', 'dom')
        good = verify.parse_samples(feature_observed())
        duplicate = good + [dict(good[-1])]
        self.assertFalse(verify.assess(duplicate, case, False, squads=True, contracts=True)['passed'])
        reordered = [dict(good[0], sequence=3), good[1]]
        self.assertFalse(verify.assess(reordered, case, False, squads=True, contracts=True)['passed'])
        mixed = verify.parse_samples(line(kind='sample')+'\n'+feature_line())
        self.assertFalse(verify.assess(mixed, case, False, squads=True, contracts=True)['passed'])

    def test_feature_counters_cannot_substitute_for_native_gameplay(self):
        case = verify.Case('mp_raid', 'dom')
        for changes in ({'kills':0}, {'score':0}, {'squad_assigned':15},
                        {'squad_attack':9, 'squad_support':3}, {'squad_defend':5, 'squad_support':3},
                        {'squad_targeted':13}, {'squad_goal_calls':0}, {'squad_goal_distinct':1},
                        {'squad_invalid':1}, {'contract_completed':0}, {'contract_active':1},
                        {'contract_commendations':3}, {'contract_invalid':1},
                        {'contract_kill_progress':0}, {'contract_score_progress':0},
                        {'allies_bots':7,'axis_bots':9}):
            with self.subTest(changes=changes):
                self.assertFalse(verify.assess(verify.parse_samples(feature_observed(**changes)), case, False, squads=True, contracts=True)['passed'])
        frozen = verify.parse_samples(feature_line('sample', sequence=1)+'\n'+feature_line())
        self.assertFalse(verify.assess(frozen, case, False, squads=True, contracts=True)['passed'])
        declining = verify.parse_samples(feature_line('sample', sequence=1, contract_completed=4, contract_commendations=4)+'\n'+feature_line())
        self.assertFalse(verify.assess(declining, case, False, squads=True, contracts=True)['passed'])
        # Genuine native combat growth cannot legitimize carried or duplicated
        # feature counters. These examples pass the ordinary combat criteria.
        carried = verify.parse_samples(feature_line('sample', sequence=1, kills=0, score=0)+'\n'+feature_line())
        self.assertTrue(verify.assess(verify.parse_samples(observed()), case, False)['passed'])
        failed = verify.assess(carried, case, False, squads=True, contracts=True)
        self.assertTrue(any('goal evidence' in reason for reason in failed['reasons']))
        self.assertTrue(any('completion did not increase' in reason for reason in failed['reasons']))
        declining = verify.parse_samples(feature_line('sample', sequence=1, kills=0, score=0, contract_kill_progress=10)+'\n'+feature_line())
        self.assertTrue(any('evidence decreased' in reason for reason in verify.assess(declining, case, False, squads=True, contracts=True)['reasons']))

    def test_off_and_unsupported_modes_require_no_feature_side_effects(self):
        zeros = {name: 0 for name in verify.FEATURE_FIELDS if name != 'sequence'}
        for mode, squads, contracts in (('dom',False,False), ('dm',True,True)):
            cfg = dict(zeros, scorelimit=verify.SCORE_LIMITS[mode], allies_bots=8, axis_bots=8)
            baseline = feature_line('sample', sequence=1, mode=mode, kills=0, score=0, **cfg)
            final = feature_line(mode=mode, **cfg)
            samples = verify.parse_samples(baseline+'\n'+final)
            self.assertTrue(verify.assess(samples, verify.Case('mp_raid',mode), False, squads=squads, contracts=contracts)['passed'])
            bad = verify.parse_samples(baseline+'\n'+feature_line(mode=mode, **dict(cfg, squad_goal_calls=1)))
            self.assertFalse(verify.assess(bad, verify.Case('mp_raid',mode), False, squads=squads, contracts=contracts)['passed'])

    @unittest.skipUnless(os.name == 'posix', 'Executable wrapper fixture uses a POSIX shebang')
    def test_docker_logs_preserve_stream_order_and_do_not_corrupt_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            wrapper = Path(temporary) / 'synthetic-wrapper'
            wrapper.write_text('#!' + sys.executable + '\nimport sys\n'
                               'if sys.argv[1] == "logs":\n'
                               ' print("first", flush=True)\n'
                               ' print("second", file=sys.stderr, flush=True)\n'
                               ' print("third", flush=True)\n'
                               'else:\n'
                               ' print(\'{"running":true}\', flush=True)\n'
                               ' print("private diagnostic", file=sys.stderr, flush=True)\n')
            wrapper.chmod(0o700)
            docker = verify.Docker(wrapper)
            self.assertEqual(docker.call('logs', 'synthetic'), 'first\nsecond\nthird\n')
            self.assertEqual(json.loads(docker.call('inspect', 'synthetic')), {'running': True})

    def test_runtime_switches_require_cleared_goals_frozen_accounting_and_new_native_activity(self):
        rows = [
            'OUTLANDS_SWITCH_V1|disabled_start|10|0|0|0|8|900|2|30',
            'OUTLANDS_SWITCH_V1|disabled_end|15|0|0|0|8|900|2|30',
            'OUTLANDS_SWITCH_V1|resumed|20|16|2|1|12|1400|3|40',
        ]
        self.assertTrue(verify.assess_switches('\n'.join(rows))['passed'])
        bad_rows = [rows[:2], [rows[1], rows[0], rows[2]], rows + [rows[2]],
                    [rows[0], rows[1].replace('|15|', '|10|'), rows[2]],
                    [rows[0].replace('|0|0|0|', '|0|1|0|'), *rows[1:]],
                    [rows[0], rows[1].replace('|900|', '|1000|'), rows[2]],
                    [*rows[:2], rows[2].replace('|40', '|30')],
                    [*rows[:2], rows[2].replace('|16|', '|15|')],
                    ['Player: ' + rows[0], *rows[1:]]]
        for changed in bad_rows:
            with self.subTest(rows=changed):
                self.assertFalse(verify.assess_switches('\n'.join(changed))['passed'])
        cfg = verify.config_for(verify.Case('mp_raid', 'dom'), 90, False, False, True, True, True)
        self.assertIn('set outlands_verify_switches 1', cfg)
        self.assertNotIn('outlands_verify_switches', (verify.ROOT/'storage/t6/outlands_t6.cfg').read_text())

    def test_cleanup_attempts_every_created_resource_despite_log_or_stop_failure(self):
        class FakeDocker:
            def __init__(self):
                self.calls = []
            def call(self, *args, **kwargs):
                self.calls.append(args)
                if args[0] == 'stop' and args[-1] == 'b' * 64:
                    raise RuntimeError('synthetic stop failure')
                return ''
        with tempfile.TemporaryDirectory() as temporary:
            blocked = Path(temporary) / 'report-file'
            blocked.write_text('preserve synthetic existing data')
            docker = FakeDocker()
            with self.assertRaisesRegex(RuntimeError, 'cleanup incomplete'):
                verify.cleanup_resources(docker, verify.Case('mp_raid','dom'), blocked, 'log',
                                         'a' * 64, 'b' * 64, ['synthetic-rivals','synthetic-game'])
            self.assertIn(('rm', 'a' * 64), docker.calls)
            self.assertIn(('rm', 'b' * 64), docker.calls)
            self.assertIn(('volume', 'rm', 'synthetic-game'), docker.calls)
            self.assertIn(('volume', 'rm', 'synthetic-rivals'), docker.calls)
            self.assertEqual(blocked.read_text(), 'preserve synthetic existing data')

    def test_case_validation_and_test_config_do_not_accept_console_injection(self):
        for text in ('mp_raid;quit:dom','../mp_raid:dom','mp_raid:exec evil','mp_raid:sab', 'mp_raid:dom\nquit'):
            with self.assertRaises(ValueError):
                verify.Case.parse(text)
        cfg = verify.config_for(verify.Case.parse('mp_raid:dom'), 30, True, False)
        self.assertIn('sv_maprotation "gametype dom execgts outlands_dom.cfg map mp_raid"', cfg)
        self.assertIn('set outlands_backend_verification 1', cfg)
        self.assertTrue(cfg.rstrip().endswith('set outlands_contracts 0'))
        feature_cfg = verify.config_for(verify.Case.parse('mp_raid:dom'), 60, True, True, True, True)
        self.assertIn('set outlands_squads 1', feature_cfg)
        self.assertIn('set outlands_contract_goal_scale 25', feature_cfg)
        self.assertIn('set outlands_contract_seconds 30', feature_cfg)
        shipped = (verify.ROOT / 'storage/t6/outlands_t6.cfg').read_text()
        self.assertNotIn('set outlands_contract_goal_scale 25', shipped)
        # The harness is staged explicitly in disposable state, never the live payload.
        source = (verify.ROOT / 'hosting/entrypoint.py').read_text()
        self.assertNotIn('Path("scripts/mp/outlands_backend_verification.gsc")', source)


if __name__ == '__main__':
    unittest.main()
