"""Google authorization-code login with state, PKCE, nonce and official verification.

No Google password, email, name, access token or ID token is persisted. User
subjects become private keyed hashes in AccountStore after verification.
"""
from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ISSUER='https://accounts.google.com'
AUTHORIZATION='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT='https://oauth2.googleapis.com/token'
TTL=300
MAX_PENDING=256


class LoginRefused(ValueError):
    pass


def https_origin(value):
    if not isinstance(value,str):raise LoginRefused('HTTPS account origin required')
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.port not in (None,443):
        raise LoginRefused('HTTPS account origin required')
    if len(parsed.hostname)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',part) for part in parsed.hostname.split('.')):
        raise LoginRefused('Invalid account host')
    return 'https://'+parsed.hostname.lower()


@dataclass(frozen=True)
class Config:
    origin:str
    client_id:str
    client_secret:str
    @property
    def callback(self):return self.origin+'/auth/google/callback'
    @classmethod
    def load(cls, origin, path):
        origin=https_origin(origin);path=Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:
            raise LoginRefused('Private Google OAuth client file required')
        value=json.loads(path.read_text())['web']
        client=value.get('client_id');secret=value.get('client_secret');redirects=value.get('redirect_uris')
        if not isinstance(client,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}\.apps\.googleusercontent\.com',client) or not isinstance(secret,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}',secret):
            raise LoginRefused('Invalid Google OAuth client configuration')
        if not isinstance(redirects,list) or origin+'/auth/google/callback' not in redirects:
            raise LoginRefused('Google OAuth callback does not match private origin')
        return cls(origin,client,secret)


def exchange(config, code, verifier):
    body=urlencode({'code':code,'client_id':config.client_id,'client_secret':config.client_secret,
                    'redirect_uri':config.callback,'grant_type':'authorization_code','code_verifier':verifier}).encode()
    # Fixed official endpoint. Refuse HTTP redirects instead of forwarding the
    # confidential request to a destination supplied by a remote response.
    from urllib.request import HTTPRedirectHandler,build_opener
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=build_opener(NoRedirect())
    with opener.open(Request(TOKEN_ENDPOINT,data=body,headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=10) as response:
        raw=response.read(32769)
    if len(raw)>32768:raise LoginRefused('Google response rejected')
    result=json.loads(raw)
    value=result.get('id_token')
    if not isinstance(value,str) or not 1<=len(value)<=16384:raise LoginRefused('Google response rejected')
    return value


def verify_google(value, client_id):
    # Verification includes Google's signature, token lifetime, issuer and
    # expected audience. No decode-only JWT or tokeninfo trust shortcut.
    import requests
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2.id_token import verify_oauth2_token
    session=requests.Session();session.trust_env=False
    class BoundedRequest(GoogleRequest):
        def __call__(self,*args,**kwargs):
            kwargs['timeout']=5
            return super().__call__(*args,**kwargs)
    try:return verify_oauth2_token(value,BoundedRequest(session=session),audience=client_id)
    except Exception:raise LoginRefused('Google token could not be verified') from None
    finally:session.close()


class GoogleLogin:
    def __init__(self,config,clock=time.time,exchanger=exchange,verifier=verify_google):
        self.config=config;self.clock=clock;self.exchange=exchanger;self.verify=verifier
        self.pending={};self.lock=threading.Lock()
    def begin(self):
        now=self.clock()
        with self.lock:
            self.pending={k:v for k,v in self.pending.items() if 0<=now-v['created']<TTL}
            if len(self.pending)>=MAX_PENDING:raise LoginRefused('Sign-in busy; retry shortly')
            state=secrets.token_urlsafe(32);cookie=secrets.token_urlsafe(32)
            nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
            self.pending[state]={'created':now,'cookie':hashlib.sha256(cookie.encode()).digest(),'nonce':nonce,'verifier':verifier}
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params={'client_id':self.config.client_id,'redirect_uri':self.config.callback,'response_type':'code',
                'scope':'openid','state':state,'nonce':nonce,'code_challenge':challenge,
                'code_challenge_method':'S256','prompt':'select_account'}
        return {'url':AUTHORIZATION+'?'+urlencode(params),'cookie':cookie}
    def finish(self,state,cookie,code):
        if not all(isinstance(v,str) and 1<=len(v)<=2048 and not any(ord(c)<32 for c in v) for v in (state,cookie,code)):
            raise LoginRefused('Google sign-in could not be confirmed')
        with self.lock:
            entry=self.pending.get(state)
            if not entry or not hmac.compare_digest(entry['cookie'],hashlib.sha256(cookie.encode()).digest()):
                raise LoginRefused('Google sign-in could not be confirmed')
            del self.pending[state]  # one use, including failed exchanges
        age=self.clock()-entry['created']
        if not 0<=age<TTL:raise LoginRefused('Google sign-in expired; retry')
        try:claims=self.verify(self.exchange(self.config,code,entry['verifier']),self.config.client_id)
        except Exception as error:raise LoginRefused('Google sign-in could not be confirmed') from None
        if not isinstance(claims,dict) or claims.get('iss') not in (ISSUER,'accounts.google.com') or claims.get('aud')!=self.config.client_id or claims.get('azp',self.config.client_id)!=self.config.client_id:
            raise LoginRefused('Google sign-in could not be confirmed')
        nonce=claims.get('nonce');subject=claims.get('sub')
        if not isinstance(nonce,str) or not hmac.compare_digest(nonce,entry['nonce']) or not isinstance(subject,str) or not re.fullmatch(r'[0-9]{1,128}',subject):
            raise LoginRefused('Google sign-in could not be confirmed')
        # Only Google's stable subject crosses into the private account core.
        return {'issuer':ISSUER,'subject':subject}
