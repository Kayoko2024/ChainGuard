"""Check or renew existing local mTLS certificates, preserving keys, data and identities.

Default is read-only. --apply stops only the local Web processes and the two TLS
servers, installs all peers together, then restores them. No chain reset or keys
are generated. Backups containing runtime credentials stay inside private volumes.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('ca', 'gateway-server', 'tool-server', 'gateway-client', 'tool-client', 'operator', 'agent')
MAPPING = {
    'gateway': {'ca.pem': 'ca', 'server.pem': 'gateway-server', 'client.pem': 'gateway-client'},
    'tool': {'ca.pem': 'ca', 'server.pem': 'tool-server', 'client.pem': 'tool-client'},
    **{k: {'ca.pem': 'ca', 'client.pem': 'operator'} for k in ('requester', 'biz', 'security')},
    'agent': {'ca.pem': 'ca', 'client.pem': 'agent'},
}


def fingerprint(pem):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.decode('ascii'))).hexdigest()


def metadata(path):
    value = ssl._ssl._test_decode_cert(str(path))
    return {**{k: value.get(k) for k in ('subject', 'issuer', 'subjectAltName', 'notBefore', 'notAfter')},
            'sha256': fingerprint(path.read_bytes()),
            'remaining_seconds': int(ssl.cert_time_to_seconds(value['notAfter']) - time.time())}


def pins(kind, certs):
    if kind == 'gateway':
        return {'authority_fingerprint': fingerprint(certs['tool-client']), 'operator_fingerprint': fingerprint(certs['operator'])}
    if kind == 'tool':
        return {'gateway_fingerprint': fingerprint(certs['gateway-client'])}
    return {}


def renewed_runtime(current, expected, replacement):
    if set(expected) != set(replacement) or any(current.get(k) != v for k, v in expected.items()):
        raise ValueError('Existing certificate pins differ from the original private TLS material')
    if any(not k.endswith('_fingerprint') for k in replacement):
        raise ValueError('Only explicit certificate pins may change')
    return {**current, **replacement}


class OpenSSL:
    def __init__(self):
        self.binary = shutil.which('openssl')

    def __call__(self, *args):
        if self.binary:
            command = [self.binary, *map(str, args)]
        else:
            def wsl(arg):
                s = str(arg)
                return '/mnt/' + s[0].lower() + '/' + s[3:].replace('\\', '/') if len(s) > 2 and s[1:3] == ':\\' else s
            command = ['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--exec', 'openssl', *map(wsl, args)]
        # All signing parameters/extensions are explicit; avoid a broken ambient
        # Conda OpenSSL configuration or loading an unrelated provider config.
        env = {**os.environ, 'OPENSSL_CONF': os.devnull}
        p = subprocess.run(command, capture_output=True, timeout=40, env=env)
        if p.returncode:
            raise RuntimeError('OpenSSL operation failed: ' + str(args[0]))
        return p.stdout


def renew_bundle(original, target, openssl, days=7, ca_days=365):
    if not 7 <= days <= 365 or not days < ca_days <= 3650:
        raise ValueError('Use 7..365 leaf days and a longer CA validity, at most 3650 days')
    if target.exists():
        raise ValueError('New private certificate staging directory required')
    target.mkdir(parents=True, mode=0o700)
    openssl('x509', '-in', original/'ca.pem', '-signkey', original/'ca.key', '-days', ca_days, '-out', target/'ca.pem')
    for name in NAMES[1:]:
        openssl('x509', '-in', original/(name+'.pem'), '-x509toreq', '-signkey', original/(name+'.key'),
                '-copy_extensions', 'copy', '-out', target/(name+'.csr'))
        openssl('x509', '-req', '-in', target/(name+'.csr'), '-CA', target/'ca.pem', '-CAkey', original/'ca.key',
                '-set_serial', '0x'+uuid.uuid4().hex, '-days', days, '-copy_extensions', 'copy', '-out', target/(name+'.pem'))
        openssl('verify', '-CAfile', target/'ca.pem', '-purpose', 'sslserver' if name.endswith('server') else 'sslclient', target/(name+'.pem'))
    from Crypto.PublicKey import RSA
    for name in NAMES:
        before, after = metadata(original/(name+'.pem')), metadata(target/(name+'.pem'))
        if any(before[k] != after[k] for k in ('subject', 'issuer', 'subjectAltName')):
            raise ValueError('Renewal changed certificate identity')
        if RSA.import_key((original/(name+'.key')).read_bytes()).public_key() != RSA.import_key((target/(name+'.pem')).read_bytes()):
            raise ValueError('Renewed certificate public key mismatch')
    return {name: (target/(name+'.pem')).read_bytes() for name in NAMES}


# Runs in the original private volume as its existing non-root owner. It never
# prints credentials or private keys; the public report only uses equality flags.
VOLUME = r'''
import base64,hashlib,json,os,re,ssl,sys
from pathlib import Path
from Crypto.PublicKey import RSA
from chainguard_gateway.phase6_server import load
v=json.load(sys.stdin);r,c=load();assert r.resolve().is_relative_to(Path('/sandbox'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def protected():
 return {p.relative_to(r).as_posix():sha(p) for p in r.rglob('*') if p.is_file() and 'mtls-backups' not in p.parts and p.name not in {'ca.pem','server.pem','client.pem','runtime.json','tokens.json'} and not p.name.endswith(('-wal','-shm'))}
def atomic(p,data):
 temp=p.with_name(p.name+'.mtls-new')
 fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 temp.replace(p)
if v['op']=='inspect':
 certs={n:hashlib.sha256(ssl.PEM_cert_to_DER_cert((r/n).read_text())).hexdigest() for n in v['files']}
 print(json.dumps(dict(certs=certs,pins={k:c.get(k) for k in v['pins']},protected=protected())))
else:
 assert re.fullmatch('[a-f0-9]{32}',v['id']);backup=r/'mtls-backups'/v['id']
 if v['op']=='install':
  assert set(v['files'])<={'ca.pem','server.pem','client.pem'}
  assert all(c.get(k)==p for k,p in v['expected_pins'].items())
  assert set(v['pins'])==set(v['expected_pins']) and all(k.endswith('_fingerprint') for k in v['pins'])
  for n,encoded in v['files'].items():
   data=base64.b64decode(encoded,validate=True)
   assert hashlib.sha256(ssl.PEM_cert_to_DER_cert((r/n).read_text())).hexdigest()==v['expected_certs'][n]
   if n!='ca.pem':assert RSA.import_key(data)==RSA.import_key((r/n.replace('.pem','.key')).read_bytes()).public_key()
  backup.mkdir(parents=True,mode=0o700)
  for n in [*v['files'],'runtime.json']:
   fd=os.open(backup/n,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'wb') as f:f.write((r/n).read_bytes())
  for n,encoded in v['files'].items():atomic(r/n,base64.b64decode(encoded,validate=True))
  atomic(r/'runtime.json',json.dumps({**c,**v['pins']},separators=(',',':')).encode())
 elif v['op']=='rollback':
  if backup.exists():
   for p in backup.iterdir():
    assert p.name in {'ca.pem','server.pem','client.pem','runtime.json'};atomic(r/p.name,p.read_bytes())
 else:raise ValueError('Unknown certificate maintenance operation')
 print(json.dumps(dict(protected=protected(),backed_up=backup.exists())))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--ca-days', type=int, default=365)
    a = parser.parse_args(); config = a.config.resolve(); out = a.out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results/maintenance'):
        raise ValueError('Existing private phase10 config and new results/maintenance output required')
    out.mkdir(parents=True); c = json.loads(config.read_text()); tls = config.parent/'tls'
    old = {name: (tls/(name+'.pem')).read_bytes() for name in NAMES}
    report = {'status': 'RUNNING', 'applied': False, 'before': {name: metadata(tls/(name+'.pem')) for name in NAMES},
              'chain_reset': False, 'private_keys_regenerated': False}
    def save(): (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    prefix = ['wsl.exe', '-d', 'Ubuntu', '-u', 'root', '--', 'docker']
    def docker(args, value=None):
        p = subprocess.run(prefix+args, input=json.dumps(value).encode() if value is not None else None, capture_output=True, timeout=90)
        if p.returncode: raise RuntimeError('Docker certificate maintenance failed')
        return p.stdout
    def volume(kind, value):
        mount = 'type=volume,src='+c['containers'][kind]+',dst=/sandbox'
        return json.loads(docker(['run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                                '--security-opt', 'no-new-privileges:true', '--mount', mount, c['image'], 'python', '-c', VOLUME], value))
    def pause_web():
        # Same exact-config match as restart_phase10.ps1; no global Python kills.
        target = str(config).replace("'", "''")
        audit = str(c['audit_config']).replace("'", "''")
        code = "$targets=@('"+target+"','"+audit+"'); foreach($t in $targets){Get-CimInstance Win32_Process | Where-Object {$_.Name -eq 'python.exe' -and $_.CommandLine -like ('*'+$t+'*') -and $_.CommandLine -match 'chainguard_gateway.phase10_(api|audit)'} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force}}"
        subprocess.run(['powershell.exe', '-NoProfile', '-Command', code], capture_output=True, check=True, timeout=30)
    def resume_web():
        with (out/'web-restart.txt').open('wb') as log:
            p = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts/restart_phase10.ps1'),'-Config',str(config)],
                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=45)
        if p.returncode: raise RuntimeError('Local Web readiness failed; see web-restart.txt')
    save()
    try:
        topology=json.loads(docker(['inspect',*c['containers'].values()]))
        for item in topology:
            name=item['Name'].lstrip('/');mounts=item['Mounts']
            if not item['State']['Running'] or not item['HostConfig']['ReadonlyRootfs'] or len(mounts)!=1 or mounts[0]['Type']!='volume' or mounts[0]['Name']!=name or mounts[0]['Destination']!='/sandbox':
                raise ValueError('Original running private-volume topology required')
        observed = {}
        for kind, mapping in MAPPING.items():
            state = volume(kind, {'op':'inspect', 'files':list(mapping), 'pins':list(pins(kind, old))})
            if state['certs'] != {dest:fingerprint(old[name]) for dest,name in mapping.items()} or state['pins'] != pins(kind, old):
                raise ValueError('Private TLS originals and current volume differ; refusing to overwrite')
            observed[kind] = state
        report['volume_identity_matches'] = True
        report['expiring_within_24_hours'] = [n for n,m in report['before'].items() if m['remaining_seconds'] < 86400]
        if not a.apply:
            report['status'] = 'NEEDS_RENEWAL' if report['expiring_within_24_hours'] else 'PASS'; save(); print(json.dumps({'status':report['status'],'expiring_certificates':report['expiring_within_24_hours']})); return
        # Encrypted UI jobs and the authoritative gateway must both be idle.
        sys.path[:0] = [str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
        from chainguard_gateway.phase10_store import OperationsStore
        from chainguard_gateway.phase10_bridge import DockerBridge
        bridge = DockerBridge(c); records = bridge.snapshot()
        jobs = OperationsStore(c['private_root']).jobs()
        if any(j['state'] in {'QUEUED','AGENT_RUNNING'} for j in jobs) or any(r['state'] in {'RESERVING','RESERVED','EXECUTING','EXECUTION_RECORDED'} for r in records):
            raise ValueError('In-flight business work must settle before certificate renewal')
        generation = uuid.uuid4().hex; private = config.parent/'mtls-renewal'/generation
        new = renew_bundle(tls, private/'staged', OpenSSL(), a.days, a.ca_days)
        report['backup_id'] = generation; report['private_backup'] = str(private)
        report['after'] = {n:metadata(private/'staged'/(n+'.pem')) for n in NAMES}
        # Keep host certificate backups, never copy or regenerate private keys.
        (private/'original').mkdir(mode=0o700)
        for n,pem in old.items(): (private/'original'/(n+'.pem')).write_bytes(pem)
        pause_web(); server_names=[c['containers'][k] for k in ('gateway','tool')]
        try:
            docker(['stop',*server_names])
            for kind,mapping in MAPPING.items():
                before = volume(kind, {'op':'inspect','files':list(mapping),'pins':list(pins(kind,old))})
                replacement = renewed_runtime(before['pins'], pins(kind,old), pins(kind,new))
                result = volume(kind, {'op':'install','id':generation,
                    'files':{dest:base64.b64encode(new[name]).decode() for dest,name in mapping.items()},
                    'expected_certs':before['certs'],'expected_pins':pins(kind,old),'pins':replacement})
                if before['protected'] != result['protected']: raise ValueError('Protected data changed during certificate install')
            for n,pem in new.items():
                p=tls/(n+'.pem');temp=p.with_suffix('.renewed.pem');temp.write_bytes(pem);temp.replace(p)
            docker(['start',*server_names])
            # Existing token refresh + full hostname/CA/client verification.
            healthy=False
            for _ in range(20):
                try:
                    bridge.call('requester',{'op':'health'});healthy=True;break
                except Exception:time.sleep(.5)
            if not healthy:raise RuntimeError('Renewed mTLS readiness failed')
            if bridge.snapshot()!=records:raise ValueError('Existing actions changed during transport maintenance')
            report.update(applied=True,protected_data_preserved=True,existing_actions_preserved=len(records))
        except BaseException:
            docker(['stop',*server_names])
            for kind in MAPPING: volume(kind,{'op':'rollback','id':generation})
            for n,pem in old.items(): (tls/(n+'.pem')).write_bytes(pem)
            docker(['start',*server_names]);report['rolled_back']=True;raise
        finally:
            resume_web()
        report['status']='PASS';save();print(json.dumps({'status':'PASS','days':a.days,'ca_days':a.ca_days,'private_keys_regenerated':False}))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise


if __name__ == '__main__': main()
