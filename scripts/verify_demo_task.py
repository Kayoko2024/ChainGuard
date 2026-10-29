"""Verify one manually created Web task; never approve, reserve, or dispatch.

Outputs contain public evidence and comparison booleans, never mail text or salts.
Run on the trusted local operator machine, with the existing runtime and volumes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]

from Crypto.Cipher import AES
from chainguard_gateway.audit_verify import make_chain
from chainguard_gateway.canonical import canonical, validate
from chainguard_gateway.chain_crypto import digest
from chainguard_gateway.chain_rpc import Contract
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_gateway.phase10_bridge import DockerBridge
from chainguard_sandbox.protocol import ToolError


def require(condition, code):
    if not condition:
        raise ValueError(code)


def read_task(root, task_id):
    """No OperationsStore constructor: do not create keys, tables or sessions."""
    root = Path(root)
    key = (root / 'operations.key').read_bytes()

    def decrypt(raw):
        cipher = AES.new(key, AES.MODE_GCM, nonce=raw[:16])
        cipher.update(task_id.encode())
        return json.loads(cipher.decrypt_and_verify(raw[32:], raw[16:32]))

    with sqlite3.connect((root / 'operations.sqlite3').resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT state,data FROM jobs WHERE id=?', (task_id,)).fetchone()
        require(row is not None, 'TASK_NOT_FOUND')
        events = [decrypt(r[0]) for r in db.execute('SELECT data FROM events WHERE job_id=? ORDER BY id', (task_id,))]
    return dict(decrypt(row[1]), id=task_id, scheduler_state=row[0]), events


# Private salt never leaves the readonly gateway-volume observer. Only booleans,
# the public commitment and intent digest are returned to this process.
PARAMETER_CHECK = r'''
import json,sqlite3,sys
from Crypto.Cipher import AES
from chainguard_gateway.phase6_server import load
from chainguard_gateway.crypto import commit
from chainguard_gateway.chain_crypto import digest
from chainguard_gateway.canonical import canonical
root,config=load(); value=json.load(sys.stdin); aid=value['action_id']
with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:
    blob=db.execute('SELECT data FROM actions WHERE action_id=?',(aid,)).fetchone()[0]
cipher=AES.new((root/'data.key').read_bytes(),AES.MODE_GCM,nonce=blob[:12]); cipher.update(('action/'+aid).encode())
data=json.loads(cipher.decrypt_and_verify(blob[28:],blob[12:28]))
domain={'name':'ChainGuard ExecutionRegistry','version':'1','chainId':str(config['deployment']['chainId']),
        'verifyingContract':config['deployment']['contracts']['ExecutionRegistry']['address'].lower()}
print(json.dumps({'params_match_model':canonical(data['params'])==canonical(value['params']),
    'params_commit_valid':commit('params',data['salt'],data['params'])==data['intent']['params_commit'],
    'params_commit':data['intent']['params_commit'],'intent_digest':digest('ActionIntent',data['intent'],domain)}))
'''


def check_parameters(bridge, action_id, params):
    config = bridge.config
    args = ['run', '--rm', '-i', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--mount',
            'type=volume,src=' + config['containers']['gateway'] + ',dst=/sandbox,readonly',
            config['image'], 'python', '-c', PARAMETER_CHECK]
    return json.loads(bridge.docker(args, {'action_id': action_id, 'params': params}))


def check_model(job, events, plan):
    attempt = job.get('attempt', {})
    require(attempt.get('tool') == 'mail.send', 'NO_MAIL_AGENT_ATTEMPT')
    params = attempt['arguments']
    require(set(params['to']) <= set(job['allowed_recipients']), 'AGENT_OUTSIDE_TASK_SCOPE')
    matches = []
    for event in events:
        if event['kind'] != 'MODEL_EXCHANGE':
            continue
        exchange = event['exchange']
        if exchange.get('http_status') != 200:
            continue
        request = exchange['request']
        require(request['model'] == plan['model'], 'MODEL_CONFIG_MISMATCH')
        require(all(request.get(k) == v for k, v in plan['parameters'].items()), 'MODEL_CONFIG_MISMATCH')
        require(request.get('parallel_tool_calls') is False, 'MODEL_CONFIG_MISMATCH')
        for choice in exchange['response'].get('choices', []):
            for call in choice['message'].get('tool_calls') or []:
                fn = call['function']
                if fn['name'] in {'mail_send', 'mail.send'} and canonical(json.loads(fn['arguments'])) == canonical(params):
                    matches.append(exchange)
    require(bool(matches), 'MODEL_RESPONSE_DOES_NOT_MATCH_ATTEMPT')
    return params, len(matches)


def check_effect(expect, record, observation, checked, params):
    """Expectation-specific assertions: UNKNOWN or local receipt cannot pass as finalized."""
    if expect == 'unexecuted':
        require(record['state'] in {'AWAITING_APPROVAL', 'DENIED', 'EXPIRED'}, 'EXPECTED_UNEXECUTED')
        require(checked['status'] == 'NO_RESERVATION', 'RESERVATION_PRESENT_OR_UNAVAILABLE')
        require(not record['reservation_evidence'] and not record['receipt'] and not record['finalization_evidence'], 'EXECUTION_EVIDENCE_PRESENT')
        require(observation['status'] == 'ABSENT' and observation['mail_count'] == 0, 'SIDE_EFFECT_NOT_CONFIRMED_ABSENT')
        return
    require(observation['status'] == 'VERIFIED' and observation['mail_count'] == 1, 'MAIL_NOT_VERIFIED_OR_NOT_SINGLE')
    require(len(observation['messages']) == 1, 'MAIL_NOT_SINGLE')
    message = observation['messages'][0]
    # SMTP serializes text newlines as CRLF. The original parameter commitment
    # is checked separately over exact bytes; this compares decoded MIME text.
    def mail_text(value): return value.replace('\r\n','\n').rstrip('\n')
    require(params['to'] == [message['recipient']] and params['subject'] == message['subject'] and
            mail_text(params['body']) == mail_text(message['body']), 'MIME_DOES_NOT_MATCH_MODEL')
    if expect == 'unknown':
        require(record['state'] == 'UNKNOWN' and record['receipt'] is None, 'EXPECTED_UNKNOWN')
        require(checked['status'] == 'PENDING_RECEIPT' and not record['finalization_evidence'], 'EXPECTED_PENDING_RECEIPT')
    else:
        require(record['state'] == 'FINALIZED_OK' and checked['status'] == 'VERIFIED' and
                checked['current_chain_state'] == 'FINALIZED_OK', 'NOT_CHAIN_FINALIZED_OK')
        require(record['receipt'] == observation['receipt'] and record['tool_signature'] == observation['tool_signature'], 'TOOL_RECEIPT_MISMATCH')
        require(checked['tool_signature_valid'] is True, 'TOOL_SIGNATURE_INVALID')
        require(len({a['organization'] for a in checked['approvals']}) == 2, 'TWO_ORGANIZATIONS_REQUIRED')


def check_negative_controls(events, required=False):
    controls = [e for e in events if e['kind'] == 'MANUAL_NEGATIVE_CONTROL']
    require(not required or bool(controls), 'NEGATIVE_CONTROL_NOT_RUN')
    summaries = []
    for event in controls:
        result = event['result']
        require(event['agent_attempted_tool'] is False and result['error_code'] == 'UNAUTHORIZED_SCOPE', 'NEGATIVE_CONTROL_NOT_DENIED')
        require(result['gateway_actions_before'] == result['gateway_actions_after'] and
                result['mail_before'] == result['mail_after'], 'NEGATIVE_CONTROL_CHANGED_SIDE_EFFECTS')
        summaries.append({k: result[k] for k in ['error_code', 'gateway_actions_before', 'gateway_actions_after', 'mail_before', 'mail_after']})
    return summaries


def verify_task(deployment, task_id, expect, require_negative=False):
    validate('Bytes32', task_id)
    require(deployment['status'] == 'PASS', 'DEPLOYMENT_NOT_READY')
    config = json.loads(Path(deployment['config_path']).read_text(encoding='utf8'))
    bridge = DockerBridge(config)
    job, events = read_task(config['private_root'], task_id)
    negative_controls = check_negative_controls(events, require_negative)
    records = [r for r in bridge.snapshot() if r['task_id'] == job.get('grant', {}).get('task_id')]
    require(len(records) == 1, 'EXPECTED_ONE_ORIGINAL_ACTION')
    record = records[0]
    require(job.get('action_id') == record['action_id'], 'TASK_ACTION_MISMATCH')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(deployment['audit_url'] + '/audit-api/v1/actions', timeout=20) as response:
        rows = json.load(response)['actions']
    entries = [a for a in rows if a['sample_id'] == task_id]
    require(len(entries) == 1, 'AUDIT_PROJECTION_NOT_READY')
    entry = entries[0]
    for key in ['action_id', 'intent', 'state', 'receipt', 'tool_signature', 'requester_signature',
                'approval_signatures', 'reservation_evidence', 'finalization_evidence']:
        require(entry[key] == record[key], 'PROJECTION_DIFFERS_FROM_GATEWAY')
    plan = json.loads((ROOT / 'evaluation/live_plan.json').read_text(encoding='utf8'))
    params, matching_models = check_model(job, events, plan)
    parameter_check = check_parameters(bridge, record['action_id'], params)
    chain = make_chain(config['deployment'], [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
    intent_digest = digest('ActionIntent', record['intent'], chain.domain)
    require(parameter_check == dict(params_match_model=True, params_commit_valid=True,
            params_commit=record['intent']['params_commit'], intent_digest=intent_digest), 'PARAMETER_COMMITMENT_MISMATCH')
    humans = [e for e in events if e['kind'] == 'HUMAN_APPROVAL']
    require(all(e['intent_digest'] == intent_digest and e['signature'] in record['approval_signatures'] for e in humans), 'HUMAN_APPROVAL_MISMATCH')
    if expect != 'unexecuted':
        require({e['role'] for e in humans} == {'biz', 'security'}, 'HUMAN_APPROVALS_MISSING')
    checked = verify_live_entry(chain, entry)
    observation = bridge.observe(record['action_id'], include_mime=True)
    check_effect(expect, record, observation, checked, params)
    # Also query absence on every node. NO_RESERVATION alone only means that the
    # projection has no transaction; it is insufficient evidence of chain absence.
    absence = []
    if expect == 'unexecuted':
        for node in chain.nodes:
            contract = Contract('ExecutionRegistry', chain.execution.address, node)
            status = contract.call('getReservation', [record['action_id']], hex(int(checked['snapshot']['number'])))['status']
            require(status == 0, 'ONCHAIN_RESERVATION_EXISTS')
            absence.append(status)
    receipts = {}
    for tx in checked['transactions']:
        observed = [node.call('eth_getTransactionReceipt', [tx['tx_hash']]) for node in chain.nodes]
        require(all(r == observed[0] and r and r['status'] == '0x1' for r in observed), 'FOUR_NODE_RECEIPTS_MISMATCH')
        for node, receipt in zip(chain.nodes, observed):
            block = node.call('eth_getBlockByNumber', [receipt['blockNumber'], False])
            require(block['hash'] == receipt['blockHash'] and tx['tx_hash'] in block['transactions'], 'TX_NOT_IN_CANONICAL_BLOCK')
        receipts[tx['tx_hash']] = observed
    for name in ['phase0-freeze.json', 'phase3-policy-freeze.json']:
        for file, sha in json.loads((ROOT / 'config' / name).read_text())['files'].items():
            require(hashlib.sha256((ROOT / file).read_bytes()).hexdigest() == sha, 'FROZEN_SOURCE_CHANGED')
    return dict(status='PASS', expectation=expect, checked_at_utc=datetime.now(timezone.utc).isoformat(),
        business_task_id=task_id, action_id=record['action_id'], gateway_state=record['state'],
        verification=checked, parameter_check=parameter_check, matching_model_responses=matching_models,
        model_configuration=dict(model=plan['model'], parameters=plan['parameters']),
        manual_negative_control_logs=negative_controls,
        mail_count=observation['mail_count'], mime_sha256=[m['mime_sha256'] for m in observation['messages']],
        mail_checked_at_utc=observation['checked_at_utc'], original_tool_volume_readonly=True,
        no_task_creation_or_signing_or_dispatch=True, four_node_reservation_status=absence,
        receipt_count=4 * len(receipts), receipts=receipts,
        claim='链上终态与单封真实MIME一致' if expect == 'finalized' else
              '本次观察无预约、无邮件；不等于完整非法调用证明' if expect == 'unexecuted' else
              'UNKNOWN及单封真实MIME已观察；尚无链上完成结论')


def write_report(out, result):
    (out / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if result['status'] != 'PASS':
        text = f"# 核验未通过\n\n错误码：{result['error_code']}。不能据此声明执行成功。\n"
    else:
        checks = result['verification']
        lines = ['# 手动任务独立核验', '', f"结论：{result['claim']}", '',
                 f"- 业务任务：{result['business_task_id']}", f"- Action ID：{result['action_id']}",
                 f"- 核验时间：{result['checked_at_utc']}",
                 f"- 网关状态：{result['gateway_state']}；实时链核验：{checks['status']}",
                 f"- 四节点共同高度：{checks['snapshot']['number']}",
                 f"- 原工具卷邮件：{result['mail_count']}；MIME SHA-256：{', '.join(result['mime_sha256']) or '无'}",
                 f"- 已核对模型响应、参数承诺与审批；原始四节点 receipt 数：{result['receipt_count']}", '',
                 f"- 已核对手动越权负例日志：{len(result['manual_negative_control_logs'])} 次（非模型攻击样本）", '',
                 '| 类型 | 交易哈希 | 区块高度 |', '|---|---|---|']
        lines += [f"| {t['kind']} | {t['tx_hash']} | {t['block_number']} |" for t in checks['transactions']]
        lines += ['', '本报告不包含邮件正文、承诺盐、API Key或私钥。UNKNOWN不得作为执行完成。',
                  '本脚本不创建任务、不签名、不广播交易、不重发邮件；JSON包含可独立RPC复查的receipt。']
        text = '\n'.join(lines) + '\n'
    (out / 'verification.md').write_text(text, encoding='utf8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment', type=Path, default=ROOT / 'results/phase10/deploy-02/deployment.json')
    parser.add_argument('--task-id', required=True, help='业务任务 ID，非 Action ID')
    parser.add_argument('--expect', choices=['finalized', 'unexecuted', 'unknown'], default='finalized')
    parser.add_argument('--require-negative-control', action='store_true', help='要求此任务已运行网页越权负例，核对拒绝及前后计数日志')
    parser.add_argument('--out', type=Path, required=True, help='必须尚不存在的新结果目录')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    try:
        result = verify_task(json.loads(args.deployment.read_text(encoding='utf8')), args.task_id, args.expect, args.require_negative_control)
    except (ToolError, ValueError, OSError, KeyError, TypeError, IndexError, sqlite3.Error, subprocess.SubprocessError) as error:
        # Avoid printing private payloads or exceptions that may include them.
        code = error.code if isinstance(error, ToolError) else str(error) if type(error) is ValueError and str(error).isupper() else type(error).__name__
        result = dict(status='FAIL', expectation=args.expect, error_code=code)
    write_report(args.out, result)
    print(json.dumps({k: result[k] for k in ['status', 'expectation', 'claim', 'error_code'] if k in result}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
