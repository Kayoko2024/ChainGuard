"""Public audit projection. No parameter plaintext, salts, credentials or paths."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .canonical import validate


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project(case, evidence, index, source):
    record = evidence.get('record')
    intent = record.get('intent') if record else None
    receipt = record.get('receipt') if record else None
    if intent:
        validate('ActionIntent', intent)
    if receipt:
        validate('ExecutionReceipt', receipt)
    chain = case['group'] == 'C'
    return dict(entry_id=f'{source}-{index:04d}', group=case['group'], scenario=case['scenario'],
        sample_id=case['sample_id'], action_id=record['action_id'] if record else None,
        task_id=record['task_id'] if record else None,
        state=(record.get('state', record.get('central_state')) if record else 'NO_ACTION'),
        chain_state=record.get('chain_state', 'NONE') if record else 'NONE',
        risk=record.get('risk') if record else None, tool='mail.send',
        observed_tool_executed=case['tool_executed'], observed_mail_count=case['mailbox_count'],
        error_code=case.get('error_code'), intent=intent, receipt=receipt,
        requester_signature=evidence.get('requester_signature') if chain else None,
        approval_signatures=evidence.get('approvals', []) if chain else [],
        tool_signature=evidence.get('tool_signature') if chain else None,
        reservation_evidence=record.get('reservation_evidence') if chain and record else None,
        finalization_evidence=record.get('finalization_evidence') if chain and record else None,
        provenance=dict(track=case.get('track', 'protocol_replay'), source=source,
                        evidence_sha256=None, export_verification='PASS',
                        note='历史副作用已由独立工具卷核验；当前页面不能从承诺自动恢复原文'))


def export_catalog(directory, sources):
    """Caller first runs existing original-volume/chain verifiers on each source."""
    actions, deployments = [], []
    for source, path in sources:
        manifest = json.loads((path/'run_manifest.json').read_text(encoding='utf8'))
        deployments.append(manifest['deployment'])
        live = manifest['track'] == 'real_llm'
        files = sorted(path.glob('live-case-*.json' if live else 'case-*.json'))
        for index, file in enumerate(files):
            raw = json.loads(file.read_text(encoding='utf8'))
            case, evidence = (raw['row'], raw['evidence']) if live else (raw['case'], raw)
            item = project(case, evidence, index, source)
            item['provenance']['evidence_sha256'] = file_sha(file)
            actions.append(item)
    if not deployments or any(d != deployments[0] for d in deployments):
        raise ValueError('Audit sources must share the exact deployment')
    catalog = dict(schema_version=1, generated_at_utc=datetime.now(timezone.utc).isoformat(),
        deployment=deployments[0], actions=actions,
        trust_note='公开证据由本地操作员选取；完整性摘要不是独立信任根。C动作可重新查询四节点；A/B只展示已验证历史快照。')
    directory.mkdir(parents=True, exist_ok=False)
    (directory/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n',encoding='utf8')
    (directory/'catalog.sha256').write_text(file_sha(directory/'catalog.json')+'\n',encoding='ascii')
    return catalog
