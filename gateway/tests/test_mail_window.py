"""Window and historic-domain checks; real Besu evidence is produced separately."""
import copy
from types import SimpleNamespace
import pytest
from chainguard_gateway.mail_window import action_expiry,mail_lifetime,chain_for_action


def deployment():
    return {'contracts':{'PolicyRegistry':{'address':'0x'+'11'*20},'SourcePolicyRegistry':{'address':'0x'+'22'*20}},
            'mailApprovalWindow':{'version':1,'seconds':86400,'source_policy':'0x'+'22'*20}}


def test_legacy_remains_120_and_window_never_outlives_task_or_chain_rule():
    assert action_expiry(1000,100000,86400,{})==1120
    assert action_expiry(1000,100000,86400,deployment())==87400
    assert action_expiry(1000,1100,86400,deployment())==1100
    assert action_expiry(1000,100000,60,deployment())==1060


@pytest.mark.parametrize('seconds',[120,86401,172800,True])
def test_malformed_or_unpinned_profile_cannot_raise_limit(seconds):
    d=deployment();d['mailApprovalWindow']['seconds']=seconds
    with pytest.raises(ValueError):mail_lifetime(d)


def test_unknown_registry_cannot_choose_arbitrary_domain():
    c=SimpleNamespace(config={'legacyDeployments':[]},execution=SimpleNamespace(address='0x'+'11'*20))
    with pytest.raises(ValueError,match='Untrusted'):chain_for_action(c,{'reservation_evidence':{'registry':'0x'+'33'*20}})
    assert chain_for_action(c,{'reservation_evidence':{'registry':c.execution.address}}) is c


def test_history_uses_only_trusted_pin_and_does_not_rewrite_old_intent(monkeypatch):
    old={'contracts':{'ExecutionRegistry':{'address':'0x'+'22'*20}}}
    c=SimpleNamespace(config={'legacyDeployments':[old]},execution=SimpleNamespace(address='0x'+'11'*20),nodes=[SimpleNamespace(url='one'),SimpleNamespace(url='two')])
    row={'intent':{'expires_at':'1120'},'reservation_evidence':{'registry':old['contracts']['ExecutionRegistry']['address']}};before=copy.deepcopy(row)
    from chainguard_gateway import audit_verify
    monkeypatch.setattr(audit_verify,'make_chain',lambda d,urls:(d,urls))
    assert chain_for_action(c,row)==(old,['one','two']) and row==before


def test_business_task_and_read_capability_have_full_day(tmp_path,monkeypatch):
    import json
    import time
    from pathlib import Path
    from chainguard_agent.model import Turn
    from chainguard_gateway.phase10_store import OperationsStore,PublicStore
    from chainguard_gateway.phase10_service import Operations
    seen={}
    class Bridge:
        def call(self,role,value):
            seen.update(value['body'])
            return dict(value['body'],task_id=value['key'],requester='0x'+'11'*20)
        def grant_library(self,value):
            # Exercise the real tool admission validator, not just a permissive
            # bridge stub: the 24h/1h mismatch previously escaped this test.
            from chainguard_sandbox.default_library import validate_capability_expiry
            validate_capability_expiry(value['expires_at'])
            seen['read_expiry']=value['expires_at']
    class Backend:
        mode='unit'
        def next_turn(self,*_):return Turn('unit response, no tool execution')
    root=Path(__file__).resolve().parents[2]
    c=dict(deployment=json.loads((root/'results/phase5/besu-run-01/report.json').read_text()),signers={'agent':'0x'+'12'*20},repo=str(root))
    ops=Operations(OperationsStore(tmp_path/'private'),PublicStore(tmp_path/'public.sqlite'),Bridge(),c,backend_factory=lambda _:Backend())
    monkeypatch.setattr(time,'time',lambda:1000000)
    id='0x'+'aa'*32
    ops.create(id,dict(task_text='read only',allowed_tools=['doc.list'],allowed_document_ids=['meeting-notes'],read_mailboxes=[],allowed_recipients=[]))
    ops.run_agent(id)
    assert int(seen['expires_at'])==1000000+86400 and seen['read_expiry']==1000000+86400
    assert ops.store.get(id)['state']=='NO_ACTION'
