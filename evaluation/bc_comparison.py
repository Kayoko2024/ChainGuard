"""Paired B/C analysis of existing protocol evidence; never executes a business task.

Historical observations are not new experiments or evidence of intrinsic superiority.
Optional localhost RPC checks only reverify the existing recovery transactions.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from .metrics import quantile, wilson, write_csv

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pair_rows(rows):
    """Keep noncomparable controls visible; reject missing or mismatched pairs."""
    groups = {'B': {}, 'C': {}}
    for row in rows:
        if row['group'] not in groups:
            continue
        group = groups[row['group']]
        if row['sample_id'] in group:
            raise ValueError('Duplicate B/C sample')
        group[row['sample_id']] = row
    if not groups['B'] or groups['B'].keys() != groups['C'].keys():
        raise ValueError('Incomplete B/C pairing')
    pairs = []
    for key in sorted(groups['B']):
        b, c = groups['B'][key], groups['C'][key]
        if any(b[k] != c[k] for k in ('input_sha256', 'scenario', 'trial')):
            raise ValueError('Paired task, parameters or scenario mismatch')
        comparable = bool(b['mechanism_applicable'] and c['mechanism_applicable'])
        pairs.append(dict(sample_id=key, scenario=b['scenario'], input_sha256=b['input_sha256'],
            comparison_status='SHARED_INTERVENTION' if comparable else 'MECHANISM_NOT_SHARED',
            B_state=b['final_state'], C_state=c['final_state'],
            B_mail_count=b['mailbox_count'], C_mail_count=c['mailbox_count'],
            B_task_completed=b['task_completed'], C_task_completed=c['task_completed'],
            B_effect_unknown=b.get('task_unknown',0), C_effect_unknown=c.get('task_unknown',0),
            B_acknowledged=int(b['final_state']=='CENTRAL_OK' and b['task_completed']==1),
            C_acknowledged=int(c['final_state']=='FINALIZED_OK' and c['task_completed']==1),
            B_elapsed_ms=b['elapsed_ms'], C_elapsed_ms=c['elapsed_ms'],
            B_observed_states=b['observed_states'], C_observed_states=c['observed_states']))
    return pairs


def comparison_metrics(rows, pairs):
    metrics = []
    for scenario in sorted({p['scenario'] for p in pairs}):
        selected = [p for p in pairs if p['scenario']==scenario]
        for group in ('B', 'C'):
            for metric, field in [('effect_completed', 'task_completed'), ('acknowledged_success', 'acknowledged')]:
                k = sum(p[f'{group}_{field}'] for p in selected)
                unknown = sum(p[f'{group}_effect_unknown'] for p in selected) if field=='task_completed' else 0
                if k<0 or unknown<0 or k+unknown>len(selected):
                    raise ValueError('Inconsistent effect/unknown counts')
                estimate, lo, hi = wilson(k, len(selected))
                metrics.append(dict(group=group, scenario=scenario, metric=metric, k=k, n=len(selected),
                    unknown=unknown, estimate=estimate if not unknown else None,
                    observed_lower_bound=k/len(selected), possible_upper_bound=(k+unknown)/len(selected),
                    ci95_low=lo if not unknown else None, ci95_high=hi if not unknown else None,
                    comparison_status=selected[0]['comparison_status'] if len({p['comparison_status'] for p in selected})==1 else 'MIXED_INTERVENTIONS_NOT_COMPARABLE',
                    interpretation='historical implementation observation; descriptive Wilson95, repeated trials are not independent tasks'))
    for group in ('B', 'C'):
        performance = [r for r in rows if r['group']==group and r['performance_eligible']]
        valid = [r['elapsed_ms'] for r in performance if r['task_completed'] and r['status']=='PASS']
        for name, p in [('P50',.5), ('P95',.95), ('P99',.99)]:
            metrics.append(dict(group=group, scenario='performance', metric='elapsed_ms_'+name,
                n=len(valid), estimate=quantile(valid,p), comparison_status='SHARED_INTERVENTION',
                interpretation='small fixed-workload sample; includes automatic test approval, excludes model/HTTP/mTLS; P99 exploratory'))
        metrics.append(dict(group=group, scenario='performance', metric='failure_count',
            k=len(performance)-len(valid), n=len(performance), comparison_status='SHARED_INTERVENTION'))
    return metrics


def load_source(source):
    from scripts.verify_phase8 import verify_rows
    from chainguard_gateway.audit import verify_log
    from chainguard_gateway.chain_crypto import recover_receipt
    manifest = json.loads((source/'run_manifest.json').read_text(encoding='utf8'))
    if manifest['status']!='PASS' or manifest['track']!='protocol_replay':
        raise ValueError('A completed protocol run is required; do not mix LLM samples')
    hashes = {'run_manifest.json': sha(source/'run_manifest.json')}
    for name, expected in manifest['artifacts'].items():
        path = source/name
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError('Unsafe artifact path')
        if sha(path)!=expected:
            raise ValueError('Original artifact digest mismatch: '+name)
        hashes[name] = expected
    rows = [json.loads(line) for line in (source/'traces.jsonl').read_text(encoding='utf8').splitlines() if line]
    verify_rows(manifest['plan'],rows)
    deployment = manifest['deployment']
    domain = dict(name='ChainGuard AuditRegistry', version='1', chainId=str(deployment['chainId']),
        verifyingContract=deployment['contracts']['AuditRegistry']['address'].lower())
    cases = {}
    for row in rows:
        if row['group'] not in {'B','C'}:
            continue
        if row['evidence_file'] not in hashes:
            raise ValueError('Unindexed case evidence')
        evidence = json.loads((source/row['evidence_file']).read_text(encoding='utf8'))
        if evidence['group']!=row['group'] or any(row.get(k)!=v for k,v in evidence['case'].items()):
            raise ValueError('Case/trace mismatch')
        if len(evidence['mailbox'])!=row['mailbox_count']:
            raise ValueError('MIME count mismatch')
        for mail in evidence['mailbox']:
            raw = base64.b64decode(mail['mime_b64'],validate=True)
            if hashlib.sha256(raw).hexdigest()!=mail['mime_sha256']:
                raise ValueError('MIME digest mismatch')
        record = evidence['record']
        if record and record['central_state' if row['group']=='B' else 'state']!=row['final_state']:
            raise ValueError('Raw record/trace state mismatch')
        if row['group']=='B':
            audit = evidence['audit']
            if verify_log(audit['entries'],audit['signer'],checkpoint=audit['checkpoint'],deployment_id=audit['deployment_id'])['status']!='VALID':
                raise ValueError('B signature chain or independent checkpoint invalid')
        elif record and record['state']=='FINALIZED_OK':
            if recover_receipt(record['receipt'],domain,evidence['tool_signature'])!=manifest['public_signers']['mailTool']:
                raise ValueError('C original tool signature invalid')
            if not record['reservation_evidence'] or not record['finalization_evidence']:
                raise ValueError('C terminal record lacks transaction evidence')
        cases[row['group'],row['sample_id']] = evidence
    return manifest, rows, cases, hashes


def live_recovery_check(manifest, rows, cases):
    from scripts.verify_phase8 import ReadOnlyRPC
    from chainguard_gateway.chain_rpc import Chain
    from chainguard_gateway.chain_crypto import digest
    chain = Chain(manifest['deployment'],[f'http://127.0.0.1:{p}' for p in range(8545,8549)])
    chain.nodes = [ReadOnlyRPC(n.url) for n in chain.nodes]
    chain.rpc = chain.nodes[0]
    chain.policy.rpc = chain.execution.rpc = chain.audit.rpc = chain.rpc
    snapshot = chain.healthy()
    transactions = []
    for row in rows:
        if row['group']!='C' or row['scenario']!='fault-after-tool':
            continue
        record = cases['C',row['sample_id']]['record']
        intent = record['intent']
        reservation = chain.execution.call('getReservation',[record['action_id']])
        if reservation['status']!=3 or reservation['intentHash']!=digest('ActionIntent',intent,chain.domain):
            raise ValueError('Current recovery reservation mismatch')
        if not chain.execution.call('usedNonce',[intent['requester'],intent['nonce']]):
            raise ValueError('Original nonce no longer consumed')
        if chain.audit.call('receiptHash',[record['action_id']])!=digest('ExecutionReceipt',record['receipt'],chain.receipt_domain):
            raise ValueError('Current tool receipt hash mismatch')
        for field, registry, event in [('reservation_evidence',chain.execution.address,'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)'),
                                       ('finalization_evidence',chain.audit.address,'ActionFinalized(bytes32,bytes32,address,uint8)')]:
            evidence = record[field]
            actual, receipt, _ = chain.transaction_evidence(evidence['tx_hash'],registry,snapshot,event,record['action_id'])
            if actual!=evidence:
                raise ValueError('Original transaction mismatch')
            transactions.append(dict(sample_id=row['sample_id'],kind=field,tx_hash=evidence['tx_hash'],
                node_receipts=4,receipt=receipt))
    if not transactions:
        raise ValueError('No recovery transactions to reverify')
    return dict(status='PASS',snapshot=snapshot,transactions=transactions,node_receipts=len(transactions)*4,
        tool_volume_rechecked=False,scope='current four-node chain check; original MIME/signatures checked offline, no new executions')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--live-chain',action='store_true')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.out.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Use a new output directory outside original evidence')
    sys.path[:0] = [str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src')]
    manifest,rows,cases,hashes = load_source(source)
    pairs = pair_rows(rows)
    metrics = comparison_metrics(rows,pairs)
    output.mkdir(parents=True,exist_ok=False)
    report = dict(status='RUNNING',track='bc_historical_paired_analysis',created_at_utc=datetime.now(timezone.utc).isoformat(),
        source=str(source),source_hashes=hashes,analysis_sha256=sha(Path(__file__)),
        model_or_tool_reexecuted=False,new_llm_samples=0,new_protocol_samples=0,
        pairs=len(pairs),shared_intervention_pairs=sum(p['comparison_status']=='SHARED_INTERVENTION' for p in pairs),
        current_chain_check='NOT_REQUESTED',
        inference='observed implementation differences only; blockchain causal advantage requires new controlled experiments')
    def save():
        (output/'run_manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    save()
    try:
        (output/'traces.jsonl').write_text(''.join(json.dumps(p,ensure_ascii=False)+'\n' for p in pairs),encoding='utf8')
        write_csv(output/'cases.csv',pairs)
        write_csv(output/'aggregated_metrics.csv',metrics)
        if args.live_chain:
            checked = live_recovery_check(manifest,rows,cases)
            (output/'current-chain.json').write_text(json.dumps(checked,indent=2)+'\n',encoding='utf8')
            report['current_chain_check'] = 'PASS'
            report['current_chain_transactions'] = len(checked['transactions'])
            report['current_chain_node_receipts'] = checked['node_receipts']
        if any(sha(source/name)!=value for name,value in hashes.items()):
            raise ValueError('Original evidence changed during analysis')
        report['source_unchanged'] = True
        report['status'] = 'PASS'
        report['artifacts'] = {p.name:sha(p) for p in output.iterdir() if p.name!='run_manifest.json'}
        save()
    except Exception as error:
        report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise
    print(json.dumps({k:report[k] for k in ['status','pairs','shared_intervention_pairs','current_chain_check','new_protocol_samples']}))


if __name__=='__main__':
    main()
