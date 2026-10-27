"""Google flow state/nonce tests and real RSA JWT checks with fixture certs only."""
import base64
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from accounts.google_login import Config,GoogleLogin,LoginRefused,https_origin,verify_google

CONFIG=Config('https://accounts.example.invalid','synthetic-client.apps.googleusercontent.com','synthetic_secret_12345')


class GoogleFlowTests(unittest.TestCase):
    def setUp(self):
        self.time=[1000];self.code=[];self.claims={}
        def exchange(config,code,verifier):self.code.append((config,code,verifier));return 'fixture.token'
        def verify(token,audience):return self.claims
        self.login=GoogleLogin(CONFIG,lambda:self.time[0],exchange,verify)
    def begin(self):
        pending=self.login.begin();query=parse_qs(urlsplit(pending['url']).query)
        self.claims={'iss':'https://accounts.google.com','aud':CONFIG.client_id,'sub':'123456789', 'nonce':query['nonce'][0]}
        return pending,query
    def finish(self,pending,query):return self.login.finish(query['state'][0],pending['cookie'],'fixture-code')
    def test_authorization_is_minimal_and_pkce_s256_matches_verifier(self):
        pending,query=self.begin()
        self.assertEqual(query['scope'],['openid']);self.assertEqual(query['response_type'],['code'])
        self.assertEqual(query['redirect_uri'],[CONFIG.callback]);self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertEqual(self.finish(pending,query),{'issuer':'https://accounts.google.com','subject':'123456789'})
        import hashlib
        challenge=base64.urlsafe_b64encode(hashlib.sha256(self.code[0][2].encode()).digest()).decode().rstrip('=')
        self.assertEqual(query['code_challenge'],[challenge]);self.assertNotIn(CONFIG.client_secret,pending['url'])
    def test_state_bound_to_browser_cookie_and_one_use(self):
        pending,query=self.begin()
        with self.assertRaises(LoginRefused):self.login.finish(query['state'][0],'different-cookie','code')
        self.assertEqual(len(self.code),0)
        self.finish(pending,query)
        with self.assertRaises(LoginRefused):self.finish(pending,query)
    def test_expired_or_clock_reversed_login_refused(self):
        for delta in (300,-1):
            pending,query=self.begin();self.time[0]+=delta
            with self.assertRaises(LoginRefused):self.finish(pending,query)
    def test_nonce_issuer_audience_authorized_party_and_subject_required(self):
        for update in ({'nonce':'wrong'},{'iss':'https://forged.invalid'},{'aud':'wrong'},{'azp':'wrong'},{'sub':'email@example.invalid'},{'sub':''}):
            pending,query=self.begin();self.claims.update(update)
            with self.assertRaises(LoginRefused):self.finish(pending,query)
    def test_failed_exchange_does_not_replay_callback_or_leak_errors(self):
        pending,query=self.begin()
        self.login.exchange=lambda *args:(_ for _ in ()).throw(ValueError('sensitive fixture token'))
        with self.assertRaises(LoginRefused) as error:self.finish(pending,query)
        self.assertNotIn('sensitive',str(error.exception))
        with self.assertRaises(LoginRefused):self.finish(pending,query)
    def test_pending_capacity_and_cookie_hash_only(self):
        pending,_=self.begin()
        self.assertNotIn(pending['cookie'],repr(self.login.pending))
        with patch('accounts.google_login.MAX_PENDING',1),self.assertRaises(LoginRefused):self.login.begin()
    def test_config_requires_https_and_exact_registered_callback(self):
        for origin in ('http://accounts.example.invalid','https://user:pass@accounts.example.invalid','https://accounts.example.invalid/path','https://accounts.example.invalid?x=1','https://accounts.example.invalid:444','https://bad_host.invalid'):
            with self.subTest(origin=origin),self.assertRaises(LoginRefused):https_origin(origin)
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'google.json'
            value={'web':{'client_id':CONFIG.client_id,'client_secret':CONFIG.client_secret,'redirect_uris':[CONFIG.callback]}}
            path.write_text(json.dumps(value));self.assertEqual(Config.load(CONFIG.origin,path),CONFIG)
            value['web']['redirect_uris']=['https://other.invalid/auth/google/callback'];path.write_text(json.dumps(value))
            with self.assertRaises(LoginRefused):Config.load(CONFIG.origin,path)


try:
    from google.auth import jwt
    from google.auth.crypt import RSASigner
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    CRYPTO_AVAILABLE=True
except ImportError:CRYPTO_AVAILABLE=False


@unittest.skipUnless(CRYPTO_AVAILABLE,'Pinned Google auth dependencies required; container/CI runs these checks')
class GoogleSignatureTests(unittest.TestCase):
    def setUp(self):
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        private=self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        self.signer=RSASigner.from_string(private.decode(),key_id='fixture-key')
        public=self.key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        self.patch=patch('google.oauth2.id_token._fetch_certs',return_value={'fixture-key':public});self.patch.start();self.addCleanup(self.patch.stop)
        now=int(time.time());self.claims={'iss':'https://accounts.google.com','aud':CONFIG.client_id,'sub':'123456789','iat':now-10,'exp':now+300}
    def signed(self,claims=None,signer=None):return jwt.encode(signer or self.signer,claims or self.claims).decode()
    def test_real_official_verifier_accepts_signed_expected_audience(self):
        self.assertEqual(verify_google(self.signed(),CONFIG.client_id)['sub'],'123456789')
    def test_signature_audience_expiry_and_issuer_fail_closed(self):
        for change in ({'aud':'other-client'},{'iss':'https://forged.invalid'},{'exp':int(time.time())-5}):
            with self.subTest(change=change),self.assertRaises(ValueError):verify_google(self.signed(self.claims|change),CONFIG.client_id)
        other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        private=other.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        with self.assertRaises(ValueError):verify_google(self.signed(signer=RSASigner.from_string(private,key_id='fixture-key')),CONFIG.client_id)
        with self.assertRaises(ValueError):verify_google('not-a-signed-token',CONFIG.client_id)


if __name__=='__main__':unittest.main()
