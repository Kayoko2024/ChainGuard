"""Read-only repeated live policy verification in a 512MiB isolated container.

Only public RPC reads are made; the original gateway volume is mounted readonly.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']]
from chainguard_gateway.phase10_bridge import DockerBridge

PROBE='''import sys,json,resource,tracemalloc,gc
from chainguard_gateway.phase6_server import load
from chainguard_gateway.conversation_grants import ConversationPolicy
v=json.load(sys.stdin);root,c=load();p=json.loads((root/'tool-sessions.json').read_text());tracemalloc.start();samples=[]
for i in range(v['iterations']+1):
 policy=ConversationPolicy(p,c['rpc_urls']);snap=policy.snapshot()
 if i%50==0 or i==v['iterations']:
  current,peak=tracemalloc.get_traced_memory();row=dict(iteration=i,rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,traced_bytes=current,peak=peak,gc_count=gc.get_count(),block_number=snap['number']);samples.append(row);print(json.dumps(row),flush=True)
 del policy
growth=samples[-1]['rss_kib']-samples[0]['rss_kib']
print(json.dumps(dict(final=True,status='PASS' if growth<65536 else 'FAIL',rss_growth_kib=growth,read_only=True,transactions_submitted=0,model_calls=0)),flush=True)
sys.exit(0 if growth<65536 else 1)
'''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--iterations',type=int,default=400);a=p.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/maintenance') or not 50<=a.iterations<=1000:raise ValueError('New maintenance output and 50..1000 iterations required')
    out.mkdir(parents=True);c=json.loads(a.config.read_text(encoding='utf8'));b=DockerBridge(c)
    args=b.prefix+['run','--rm','-i','--network','chainguard_qbft','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','512m','--pids-limit','64','--mount','type=volume,src='+c['containers']['gateway']+',dst=/sandbox,readonly',c['image'],'python','-c',PROBE]
    with (out/'samples.jsonl').open('wb') as stdout,(out/'stderr.bin').open('wb') as stderr:
        result=subprocess.run(args,input=json.dumps(dict(iterations=a.iterations)).encode(),stdout=stdout,stderr=stderr,timeout=240)
    rows=[json.loads(l) for l in (out/'samples.jsonl').read_text().splitlines()]
    report=dict(status='PASS' if result.returncode==0 else 'FAIL',image=c['image'],iterations=a.iterations,read_only=True,transactions_submitted=0,model_calls=0,samples=rows)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],iterations=a.iterations)))
    if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':main()
