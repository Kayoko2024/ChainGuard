"""Inspect or roll development QBFT resource limits without resetting the chain."""
import argparse
import json
from pathlib import Path
import time
from chain import Chain,ROOT,LOCAL,NODES


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--apply',action='store_true',help='Recreate exactly one validator at a time using the existing volumes')
    a=p.parse_args();out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/maintenance'):raise ValueError('New maintenance result directory required')
    out.mkdir(parents=True)
    chain=Chain(argparse.Namespace(wsl_distro='Ubuntu',wsl_user='root'))
    report=dict(status='RUNNING',apply=a.apply,nodes=[],genesis_modified=False)
    def save():(out/'resources.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    def inspect(name):
        raw=json.loads(chain.docker('inspect','chainguard-chain-'+name+'-1').stdout)[0]
        return dict(id=raw['Id'],image=raw['Image'],volumes=sorted(m['Name'] for m in raw['Mounts'] if m['Type']=='volume'),
            memory_bytes=raw['HostConfig']['Memory'],java_opts=next((e.split('=',1)[1] for e in raw['Config']['Env'] if e.startswith('JAVA_OPTS=')),None),
            restart=raw['HostConfig']['RestartPolicy']['Name'],readonly=raw['HostConfig']['ReadonlyRootfs'],
            running=raw['State']['Running'],oom_killed=raw['State']['OOMKilled'])
    try:
        report['before']=chain.wait_healthy();save()
        genesis=json.loads((LOCAL/'network/genesis.json').read_text(encoding='utf8'))
        report['block_period_seconds']=genesis['config']['qbft']['blockperiodseconds']
        chain.compose('config','--quiet')
        for name in NODES:
            entry=dict(name=name,before=inspect(name));report['nodes'].append(entry);save()
            if a.apply:
                result=chain.compose('up','-d','--no-deps','--no-build',name,timeout=100)
                (out/(name+'-restart.txt')).write_bytes(result.stdout+result.stderr)
            health=chain.wait_healthy(seconds=120);current=entry['after']=inspect(name)
            assert current['volumes']==entry['before']['volumes'] and current['image']==entry['before']['image']
            assert current['running'] and not current['oom_killed'] and current['readonly']
            if a.apply:
                assert current['memory_bytes']==1024**3 and '-Xmx512m' in current['java_opts'] and current['restart']=='unless-stopped'
            assert health['nodes'][0]['genesis_hash']==report['before']['nodes'][0]['genesis_hash']
            assert health['nodes'][0]['validators']==report['before']['nodes'][0]['validators']
            entry.update(status='PASS',height=health['common_height']);save()
        report['after']=chain.wait_healthy()
        time.sleep(5)
        report['after_wait']=chain.wait_healthy()
        assert report['after_wait']['common_height']>report['after']['common_height']
        result=chain.docker('stats','--no-stream','--format','{{json .}}',*['chainguard-chain-'+n+'-1' for n in NODES])
        report['stats']=[json.loads(line) for line in result.stdout.decode('utf8').splitlines() if line.strip()]
        report['status']='PASS';save()
        print(json.dumps(dict(status='PASS',nodes=len(NODES),block_period_seconds=report['block_period_seconds'],apply=a.apply)))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise


if __name__=='__main__':main()
