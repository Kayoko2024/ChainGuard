"""Independent acceptance tooling only. Does not change application behavior or old evidence."""
import argparse
import base64
import csv
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
PYTHON=str(ROOT/'.venv/Scripts/python.exe')
DOCKER=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
PROTOCOL=ROOT/'results/phase8/phase9/b5b09af5ea'
MODEL=ROOT/'results/phase8/complete-experiment-01/real-abc'


def load(path):return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def utc():return datetime.now(timezone.utc).isoformat()


class Acceptance:
    def __init__(self,out):
        self.out=out.resolve()
        if not self.out.is_relative_to(ROOT/'results/final_acceptance'):raise ValueError('Acceptance output required')
        self.out.mkdir(parents=True,exist_ok=True)

    def command(self,name,args,cwd=ROOT,timeout=300,data=None):
        logfile=self.out/(name+'.log')
        if logfile.exists():raise ValueError('Never overwrite a command log: '+name)
        started=utc();before=time.monotonic()
        try:
            result=subprocess.run(args,cwd=cwd,input=data,capture_output=True,timeout=timeout)
            stdout=result.stdout;output=stdout+result.stderr;code=result.returncode
        except subprocess.TimeoutExpired as error:
            stdout=error.stdout or b'';output=stdout+(error.stderr or b'');code=124
        logfile.write_bytes(output)
        row=dict(name=name,command=[str(a) for a in args],cwd=str(Path(cwd).relative_to(ROOT)),
                 started_at_utc=started,finished_at_utc=utc(),exit_code=code,
                 elapsed_seconds=round(time.monotonic()-before,3),log=logfile.name,stdin_saved=False)
        with (self.out/'commands.jsonl').open('a',encoding='utf8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        print(name+': exit='+str(code),flush=True)
        return code,stdout

    def baseline(self):
        results={}
        commands=[('pytest',[PYTHON,'-m','pytest','-q','--junitxml='+str(self.out/'pytest.xml')],ROOT),
            ('hardhat',['npm.cmd','test'],ROOT),('frontend',['npm.cmd','test'],ROOT/'dashboard'),
            ('spec-check',[PYTHON,'scripts/build_specs.py','--check'],ROOT),
            ('policy-check',[PYTHON,'scripts/freeze_phase3_policy.py','--check'],ROOT),
            ('pip-check',[PYTHON,'-m','pip','check'],ROOT),
            ('source-integrity',[PYTHON,'scripts/check_phase9_integrity.py','--out',str(self.out/'source-integrity.json')],ROOT)]
        for name,args,cwd in commands:results[name]=self.command(name,args,cwd)[0]
        dump(self.out/'baseline.json',dict(status='PASS' if not any(results.values()) else 'FAIL',exits=results))

    def environment(self):
        results={}
        for name,args in [
            ('git-start-status',['git','status','--short']),('git-start-head',['git','rev-parse','--verify','HEAD']),
            ('git-start-diff',['git','diff','--stat']),('git-start-cached',['git','diff','--cached','--stat']),
            ('python-version',[PYTHON,'--version']),('node-version',['node','--version']),('npm-version',['npm.cmd','--version']),
            ('docker-version',DOCKER+['version','--format','{{json .}}']),('compose-version',DOCKER+['compose','version']),
            ('network-health',[PYTHON,'scripts/chain.py','health','--wsl-distro','Ubuntu'])]:
            results[name]=self.command(name,args,timeout=180)[0]
        original=load(ROOT/'results/phase9/source-manifest.json')['files']
        frozen={}
        for name in ['phase0-freeze.json','phase3-policy-freeze.json']:frozen.update(load(ROOT/'config'/name)['files'])
        snapshot={name:sha(ROOT/name) for name in sorted(set(original)|set(frozen))}
        dump(self.out/'starting-source-snapshot.json',snapshot)
        drift=[name for name,expected in {**original,**frozen}.items() if snapshot[name]!=expected]
        # Values remain exclusively in memory; neither secrets nor their hashes are saved.
        def local_value(path):
            return next((line.partition('=')[2].strip().strip('\"\'') for line in path.read_text(encoding='utf8').splitlines() if line.startswith('CHAINGUARD_LLM_API_KEY=')),'') if path.exists() else ''
        key=local_value(ROOT/'.env.local')
        ignored=subprocess.run(['git','check-ignore','-q','.env.local'],cwd=ROOT).returncode==0
        candidates=[]
        for folder in ['gateway','agent','sandbox_tools','evaluation','scripts','spec','docs','config','dashboard']:
            candidates.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and not any(v in p.parts for v in ['node_modules','__pycache__','dist']) and p.suffix in {'.py','.md','.json','.jsx','.mjs','.cjs','.yaml','.txt'})
        hits=[p.relative_to(ROOT).as_posix() for p in candidates if key and key.encode() in p.read_bytes()]
        dump(self.out/'environment.json',dict(checked_at_utc=utc(),command_exits=results,source_drift=drift,
            local_key_present=bool(key),local_key_ignored=ignored,template_empty=not local_value(ROOT/'.env.local.example'),
            current_key_scan_hits=hits,root_package_version=load(ROOT/'package.json')['version'],
            dashboard_version=load(ROOT/'dashboard/package.json')['version'],project_license_present=(ROOT/'LICENSE').exists(),
            note='No API call; no secret values or secret digests saved. Missing HEAD is an observed initial failure.'))

    def history(self):
        from chainguard_gateway.audit_console import load_catalog
        from chainguard_gateway.audit_verify import make_chain,verify_action
        from chainguard_gateway.chain_crypto import digest,recover_receipt
        from chainguard_gateway.crypto import recover_intent
        from chainguard_sandbox.protocol import ToolError
        from verify_phase8 import VOLUME_CODE
        catalog=load_catalog(ROOT/'results/phase9/deploy-final/public/catalog.json')
        chain=make_chain(catalog['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
        snapshot=chain.healthy();details={};all_receipts={}
        for entry in ['protocol-0000','protocol-0043','protocol-0006']:
            action=next(a for a in catalog['actions'] if a['entry_id']==entry)
            result=verify_action(chain,action)
            detail=dict(action=action,observer=result,raw_receipts={},current_chain=None)
            if action['intent']:
                reservation=chain.execution.call('getReservation',[action['action_id']])
                detail['current_chain']=reservation
                detail['nonce_consumed']=chain.execution.call('usedNonce',[action['intent']['requester'],action['intent']['nonce']])
            for kind in ['reservation_evidence','finalization_evidence']:
                evidence=action[kind]
                if not evidence:continue
                receipts=[n.call('eth_getTransactionReceipt',[evidence['tx_hash']]) for n in chain.nodes]
                assert all(r==receipts[0] and r['status']=='0x1' for r in receipts)
                for n,r in zip(chain.nodes,receipts):
                    b=n.call('eth_getBlockByNumber',[r['blockNumber'],False])
                    assert b['hash']==r['blockHash'] and evidence['tx_hash'] in b['transactions']
                detail['raw_receipts'][kind]=receipts
                tx=chain.rpc.call('eth_getTransactionByHash',[evidence['tx_hash']])
                detail[kind+'_transaction']=tx
            if action['receipt']:
                detail['tool_signer_recovered']=recover_receipt(action['receipt'],chain.receipt_domain,action['tool_signature'])
                detail['receipt_commit_matches_chain']=chain.audit.call('receiptHash',[action['action_id']])==digest('ExecutionReceipt',action['receipt'],chain.receipt_domain)
                assert detail['receipt_commit_matches_chain']
            if action['intent'] and action['requester_signature']:
                detail['requester_valid']=recover_intent(action['intent'],chain.domain,action['requester_signature'])==action['intent']['requester']
                detail['approvers_recovered']=[recover_intent(action['intent'],chain.domain,s) for s in action['approval_signatures']]
            if entry=='protocol-0006':
                assert action['receipt'] is None and action['tool_signature'] is None
                assert action['state']=='UNKNOWN' and detail['current_chain']['status']==1
                detail['unknown_preserved']=True;detail['new_execute_requested']=False
            if entry=='protocol-0043':
                assert not action['reservation_evidence'] and not action['observed_tool_executed'] and action['observed_mail_count']==0
                detail['limited_claim']='No action allocated by rejected propose; check entire run reservation set and original tool store below.'
            details[entry]=detail
        dump(self.out/'named-actions.json',dict(snapshot=snapshot,actions=details))
        # All original protocol receipts, independent from any UI; no historical eth_call required.
        for directory,name in [(PROTOCOL,'protocol'),(MODEL,'model')]:
            manifest=load(directory/'run_manifest.json')
            originals=load(directory/'tx-receipts.json');receipts={}
            for tx_hash,expected in originals.items():
                current=[n.call('eth_getTransactionReceipt',[tx_hash]) for n in chain.nodes]
                assert current==expected
                for n,r in zip(chain.nodes,current):
                    b=n.call('eth_getBlockByNumber',[r['blockNumber'],False])
                    assert r['blockHash']==b['hash'] and tx_hash in b['transactions']
                receipts[tx_hash]=current
            dump(self.out/(name+'-live-receipts.json'),receipts)
            expected=[]
            for file in sorted(directory.glob('case-*.json' if name=='protocol' else 'live-case-*.json')):
                raw=load(file)
                e=raw if name=='protocol' else raw['evidence']
                row=e['case'] if name=='protocol' else raw['row']
                record=e['record'] if name=='protocol' else (e['action_evidence'][0]['record'] if e['action_evidence'] else None)
                params=e['semantic_input']['params'] if name=='protocol' else (e['action_evidence'][0]['params'] if e['action_evidence'] else None)
                expected.append(dict(tool_root=e['tool_root'],group=row['group'],sample_id=row['sample_id'],
                    action_id=record['action_id'] if record else None,params=params,
                    mailbox=[{k:v for k,v in m.items() if k!='mime_b64'} for m in e['mailbox']]))
            info=json.loads(subprocess.run(DOCKER+['inspect',manifest['container_name']],capture_output=True,check=True).stdout)[0]
            assert info['Id']==manifest['isolation']['id'] and info['Image']==manifest['image']
            assert len(info['Mounts'])==1 and info['Mounts'][0]['Name']==manifest['volume']
            code=VOLUME_CODE if name=='protocol' else VOLUME_CODE.replace("WHERE state='COMPLETED'", "WHERE state='COMPLETED' AND tool_name='mail.send'")
            ec,raw=self.command(name+'-original-volume',DOCKER+['run','--rm','-i','--network','none','--read-only','--cap-drop','ALL',
                '--security-opt','no-new-privileges:true','--mount','type=volume,src='+manifest['volume']+',dst=/sandbox,readonly',
                manifest['image'],'python','-c',code],data=json.dumps(expected).encode(),timeout=120)
            assert ec==0
            dump(self.out/(name+'-physical-verification.json'),dict(status='PASS',receipts=len(receipts),four_node_receipts=4*len(receipts),volume=json.loads(raw)))
        # Run the existing complete verifier ONLY against fresh copies to preserve every original artifact.
        from verify_phase8 import verify as vp
        from verify_live_agent import verify as vm
        for source,name,verify in [(PROTOCOL,'protocol',vp),(MODEL,'model',vm)]:
            destination=self.out/(name+'-readonly-copy');shutil.copytree(source,destination)
            try:result=verify(destination)
            except Exception as error:
                result=dict(status='UNAVAILABLE' if isinstance(error,ToolError) and error.code=='CHAIN_UNAVAILABLE' else 'FAIL',error_type=type(error).__name__,error=str(error),original_unchanged=True)
            dump(self.out/(name+'-full-reverification.json'),result)
        print('History: live receipts and original read-only volumes checked; observer/full status saved without fallback',flush=True)

    def statistics(self):
        from evaluation.metrics import aggregate
        from evaluation.live_results import observations,judged_rows,live_metrics
        from verify_phase8 import verify_rows,verify_csv
        results={}
        for directory,name in [(PROTOCOL,'protocol'),(MODEL,'model')]:
            manifest=load(directory/'run_manifest.json')
            rows=[json.loads(line) for line in (directory/'traces.jsonl').read_text(encoding='utf8').splitlines()]
            if name=='protocol':
                verify_rows(manifest['plan'],rows)
                assert all(r['attack_success'] is None and r['llm_sample_count']==0 for r in rows)
                metrics=aggregate(rows,manifest['plan']['bootstrap_replicates'])
            else:
                cases=[load(p) for p in sorted(directory.glob('live-case-*.json'))]
                for case in cases:
                    observed=observations(case['events'],case['model_exchanges'],case['evidence'],manifest['plan']['authorized_mail'])
                    assert all(case['row'][k]==v for k,v in observed.items() if k in case['row'])
                    for exchange in case['model_exchanges']:
                        request=exchange['request']
                        assert request['model']==manifest['plan']['model'] and all(request[k]==v for k,v in manifest['plan']['parameters'].items())
                assert judged_rows(cases,load(directory/'official-judgements.json'))==rows
                metrics=live_metrics(rows,manifest['plan']['bootstrap_replicates'])
                copied=self.out/'model-judge-copy';copied.mkdir()
                for path in directory.glob('live-case-*.json'):shutil.copyfile(path,copied/path.name)
                ec,_=self.command('official-judges',[str(ROOT/'.local/phase7-agentdojo-venv/Scripts/python.exe'),'evaluation/judge_real_effects.py',str(copied)],timeout=120)
                assert ec==0 and load(copied/'official-judgements.json')==load(directory/'official-judgements.json')
            verify_csv(directory/'cases.csv',rows)
            verify_csv(directory/'aggregated_metrics.csv',metrics)
            dump(self.out/(name+'-recomputed-metrics.json'),metrics)
            # Independently recount numerator/denominator and Wilson bounds using a separate formula.
            independent=[]
            for group in ['A','B','C']:
                selected=[r for r in rows if r['group']==group]
                counters={'UER':('unauthorized_executions','unauthorized_attempts'),'UBR':('unauthorized_blocked','unauthorized_attempts'),
                    'ASR':('attack_success_count','attack_evaluable'),'TCR':('task_completed','task_eligible'),'TDR':('tamper_detected','tamper_attempts')}
                for label,(numerator,denominator) in counters.items():
                    k=sum(r.get(numerator,0) for r in selected);n=sum(r.get(denominator,0) for r in selected)
                    actual=next(m for m in metrics if m['group']==group and m['metric']==label and m.get('cohort')=='all_applicable')
                    assert (actual['k'],actual['n'])==(k,n)
                    bounds=None
                    if n:
                        z=1.959963984540054;den=2*(n+z*z)
                        center=(2*k+z*z)/den;delta=z*math.sqrt(z*z+4*k*(1-k/n))/den
                        bounds=[max(0,center-delta),min(1,center+delta)]
                        assert abs(bounds[0]-actual['ci95_low'])<1e-12 and abs(bounds[1]-actual['ci95_high'])<1e-12
                    independent.append(dict(group=group,metric=label,k=k,n=n,wilson95=bounds))
            dump(self.out/(name+'-independent-counts.json'),independent)
            results[name]=dict(status='PASS',rows=len(rows),metrics=len(metrics),raw_counts_and_wilson_independent=True,bootstrap_reexecuted=True,
                csv_matches=True,official_judges_rerun=name=='model',real_model_rerun=False)
        results['trace_in_real_asr']=False
        dump(self.out/'statistics.json',results)

    def sandbox(self):
        from run_phase2_container import context_archive,restricted_run
        archive,_=context_archive()
        ec,_=self.command('sandbox-build',DOCKER+['build','--network','none','-f','sandbox_tools/Dockerfile','-t','chainguard/sandbox-tools:0.2.0','-'],data=archive)
        assert ec==0
        checks={}
        for suite in ['resources','tools']:
            # Existing runner enforces non-root, network none, read-only root, and tmpfs-only test files.
            started=utc();before=time.monotonic()
            result=restricted_run(DOCKER,['python','-m','unittest','discover','-s','sandbox_tools/tests','-p','test_'+suite+'.py','-v'])
            (self.out/('sandbox-'+suite+'.log')).write_bytes(result.stdout+result.stderr)
            checks[suite]=dict(exit_code=result.returncode,started_at_utc=started,elapsed_seconds=time.monotonic()-before,
                network='none',host_mounts=[],read_only=True,user='10001:10001',command=['python','-m','unittest','discover','-s','sandbox_tools/tests','-p','test_'+suite+'.py','-v'])
            assert result.returncode==0
        dump(self.out/'sandbox.json',dict(status='PASS',checks=checks,note='Real concurrent mail/delete test side effects only in isolated tmpfs; not C on-chain concurrency evidence'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--step',choices=['baseline','environment','history','statistics','sandbox','command'],required=True)
    parser.add_argument('--name')
    parser.add_argument('--cwd',type=Path,default=ROOT)
    parser.add_argument('--timeout',type=int,default=1800)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();audit=Acceptance(args.out)
    try:
        if args.step=='command':
            command=args.command[1:] if args.command[:1]==['--'] else args.command
            raise SystemExit(audit.command(args.name,command,args.cwd,args.timeout)[0])
        getattr(audit,args.step)()
    except Exception as error:
        dump(audit.out/(args.step+'-error.json'),dict(status='FAIL',error_type=type(error).__name__,error=str(error)))
        traceback.print_exc();raise SystemExit(1)
