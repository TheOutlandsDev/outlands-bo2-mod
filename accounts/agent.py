#!/usr/bin/env python3
"""Read-only native observations to the account service, plus one fixed mailbox.

No model, arbitrary console commands, profile file uploads or browser inputs.
"""
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from portal.portal import LogFollower,ANSI

MARKER='OUTLANDS_ACCOUNT_V1|'
TOKEN=re.compile(r'[A-Za-z0-9_-]{16,100}\Z')


def parse_event(line):
    if not isinstance(line,str) or len(line)>512:return None
    line=ANSI.sub('',line).strip('\r\n')
    if not line.startswith(MARKER):return None
    fields=line[len(MARKER):].split('|')
    if len(fields)!=8:return None
    session,sequence,kind,slot,guid,xp,rank,prestige=fields
    if not TOKEN.fullmatch(session) or kind not in ('hello','snapshot','link','depart') or not re.fullmatch(r'[0-9a-fA-F]{1,32}',guid) or not int(guid,16):return None
    numbers=(sequence,slot,xp,rank,prestige)
    if any(not re.fullmatch(r'-1|0|[1-9][0-9]{0,9}',v) for v in numbers):return None
    sequence,slot,xp,rank,prestige=map(int,numbers)
    if not 1<=sequence<=2147483647 or not 0<=slot<=17 or not -1<=xp<=2147483647 or not -1<=rank<=55 or rank==0 or not -1<=prestige<=11:return None
    stats={key:value for key,value in (('rank_xp',xp),('rank_level',rank),('prestige',prestige)) if value>=0}
    return {'session':session,'sequence':sequence,'kind':kind,'slot':slot,'profile_reference':guid.lower(),'stats':stats}


def secret(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>256:raise ValueError('Private worker credential required')
    value=path.read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',value):raise ValueError('Invalid private worker credential')
    return value


def api_url(value):
    url=urlsplit(value)
    if url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
        raise ValueError('Invalid account service endpoint')
    if url.scheme!='https' and not (url.scheme=='http' and url.hostname=='127.0.0.1'):
        raise ValueError('Account transport requires HTTPS or local loopback')
    if not url.hostname:raise ValueError('Account endpoint required')
    return value.rstrip('/')+'/internal/native'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def submit(opener,url,credential,event,host):
    value={k:v for k,v in event.items() if k!='slot'}
    request=Request(url,data=json.dumps(value).encode(),headers={'Host':host,'Content-Type':'application/json','Authorization':'Bearer '+credential})
    with opener.open(request,timeout=5) as response:raw=response.read(4097)
    if len(raw)>4096:raise ValueError('Account response too large')
    return json.loads(raw)


def deliver(event,result,password,port,sender=None):
    code=result.get('code')
    if event['kind']!='link' or not isinstance(code,str) or not re.fullmatch(r'[0-9A-F]{32}',code):raise ValueError('Invalid pairing response')
    value=event['session']+'_'+str(event['sequence'])+'|'+str(event['slot'])+'|'+code
    command='set outlands_account_response "'+value+'"'
    packet=b'\xff\xff\xff\xffrcon '+password.encode()+b' '+command.encode()
    if sender:return sender(packet,('127.0.0.1',port))
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.sendto(packet,('127.0.0.1',port))


def main():
    url=api_url(os.environ['OUTLANDS_ACCOUNT_API'])
    from accounts.google_login import https_origin
    host=urlsplit(https_origin(os.environ['OUTLANDS_ACCOUNT_ORIGIN'])).netloc
    credential=secret('/run/outlands/server.credential')
    password=secret('/data/private/outlands_rcon_password')
    port=int(os.environ.get('T6_PORT','4977'))
    if not 1<=port<=65535:raise ValueError('Invalid native port')
    follower=LogFollower('/data/plutonium/console.log')
    opener=build_opener(NoRedirect(),ProxyHandler({}))
    print('Outlands account follower ready; native human observations only',flush=True)
    while True:
        for line in follower.poll():
            event=parse_event(line)
            if event:
                try:
                    result=submit(opener,url,credential,event,host)
                    if event['kind']=='link':deliver(event,result,password,port)
                except (OSError,ValueError,KeyError):
                    print('Account observation unavailable; next live observation will retry',flush=True)
        time.sleep(1)


if __name__=='__main__':main()
