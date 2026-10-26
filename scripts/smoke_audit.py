"""Actual HTTP smoke; UI state alone never establishes ledger execution."""
import argparse
import json
from pathlib import Path
import urllib.request
import urllib.error


def smoke(url):
    if not url.startswith('http://127.0.0.1:'):
        raise ValueError('Only localhost audit smoke allowed')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def call(path,method='GET'):
        request=urllib.request.Request(url+path,method=method)
        with opener.open(request,timeout=60) as response:
            raw=response.read()
            return json.loads(raw) if response.headers.get_content_type()=='application/json' else raw.decode()
    assert call('/health/live')['read_only']
    assert call('/health/ready')['ledger_checked'] is False
    assert '<div id="root">' in call('/')
    network=call('/audit-api/v1/network');assert network['status']=='ONLINE' and network['nodes']==4
    listing=call('/audit-api/v1/actions');actions=listing['actions']
    normal=next(a for a in actions if a['group']=='C' and a['state']=='FINALIZED_OK')
    evidence=call('/audit-api/v1/actions/'+normal['entry_id']+'/verify')
    assert evidence['status']=='VERIFIED' and evidence['tool_signature_valid'] is True
    assert len({a['organization'] for a in evidence['approvals']})>=2
    assert len(evidence['transactions'])==2 and all(t['node_receipts']==4 for t in evidence['transactions'])
    unknown=next(a for a in actions if a['group']=='C' and a['state']=='UNKNOWN')
    unknown_check=call('/audit-api/v1/actions/'+unknown['entry_id']+'/verify')
    assert unknown_check['status']=='PENDING_RECEIPT'
    central=next(a for a in actions if a['group']=='B')
    assert call('/audit-api/v1/actions/'+central['entry_id']+'/verify')['status']=='HISTORICAL_ONLY'
    denied=next(a for a in actions if a['group']=='C' and not a['reservation_evidence'])
    assert call('/audit-api/v1/actions/'+denied['entry_id']+'/verify')['status']=='NO_RESERVATION'
    for path in ['/v1/agent/actions/propose','/v1/actions/reserve','/internal/v1/tools/execute']:
        try:call(path,'POST');raise AssertionError('Unexpected write endpoint')
        except urllib.error.HTTPError as e:assert e.code in [404,405]
    text=json.dumps(listing)
    for forbidden in ['mime_b64','params_salt','tool_root','relay_key','api_key','signing_keys']:
        assert forbidden not in text
    return dict(status='PASS',entries=len(actions),network=network,normal=evidence,unknown=unknown_check,
                denied_entry=denied['entry_id'],write_routes_absent=True,sensitive_plaintext_absent=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8080')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    result=smoke(args.url)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':'PASS','entries':result['entries'],'live_verified':result['normal']['status']}))
