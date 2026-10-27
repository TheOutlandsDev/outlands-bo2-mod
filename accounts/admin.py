#!/usr/bin/env python3
"""Offline provisioning. Writes new private files; never prints their contents."""
import argparse
import os
from pathlib import Path
import secrets

try:
    from .store import AccountStore
    from .google_login import Config
except ImportError:
    from store import AccountStore
    from google_login import Config


def new_file(path,raw):
    if path.is_symlink() or path.exists():raise ValueError('Private output already exists; preserve it')
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def configure_files(private, origin, source, owner=None):
    Config.load(origin,source)
    outputs=(private/'google-client.json',private/'identity.key')
    if any(p.exists() or p.is_symlink() for p in outputs):raise ValueError('Existing account secrets must be preserved')
    private.mkdir(parents=True,mode=0o700,exist_ok=True)
    # Image-seeded volumes already belong to the runtime UID and are mode 700.
    # Root with only CHOWN/DAC_OVERRIDE cannot chmod another UID's directory;
    # avoid requiring FOWNER for an operation that would not change its mode.
    if private.stat().st_mode & 0o777 != 0o700:
        private.chmod(0o700)
    created=[]
    try:
        for path,raw in zip(outputs,(source.read_bytes(),secrets.token_bytes(32))):
            new_file(path,raw);created.append(path)
            if owner is not None:os.chown(path,owner,owner)
        if owner is not None:os.chown(private,owner,owner)
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise


def enroll_file(store, server, output):
    if output.is_symlink() or output.exists():raise ValueError('Existing worker credential must be preserved')
    created=[]
    def persist(credential):
        new_file(output,credential.encode());created.append(output)
    try:store.enroll_server(server,persist)
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    configure=commands.add_parser('configure');configure.add_argument('--origin',required=True);configure.add_argument('--google-client',type=Path,required=True)
    enroll=commands.add_parser('enroll');enroll.add_argument('--server',required=True)
    args=parser.parse_args();private=Path('/run/outlands')
    if args.action=='configure':
        if os.getuid()!=0:raise ValueError('Offline bootstrap requires container root to assign ownership')
        configure_files(private,args.origin,args.google_client,10001)
        print('Account OAuth configuration and identity key stored privately')
    else:
        store=AccountStore(Path('/accounts/accounts.sqlite3'),(private/'identity.key').read_bytes())
        output=Path('/agent-secrets/server.credential')
        enroll_file(store,args.server,output)
        print('Game worker enrolled; credential stored privately')


if __name__=='__main__':main()
