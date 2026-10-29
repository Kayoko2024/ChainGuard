"""Two local transaction senders race valid intents for one requester nonce.

Protocol-only real-Besu test. Never dispatches mail or signs a tool receipt.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from eth_account import Account
from eth_account.messages import encode_typed_data
from chainguard_gateway.chain_rpc import Chain
from chainguard_gateway.crypto import label, commit, typed_intent, PROTOCOL
from run_phase6 import find_signers


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = dict(status='RUNNING', track='protocol_concurrency', real_llm=False,
                  tool_dispatched=False, tool_receipt_created=False, transactions=[])
    def save():
        (args.out / 'shared-nonce.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    save()
    try:
        phase5 = json.loads((ROOT / 'results/phase5/besu-run-01/report.json').read_text())
        keys = find_signers(phase5)
        config = json.loads((ROOT / '.local/phase10/20261026T123255815352Z/runtime.json').read_text())['deployment']
        chain = Chain(config, [f'http://127.0.0.1:{p}' for p in range(8545, 8549)])
        before = chain.healthy(); report['before'] = before
        requester, agent = (phase5['publicSigners'][n].lower() for n in ['requester', 'agent'])
        nonce = secrets.randbits(63)
        assert not chain.execution.call('usedNonce', [requester, nonce])
        now = int(before['timestamp'])
        params = dict(to=['alice@inbox.chainguard.invalid'], subject='Concurrency protocol only', body='No tool dispatch')
        base = dict(schema_version=1, task_id='0x'+secrets.token_hex(32), requester=requester, agent=agent,
            tool_id=label('tool', 'mail.send'), resource_scope=label('scope', 'ORG_A_INTERNAL_MAIL'),
            params_commit=commit('params', '0x'+secrets.token_hex(32), params), policy_id=label('policy', 'POLICY_R2_MAIL'),
            policy_epoch=str(chain.policy.call('getEffectiveRule', [label('policy', 'POLICY_R2_MAIL')])['policyEpoch']),
            nonce=str(nonce), issued_at=str(now), expires_at=str(now+120), risk=2)
        intents = [dict(base, action_id='0x'+secrets.token_hex(32)) for _ in range(2)]
        sender_keys = [json.loads((ROOT / '.local/phase4/accounts.private.json').read_text())['sender'], keys['reconciler']]
        def signed_transaction(node, private_key, contract, method, arguments):
            sender = Account.from_key(private_key)
            signed = sender.sign_transaction(dict(chainId=20261026, nonce=int(node.call('eth_getTransactionCount',[sender.address.lower(),'pending']),16),
                gasPrice=0, gas=8000000, to=bytes.fromhex(contract.address[2:]), value=0, data=contract.data(method, arguments)))
            return '0x'+signed.raw_transaction.hex().removeprefix('0x'), '0x'+signed.hash.hex().removeprefix('0x')
        pending = []
        for index, intent in enumerate(intents):
            wire = typed_intent(intent, chain.domain)
            sigs = {n: '0x'+Account.sign_message(encode_typed_data(full_message=wire), keys[n]).signature.hex().removeprefix('0x') for n in ['requester','biz','security']}
            raw, tx_hash = signed_transaction(chain.nodes[index*2], sender_keys[index], chain.execution, 'reserve',
                [dict((target, intent[source]) for source,target in PROTOCOL['json_to_typed']['ActionIntent'].items()), sigs['requester'], [{'signature':sigs[n]} for n in ['biz','security']]])
            pending.append(raw)
            report['transactions'].append(dict(kind='reserve', tx_hash=tx_hash, action_id=intent['action_id'], intent=intent, signatures=sigs))
        # Persist public hashes before broadcasting; never save raw signed txs/keys.
        save()
        with ThreadPoolExecutor(max_workers=2) as pool:
            sent = list(pool.map(lambda x: chain.nodes[x*2].call('eth_sendRawTransaction', [pending[x]]), range(2)))
        assert sent == [t['tx_hash'] for t in report['transactions']]
        def receipts(tx_hash):
            deadline = time.monotonic()+60
            while time.monotonic() < deadline:
                rows = [n.call('eth_getTransactionReceipt', [tx_hash]) for n in chain.nodes]
                if all(rows):
                    assert all(r == rows[0] for r in rows)
                    for node,r in zip(chain.nodes,rows):
                        block = node.call('eth_getBlockByNumber', [r['blockNumber'],False])
                        assert block['hash'] == r['blockHash'] and tx_hash in block['transactions']
                    return rows
                time.sleep(.25)
            raise TimeoutError('Real receipt not confirmed; do not resubmit')
        for tx in report['transactions']:
            tx['node_receipts'] = receipts(tx['tx_hash'])
        assert sorted(int(t['node_receipts'][0]['status'],16) for t in report['transactions']) == [0,1]
        assert chain.execution.call('usedNonce', [requester, nonce])
        states = [chain.execution.call('getReservation', [i['action_id']])['status'] for i in intents]
        assert sorted(states) == [0,1]
        winner = intents[states.index(1)]
        raw, tx_hash = signed_transaction(chain.nodes[0], keys['reconciler'], chain.audit, 'markUnknown', [winner['action_id'], label('reason', 'PROTOCOL_TEST_NO_TOOL_DISPATCH')])
        report['transactions'].append(dict(kind='markUnknown', tx_hash=tx_hash)); save()
        assert chain.rpc.call('eth_sendRawTransaction', [raw]) == tx_hash
        report['transactions'][-1]['node_receipts'] = receipts(tx_hash)
        assert report['transactions'][-1]['node_receipts'][0]['status'] == '0x1'
        report.update(status='PASS', reservation_states=states, nonce_consumed=True,
            transaction_senders=[Account.from_key(k).address for k in sender_keys],
            final_winner_state=chain.execution.call('getReservation', [winner['action_id']])['status'],
            after=chain.healthy(), checked_at_utc=datetime.now(timezone.utc).isoformat(),
            limitation='Two local senders and RPC entrances, same-host validators. Not independent institutions or a B/C superiority experiment.')
        save()
        print(json.dumps(dict(status='PASS', reserves_accepted=1, reserves_reverted=1, node_receipts=12, tool_dispatched=False)))
    except Exception as error:
        report.update(status='FAIL', error_type=type(error).__name__); save(); raise


if __name__ == '__main__':
    main()
