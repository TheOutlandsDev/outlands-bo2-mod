#!/usr/bin/env python3
"""Read-only native observations to the account service, plus one fixed mailbox.

No model, arbitrary console commands, profile file uploads or browser inputs.
"""
import json
from collections import deque
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
ACK=re.compile(r'OUTLANDS_ACCOUNT_ACK_V1\|([A-Za-z0-9_-]{16,100})_([1-9][0-9]{0,9})\Z')


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


def request_key(event):
    if (not isinstance(event,dict) or event.get('kind')!='link'
        or not isinstance(event.get('session'),str) or not TOKEN.fullmatch(event['session'])
        or type(event.get('sequence')) is not int or not 1<=event['sequence']<=2147483647
        or type(event.get('slot')) is not int or not 0<=event['slot']<=17):
        raise ValueError('Invalid pairing request')
    return event['session']+'_'+str(event['sequence'])


def pairing_packet(event,result,password,port):
    key=request_key(event)
    code=result.get('code') if isinstance(result,dict) else None
    if not isinstance(code,str) or not re.fullmatch(r'[0-9A-F]{32}',code):raise ValueError('Invalid pairing response')
    if not isinstance(password,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',password) or type(port) is not int or not 1<=port<=65535:
        raise ValueError('Invalid private transport')
    value=key+'|'+str(event['slot'])+'|'+code
    command='set outlands_account_response "'+value+'"'
    return b'\xff\xff\xff\xffrcon '+password.encode()+b' '+command.encode()


def send_packet(packet,address):
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.sendto(packet,address)


def deliver(event,result,password,port,sender=None):
    return (sender or send_packet)(pairing_packet(event,result,password,port),('127.0.0.1',port))


class PairingDelivery:
    """One active fixed mailbox; native consumption ACK, finite retries/age.

    ACK means consumed, not that a player linked or even displayed a code.
    Native session/sequence/slot checks remain the only display authority.
    The same one-use code is retried; HTTP never issues a new code for a retry.
    """
    MAX_PENDING=18
    MAX_ATTEMPTS=6
    RETRY_SECONDS=.8
    MAX_AGE=8

    def __init__(self,sender=None,clock=None):
        self.sender=sender or send_packet;self.clock=clock or time.monotonic
        self.pending=deque();self.active=None
        self.attempts=0;self.consumed=0;self.expired=0

    def observe(self,event):
        def stale(item):
            return item['slot']==event['slot'] and (item['session']!=event['session'] or event['kind'] in ('hello','depart'))
        if self.active and stale(self.active):self.active=None
        self.pending=deque(item for item in self.pending if not stale(item))

    def clear(self):
        self.active=None;self.pending.clear()

    def add(self,event,result,password,port,received=None):
        key=request_key(event);packet=pairing_packet(event,result,password,port)
        now=self.clock();received=now if received is None else received
        if self.active and self.active['slot']==event['slot']:self.active=None
        self.pending=deque(item for item in self.pending if item['slot']!=event['slot'])
        if len(self.pending)+(self.active is not None)>=self.MAX_PENDING:raise ValueError('Pairing delivery capacity reached')
        self.pending.append({'key':key,'slot':event['slot'],'session':event['session'],
                             'packet':packet,'address':('127.0.0.1',port),'expires':received+self.MAX_AGE,
                             'attempts':0,'next':now})

    def acknowledge(self,line):
        if not isinstance(line,str) or len(line)>256:return False
        clean=ANSI.sub('',line).strip('\r\n');match=ACK.fullmatch(clean)
        if not match or int(match[2])>2147483647 or not self.active or self.clock()>=self.active['expires']:return False
        if clean.split('|',1)[1]!=self.active['key']:return False
        self.active=None;self.consumed+=1;return True

    def service(self):
        now=self.clock()
        if self.active and (now>=self.active['expires'] or self.active['attempts']>=self.MAX_ATTEMPTS and now>=self.active['next']):
            self.active=None;self.expired+=1
        while not self.active and self.pending:
            item=self.pending.popleft()
            if now>=item['expires']:self.expired+=1
            else:self.active=item
        if self.active and now>=self.active['next']:
            item=self.active;item['attempts']+=1;self.attempts+=1;item['next']=now+self.RETRY_SECONDS
            try:self.sender(item['packet'],item['address'])
            except OSError:pass # A lost/failed datagram gets the same bounded retry.


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
    delivery=PairingDelivery()
    print('Outlands account follower ready; native human observations only',flush=True)
    while True:
        for line in follower.poll():
            clean=ANSI.sub('',line).strip('\r\n')
            if clean=='OUTLANDS_ACCOUNT_READY_V1':delivery.clear()
            delivery.acknowledge(line)
            event=parse_event(line)
            if event:
                received=time.monotonic();delivery.observe(event)
                try:
                    result=submit(opener,url,credential,event,host)
                    if event['kind']=='link':delivery.add(event,result,password,port,received)
                except (OSError,ValueError,KeyError):
                    print('Account observation unavailable; next live observation will retry',flush=True)
            delivery.service()
        expired=delivery.expired;delivery.service()
        if delivery.expired>expired:print('Account delivery expired; request a fresh private link code',flush=True)
        time.sleep(.25)


if __name__=='__main__':main()
