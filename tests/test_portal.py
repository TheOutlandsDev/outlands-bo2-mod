"""Portal boundary tests: native telemetry, privacy, freshness and HTTP access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('outlands_portal', Path(__file__).resolve().parents[1]/'portal/portal.py')
PORTAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTAL)
SAMPLE = 'OUTLANDS_PORTAL_V1|mp_raid|dom|playing|15000|2|14|8|8|41|39|120|team_points|30|12|0|team_eliminations|20|20|1'
MAPS = {'mp_raid': 'Raid'}


class TelemetryTests(unittest.TestCase):
    def test_native_contracts_and_population(self):
        result = PORTAL.parse_snapshot(SAMPLE, MAPS)
        self.assertEqual((result['humans'], result['bots']), (2, 14))
        self.assertEqual(result['teams'][0]['score'], 41)
        self.assertEqual(result['contracts'][0]['progress'], 12)
        self.assertTrue(result['contracts'][1]['complete'])
        self.assertEqual(PORTAL.parse_snapshot('\x1b[38;2;255;255;255m'+SAMPLE, MAPS), result)

    def test_fail_closed_malformed_and_embedded_records(self):
        bad = [None, '', SAMPLE+'|extra', 'chat: '+SAMPLE, SAMPLE.replace('mp_raid','mp_missing'),
               SAMPLE.replace('|dom|', '|unknown|'), SAMPLE.replace('|playing|', '|invented|'),
               SAMPLE.replace('|2|14|8|8|','|8|14|8|8|'), SAMPLE.replace('|2|14|8|8|','|2|14|18|18|'),
               SAMPLE.replace('|120|','|-1|'), SAMPLE.replace('|120|','|999|'),
               SAMPLE.replace('|team_points|','|arbitrary|'), SAMPLE.replace('|30|12|','|0|12|'),
               SAMPLE.replace('|30|12|0|','|30|12|2|'), SAMPLE.replace('|15000|','|1.5|'),
               SAMPLE.replace('|15000|','|015000|'), SAMPLE.replace('|15000|','|2147483648|')]
        for value in bad[1:]:
            with self.subTest(value=value):
                self.assertIsNone(PORTAL.parse_snapshot(value, MAPS))

    def test_ffa_contracts_unavailable(self):
        line = 'OUTLANDS_PORTAL_V1|mp_raid|dm|waiting|0|0|16|0|0|0|0|0|none|0|0|0|none|0|0|0'
        self.assertEqual(PORTAL.parse_snapshot(line, MAPS)['contracts'][0]['kind'], 'none')
        self.assertIsNone(PORTAL.parse_snapshot(line.replace('|none|0|0|0','|none|0|2|0',1), MAPS))

    def test_only_allowlisted_fictional_aggregate_fields_leave_exporter(self):
        state = {'schema_version':1, 'sessions':{'secret':'human'}, 'retired':['secret'],
                 'careers':{'Fictional':{'xp':300000,'kills':23,'deaths':15,'observed_rounds':2,
                             'role':'support','human_guid':'secret'},
                            'HumanName':{'xp':1,'kills':1,'deaths':1,'observed_rounds':1}}}
        result = PORTAL.rival_view(state, {'Fictional':{}})
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]['prestige'],result[0]['level']), (1,6))
        self.assertNotIn('secret', json.dumps(result))
        self.assertNotIn('HumanName', json.dumps(result))
        self.assertEqual(set(result[0]), {'alias','role','level','prestige','kills','deaths','rounds'})
        state['careers']['Fictional']['xp'] = True
        self.assertEqual(PORTAL.rival_view(state, {'Fictional':{}}), [])

    def test_no_startup_replay_partial_records_rotation_or_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'console.log'
            path.write_text(SAMPLE+'\n')
            follower = PORTAL.LogFollower(path)
            self.assertEqual(follower.poll(), [])
            with path.open('a') as stream: stream.write(SAMPLE[:50])
            self.assertEqual(follower.poll(), [])
            with path.open('a') as stream: stream.write(SAMPLE[50:]+'\n')
            self.assertEqual(follower.poll(), [SAMPLE])
            self.assertEqual(follower.poll(), [])
            path.rename(Path(temporary)/'old.log'); path.write_text(SAMPLE+'\n')
            self.assertEqual(follower.poll(), [SAMPLE])
            path.write_text('short\n'); self.assertEqual(follower.poll(), ['short'])

    def test_missing_log_can_appear_later(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'console.log'; follower = PORTAL.LogFollower(path)
            self.assertEqual(follower.poll(), [])
            path.write_text(SAMPLE+'\n'); self.assertEqual(follower.poll(), [SAMPLE])

    def test_bounded_files_and_atomic_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'status.json'
            PORTAL.atomic_json(path, {'schema':1})
            self.assertEqual(PORTAL.load_json(path), {'schema':1})
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            linked = Path(temporary)/'link.json'; linked.symlink_to(path)
            with self.assertRaises(ValueError): PORTAL.load_json(linked)
            path.write_bytes(b'x'*(PORTAL.MAX_BYTES+1))
            with self.assertRaises(ValueError): PORTAL.load_json(path)

    def test_native_acceptance_requires_real_complete_aggregate_records(self):
        spec = importlib.util.spec_from_file_location('portal_native_assessor', Path(__file__).resolve().parents[1]/'hosting/backend_verify.py')
        backend = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = backend
        spec.loader.exec_module(backend)
        case = backend.Case('mp_raid', 'dom')
        record = SAMPLE.replace('|2|14|8|8|','|0|16|8|8|')
        self.assertTrue(backend.assess_portal('\n'.join([record]*3), case)['passed'])
        for raw in (record, '\n'.join(['chat: '+record]*3), '\n'.join([record,record,record+'|extra']), '\n'.join([SAMPLE]*3)):
            self.assertFalse(backend.assess_portal(raw,case)['passed'])

    def test_public_bind_is_refused(self):
        for address in ('0.0.0.0','192.168.1.12','::','', 'example.invalid'):
            with self.subTest(address=address), patch.dict('os.environ', {'PORTAL_BIND':address}):
                with self.assertRaises(ValueError): PORTAL.serve()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.snapshot = Path(self.temporary.name)/'status.json'
        self.patch = patch.dict('os.environ', {'PORTAL_SNAPSHOT':str(self.snapshot)})
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.server = PORTAL.PortalServer(('127.0.0.1',0), PORTAL.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
    def request(self, path, method='GET'):
        try:
            return urllib.request.urlopen(urllib.request.Request(self.base+path, method=method), timeout=2)
        except urllib.error.HTTPError as error:
            return error
    def test_exact_static_routes_and_browser_policy(self):
        with self.request('/') as response:
            self.assertEqual(response.status,200)
            self.assertIn(b'Outlands / Operations', response.read())
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        for path in ('/app.js','/app.css','/healthz'):
            with self.request(path) as response: self.assertEqual(response.status,200)
        for path in ('/../portal.py','/%2e%2e/portal.py','/status.json','/rivals/careers.json','/api/player','//api/status'):
            with self.request(path) as response: self.assertIn(response.status, (404,503))
    def test_all_writes_refused_and_head_has_no_body(self):
        for method in ('POST','PUT','PATCH','DELETE'):
            with self.request('/api/status',method) as response: self.assertEqual(response.status,405)
        with self.request('/', 'HEAD') as response:
            self.assertEqual(response.status,200); self.assertEqual(response.read(),b'')
    def test_fresh_snapshot_and_stale_export_failure(self):
        with self.request('/api/status') as response: self.assertEqual(response.status,503)
        for stamp in (time.time()-21, time.time()+10, float('inf'), 'invalid'):
            self.snapshot.write_text(json.dumps({'schema':1,'generated_at':stamp}))
            with self.request('/api/status') as response: self.assertEqual(response.status,503)
        PORTAL.atomic_json(self.snapshot, {'schema':1,'generated_at':time.time(),'live':False,'match':None})
        with self.request('/api/status') as response:
            self.assertEqual(response.status,200); self.assertFalse(json.load(response)['live'])


if __name__ == '__main__': unittest.main()
