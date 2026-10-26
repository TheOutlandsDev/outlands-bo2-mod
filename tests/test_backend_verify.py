"""Backend integration report boundaries, using synthetic records only."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import tempfile
import unittest

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


class BackendReportTests(unittest.TestCase):
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
        # The harness is staged explicitly in disposable state, never the live payload.
        source = (verify.ROOT / 'hosting/entrypoint.py').read_text()
        self.assertNotIn('Path("scripts/mp/outlands_backend_verification.gsc")', source)


if __name__ == '__main__':
    unittest.main()
