"""Rolling local observer-history configuration; no signing, chain reset or key changes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from chain import Chain, ROOT, LOCAL, NODES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--nodes',nargs='+',choices=NODES,default=NODES)
    args=parser.parse_args()
    out=args.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/phase10'): raise ValueError('New phase10 output directory required')
    out.mkdir(parents=True)
    chain=Chain(argparse.Namespace(wsl_distro='Ubuntu',wsl_user='root'))
    chain.wsl_session()
    compose=['compose','--project-directory',chain.path(ROOT/'chain'),'--env-file',chain.path(LOCAL/'compose.env'),
             '-f',chain.path(ROOT/'chain/compose.yaml'),'-f',chain.path(ROOT/'chain/compose.audit-history.yaml')]
    report={'status':'RUNNING','checked_at_utc':datetime.now(timezone.utc).isoformat(),'nodes':[],
            'limit':1000000,'retain_future_trie_logs':True,'restores_pruned_history':False}
    def save(): (out/'history-config.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    report['before']=chain.wait_healthy(); save()
    try:
        chain.docker(*compose,'config','--quiet')
        for name in args.nodes:
            original=json.loads(chain.docker('inspect','chainguard-chain-'+name+'-1').stdout)[0]
            report['nodes'].append({'node':name,'before_id':original['Id'],'data_volumes':
                [m['Name'] for m in original['Mounts'] if m['Type']=='volume'],'status':'RESTARTING'})
            save()
            # Exactly one service per invocation. Other three validators remain up.
            result=chain.docker(*compose,'up','-d','--no-deps','--no-build',name,timeout=100)
            (out/(name+'-restart.txt')).write_bytes(result.stdout+result.stderr)
            after=chain.wait_healthy(seconds=120)
            current=json.loads(chain.docker('inspect','chainguard-chain-'+name+'-1').stdout)[0]
            assert [m['Name'] for m in current['Mounts'] if m['Type']=='volume']==report['nodes'][-1]['data_volumes']
            assert current['Image']==original['Image'] and current['Config']['User']==original['Config']['User']
            assert current['HostConfig']['ReadonlyRootfs'] and '--bonsai-limit-trie-logs-enabled=false' in current['Config']['Cmd']
            assert after['nodes'][0]['genesis_hash']==report['before']['nodes'][0]['genesis_hash']
            assert after['nodes'][0]['validators']==report['before']['nodes'][0]['validators']
            report['nodes'][-1].update(status='PASS',after_id=current['Id'],height=after['common_height'])
            save()
        report['after']=chain.wait_healthy()
        report['status']='PASS';save()
        print(json.dumps({'status':'PASS','nodes':[n['node'] for n in report['nodes']],'restores_pruned_history':False}))
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__);save();raise


if __name__=='__main__':main()
