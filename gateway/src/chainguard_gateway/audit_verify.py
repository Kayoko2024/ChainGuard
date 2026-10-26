"""Read-only live ledger verification. Never grants or changes execution authority."""
from datetime import datetime, timezone
from eth_abi import decode
from .chain_rpc import Chain, RPC, STATES
from .chain_crypto import digest, recover_receipt
from .crypto import PROTOCOL, recover_intent, label
from chainguard_sandbox.protocol import ToolError

METHODS={'eth_chainId','eth_syncing','eth_blockNumber','eth_getBlockByNumber',
         'qbft_getValidatorsByBlockNumber','net_peerCount','eth_getCode',
         'eth_getTransactionReceipt','eth_getTransactionByHash','eth_call'}


class AuditRPC(RPC):
    def call(self, method, params=None):
        if method not in METHODS:
            raise ValueError('Audit RPC is read only')
        value=super().call(method,params)
        if method=='qbft_getValidatorsByBlockNumber' and not isinstance(value,list):
            raise ToolError('CHAIN_UNAVAILABLE')
        return value


def make_chain(deployment, urls):
    if len(urls) != 4:
        raise ValueError('Four real independent endpoints required')
    chain=Chain(deployment,urls)
    chain.nodes=[AuditRPC(url) for url in urls]
    chain.rpc=chain.nodes[0]
    for contract in [chain.policy,chain.execution,chain.audit]:
        contract.rpc=chain.rpc
    return chain


def require(condition):
    if not condition:
        raise ValueError('AUDIT_EVIDENCE_MISMATCH')


def same_typed(kind, wire, typed):
    return all(str(typed[target])==str(wire[source]) for source,target in PROTOCOL['json_to_typed'][kind].items())


def verify_action(chain, action):
    result=dict(status='UNVERIFIED', checked_at_utc=datetime.now(timezone.utc).isoformat(),
        entry_id=action['entry_id'], approvals=[], tool_signature_valid=None, transactions=[],
        historical_state=action['state'], current_chain_state=None, snapshot=None,
        scope='只读链证据与签名复核；原始敏感参数不向浏览器提供')
    if action['group'] != 'C':
        return dict(result,status='HISTORICAL_ONLY',reason='A/B为已独立验证的中央历史证据，不声明链上确认')
    try:
        snapshot=chain.healthy()
        result['snapshot']=snapshot
        if not action['reservation_evidence']:
            require(not action['receipt'] and not action['finalization_evidence'])
            return dict(result,status='NO_RESERVATION',reason='此记录没有预约交易，不作为链上执行成功')
        intent=action['intent']; reserve=action['reservation_evidence']; action_id=action['action_id']
        require(intent['action_id']==action_id)
        actual,reservation_receipt,event=chain.transaction_evidence(reserve['tx_hash'],chain.execution.address,snapshot,
            'ActionReserved(bytes32,bytes32,bytes32,bytes32,uint64)',action_id)
        require(actual==reserve)
        require(event['topics'][2]==intent['task_id'])
        require(decode(['bytes32','bytes32','uint64'],bytes.fromhex(event['data'][2:])) ==
            (bytes.fromhex(intent['tool_id'][2:]),bytes.fromhex(intent['params_commit'][2:]),int(intent['policy_epoch'])))
        tx=chain.rpc.call('eth_getTransactionByHash',[reserve['tx_hash']])
        typed,requester,approvals=chain.execution.decode_input('reserve',tx['input'])
        require(same_typed('ActionIntent',intent,typed))
        require(requester==action['requester_signature'] and [a['signature'] for a in approvals]==action['approval_signatures'])
        require(recover_intent(intent,chain.domain,requester)==intent['requester'])
        historic={'number':str(int(reservation_receipt['blockNumber'],16))}
        chain.validate_authorization(intent,requester,action['approval_signatures'],historic,live=False)
        block=hex(int(historic['number']))
        current_block=hex(int(snapshot['number']))
        for signature in action['approval_signatures']:
            address=recover_intent(intent,chain.domain,signature)
            actor=chain.actor(address,intent['resource_scope'],block)
            current=chain.actor(address,intent['resource_scope'],current_block)
            org_label=next((name for name in ['OrgA_Business','OrgB_Security'] if label('org',name)==actor['organization']),actor['organization'])
            result['approvals'].append(dict(address=address,organization=actor['organization'],organization_label=org_label,
                roles=actor['roles'],signature=signature,valid_at_reservation=True,current_active=current['active']))
        reservation=chain.execution.call('getReservation',[action_id],current_block)
        require(reservation['intentHash']==digest('ActionIntent',intent,chain.domain))
        require(reservation['approvers']==[a['address'] for a in result['approvals']])
        require(chain.execution.call('usedNonce',[intent['requester'],intent['nonce']],current_block))
        result['current_chain_state']=STATES[reservation['status']]
        result['transactions'].append(dict(kind='reserve',**actual,confirmations=str(int(snapshot['number'])-int(actual['block_number'])+1),node_receipts=4))
        receipt=action['receipt']
        if receipt:
            require(receipt['action_id']==action_id and receipt['params_commit']==intent['params_commit'])
            signer=recover_receipt(receipt,chain.receipt_domain,action['tool_signature'])
            final=action['finalization_evidence']; require(bool(final))
            final_tx=chain.rpc.call('eth_getTransactionByHash',[final['tx_hash']])
            # UNKNOWN recovery is anchored through reconcile, normal path through finalize.
            try:
                typed_receipt,signature=chain.audit.decode_input('finalize',final_tx['input'])
                fn='finalize'
            except ToolError:
                typed_receipt,signature=chain.audit.decode_input('reconcile',final_tx['input'])
                fn='reconcile'
            require(same_typed('ExecutionReceipt',receipt,typed_receipt) and signature==action['tool_signature'])
            event_name='ActionFinalized(bytes32,bytes32,address,uint8)'
            actual,final_receipt,final_event=chain.transaction_evidence(final['tx_hash'],chain.audit.address,snapshot,event_name,action_id)
            require(actual==final)
            require(chain.audit.call('receiptHash',[action_id],current_block)==digest('ExecutionReceipt',receipt,chain.receipt_domain))
            require(reservation['status']==3+receipt['outcome'])
            historic_actor=chain.actor(signer,intent['resource_scope'],final_receipt['blockNumber'])
            require(historic_actor['active'] and 'TOOL_SIGNER' in historic_actor['roles'])
            require(chain.policy.call('isToolSigner',[intent['tool_id'],signer],final_receipt['blockNumber']))
            require(chain.audit.call('receiptSigner',[action_id],current_block)==signer)
            result.update(tool_signature_valid=True,tool_signer=signer,
                current_tool_signer_active=chain.actor(signer,intent['resource_scope'],current_block)['active'])
            result['transactions'].append(dict(kind=fn,**actual,confirmations=str(int(snapshot['number'])-int(actual['block_number'])+1),node_receipts=4))
            return dict(result,status='VERIFIED',reason='原意图/跨组织签名、nonce、四节点交易/事件及工具签名回执吻合；历史副作用另由工具卷核验')
        require(not action['finalization_evidence'])
        return dict(result,status='PENDING_RECEIPT',reason='预约存在，缺少工具签名回执；不得推断未执行或再次执行')
    except ToolError as error:
        return dict(result,status='UNAVAILABLE' if error.code=='CHAIN_UNAVAILABLE' else 'INVALID',reason=error.code)
    except (ValueError,KeyError,TypeError,IndexError,StopIteration):
        return dict(result,status='INVALID',reason='AUDIT_EVIDENCE_MISMATCH')
