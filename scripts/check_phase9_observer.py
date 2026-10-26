"""Actual-chain negative verification and actual audit-container network outage."""
import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import urllib.error

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
from chainguard_gateway.audit_console import load_catalog
from chainguard_gateway.audit_verify import make_chain,verify_action


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((args.deployment/'deployment.json').read_text())
    catalog=load_catalog(args.deployment/'public/catalog.json')
    chain=make_chain(catalog['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    action=next(a for a in catalog['actions'] if a['group']=='C' and a['state']=='FINALIZED_OK')
    checks={}
    require=lambda condition: (_ for _ in ()).throw(AssertionError('Actual audit expectation failed')) if not condition else None
    require(verify_action(chain,action)['status']=='VERIFIED')
    for kind in ['intent','approval','receipt','block','action']:
        bad=copy.deepcopy(action)
        if kind=='intent':bad['intent']['params_commit']='0x'+'11'*32
        elif kind=='approval':bad['approval_signatures'][0]='0x'+'22'*65
        elif kind=='receipt':bad['receipt']['result_commit']='0x'+'33'*32
        elif kind=='block':bad['reservation_evidence']['block_number']='1'
        else:bad['action_id']='0x'+'44'*32
        result=verify_action(chain,bad)
        require(result['status']=='INVALID');checks[kind]=result['status']
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
    container=manifest['container_id']
    require(bool(re.fullmatch('[0-9a-f]{64}',container)))
    info=json.loads(subprocess.run(prefix+['inspect',container],capture_output=True,check=True).stdout)[0]
    require(info['Name'].startswith('/chainguard-audit-') and info['Config']['User']=='10001:10001')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path):
        try:
            with opener.open(manifest['url']+path,timeout=60) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    try:
        subprocess.run(prefix+['network','disconnect','chainguard_qbft',container],capture_output=True,check=True)
        # Port mapping remains loopback, so removing the only interface can make HTTP
        # itself unreachable. Exec checks the same actual FastAPI process over loopback.
        code="import urllib.request,urllib.error,json; p='/audit-api/v1/actions/"+action['entry_id']+"/verify'; r=urllib.request.urlopen('http://127.0.0.1:8080'+p,timeout=60); print(r.read().decode())"
        raw=subprocess.run(prefix+['exec',container,'python','-c',code],capture_output=True,check=True,timeout=90).stdout
        outage=json.loads(raw)
        require(outage['status']=='UNAVAILABLE' and outage['tool_signature_valid'] is None)
    finally:
        subprocess.run(prefix+['network','connect','chainguard_qbft',container],capture_output=True,check=True)
    restored=verify_action(chain,action);require(restored['status']=='VERIFIED')
    result=dict(status='PASS',negative_checks=checks,actual_network_disconnected=True,outage=outage,
        restored=restored,transaction_or_tool_writes=False)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Actual-chain tamper detection and actual isolated observer outage PASS')


if __name__=='__main__':main()
