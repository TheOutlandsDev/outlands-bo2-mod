"""Disposable offline container bootstrap acceptance; fixture OAuth only."""
import argparse,json,re,subprocess,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOCKER=str(ROOT/'hosting/docker.sh')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true',help='create and remove disposable fixture resources')
    parser.add_argument('--image',default='outlands-bo2-accounts:dev')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'runtime/validation/account-bootstrap')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/:@-]{0,240}',args.image):parser.error('Invalid local image reference')
    if not args.run:
        print(json.dumps({'scope':'disposable_offline_bootstrap','network':'none','live_volumes':False,'requires_run_flag':True}));raise SystemExit(0)
    args.report_dir=args.report_dir.absolute()
    if args.report_dir.exists() or any(p.is_symlink() for p in (args.report_dir,*args.report_dir.parents)):parser.error('Choose a fresh report directory without symlinks')
    args.report_dir.mkdir(parents=True,mode=0o700)
    IMAGE=args.image
    PREFIX='outlands-account-test-'+uuid.uuid4().hex
    ORIGIN='https://accounts.example.invalid'
    volumes=[PREFIX+'-'+name for name in ('state','secrets','worker')]
    container=PREFIX+'-service'
    created=[]
    container_created=False
    checks={}
    failure=False
    def call(*command,check=True):
        result=subprocess.run([DOCKER,*command],cwd=ROOT,text=True,capture_output=True,timeout=60)
        if check and result.returncode:
            error=args.report_dir/'error.log';error.write_text(result.stderr);error.chmod(0o600)
            raise RuntimeError('Fixture container action failed: '+command[0])
        return result
    common=['--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true']
    mounts=['-v',volumes[0]+':/accounts','-v',volumes[1]+':/run/outlands','-v',volumes[2]+':/agent-secrets']
    try:
        with tempfile.TemporaryDirectory(prefix='account-seed-',dir=args.report_dir) as temporary:
            seed=Path(temporary)/'fixture-google-client.json'
            seed.write_text(json.dumps({'web':{'client_id':'synthetic-client.apps.googleusercontent.com','client_secret':'synthetic_secret_12345','redirect_uris':[ORIGIN+'/auth/google/callback']}}));seed.chmod(0o600)
            for volume in volumes:call('volume','create','--label','outlands.account-verification=1',volume);created.append(volume)
            configure=['run',*common,'--user','0:0','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE',*mounts,'-v',str(seed)+':/seed/google-client.json:ro','--entrypoint','python3',IMAGE,'-B','/app/accounts/admin.py','configure','--origin',ORIGIN,'--google-client','/seed/google-client.json']
            first=call(*configure);checks['offline_configure']=first.returncode==0 and 'stored privately' in first.stdout
            checks['configure_refuses_overwrite']=call(*configure,check=False).returncode!=0
            enrollment=['run',*common,*mounts,'--entrypoint','python3',IMAGE,'-B','/app/accounts/admin.py','enroll','--server','synthetic_server_001']
            first=call(*enrollment);checks['rootless_enroll']=first.returncode==0 and 'stored privately' in first.stdout
            checks['enroll_refuses_overwrite']=call(*enrollment,check=False).returncode!=0
            verify="from pathlib import Path;import os,json;from accounts.store import AccountStore;p=Path('/run/outlands');k=(p/'identity.key').read_bytes();c=Path('/agent-secrets/server.credential').read_text();s=AccountStore(Path('/accounts/accounts.sqlite3'),k);\nwith s.connection() as db:ok=s.server(db,c)=='synthetic_server_001'\nprint(json.dumps({'uid':os.getuid(),'key_bytes':len(k),'secret_mode':(p/'identity.key').stat().st_mode&511,'db_mode':Path('/accounts/accounts.sqlite3').stat().st_mode&511,'credential_mode':Path('/agent-secrets/server.credential').stat().st_mode&511,'credential_authenticates':ok}))"
            details=json.loads(call('run',*common,*mounts,'--entrypoint','python3',IMAGE,'-B','-c',verify).stdout)
            checks['owned_private_storage']=details=={'uid':10001,'key_bytes':32,'secret_mode':384,'db_mode':384,'credential_mode':384,'credential_authenticates':True}
            call('run','-d','--pull','never','--label','outlands.account-verification=1','--name',container,'--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','-e','OUTLANDS_ACCOUNT_ORIGIN='+ORIGIN,'-v',volumes[0]+':/accounts','-v',volumes[1]+':/run/outlands:ro',IMAGE)
            container_created=True
            health="import urllib.request,json;r=urllib.request.Request('http://127.0.0.1:8087/healthz',headers={'Host':'accounts.example.invalid'});print(urllib.request.urlopen(r,timeout=2).read().decode())"
            for _ in range(20):
                result=call('exec',container,'python3','-B','-c',health,check=False)
                if result.returncode==0:break
                time.sleep(.2)
            checks['service_starts_with_bootstrapped_config']=result.returncode==0 and json.loads(result.stdout).get('service')=='outlands-accounts'
            privacy="import urllib.request,urllib.error,json;r=urllib.request.Request('http://127.0.0.1:8087/api/me',headers={'Host':'accounts.example.invalid'});\ntry:urllib.request.urlopen(r,timeout=2);raise SystemExit(1)\nexcept urllib.error.HTTPError as e:print(json.dumps({'status':e.code}))"
            checks['anonymous_private_data_refused']=json.loads(call('exec',container,'python3','-B','-c',privacy).stdout)['status']==401
            call('restart',container)
            for _ in range(20):
                result=call('exec',container,'python3','-B','-c',health,check=False)
                if result.returncode==0:break
                time.sleep(.2)
            checks['service_restarts_with_same_private_state']=result.returncode==0
            state=json.loads(call('inspect',container).stdout)[0]
            checks['isolated_rootless_runtime']=state['HostConfig']['NetworkMode']=='none' and not state['HostConfig'].get('PortBindings') and state['Config']['User']=='10001:10001'
            logs=call('logs',container)
            checks['fixture_secret_not_logged']='synthetic_secret_12345' not in logs.stdout+logs.stderr
    except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired):
        failure=True
    finally:
        if container_created:call('rm','-f',container,check=False)
        for volume in created:call('volume','rm',volume,check=False)
    report={'scope':'disposable_offline_bootstrap','passed':not failure and bool(checks) and all(checks.values()),'checks':checks,'real_google_login':False,'tls_enabled':False,'live_volumes_used':False,'resources_cleaned':all(call('volume','inspect',v,check=False).returncode!=0 for v in created) and (not container_created or call('inspect',container,check=False).returncode!=0)}
    path=args.report_dir/'report.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o600)
    print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] and report['resources_cleaned'] else 1)


if __name__=="__main__":
    main()
