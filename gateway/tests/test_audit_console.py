"""Audit fixtures test the observer only; they do not assert real chain execution."""
import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.audit_console import create_audit_app,load_catalog
from chainguard_gateway.audit_projection import project
from chainguard_gateway.audit_verify import AuditRPC,verify_action
from chainguard_sandbox.protocol import ToolError

ROOT=Path(__file__).resolve().parents[2]


def fixture():
    path=next((ROOT/'results/phase8/complete-experiment-01/protocol').glob('case-*.json'))
    data=json.loads(path.read_text(encoding='utf8'))
    return project(data['case'],data,0,'protocol')


class Offline:
    def healthy(self): raise ToolError('CHAIN_UNAVAILABLE')


def catalog():
    return dict(schema_version=1,deployment={'chainId':20261026},generated_at_utc='fixture',trust_note='fixture',actions=[fixture()])


def test_public_projection_never_copies_parameters_mailbox_or_credentials():
    original=fixture()
    raw=json.dumps(original)
    for field in ['mime_b64','params_salt','relay_key','api_key','tool_root','authorized_mail','signing_keys']:
        assert field not in raw
    assert original['action_id'] and original['intent']['params_commit']


def test_offline_keeps_historical_state_and_does_not_report_verified():
    a=fixture(); state=a['state']
    result=verify_action(Offline(),a)
    assert result['status']=='UNAVAILABLE' and result['snapshot'] is None
    assert result['historical_state']==state and a['state']==state and result['tool_signature_valid'] is None


@pytest.mark.parametrize('method',['eth_sendRawTransaction','eth_sendTransaction','admin_addPeer','miner_start','personal_unlockAccount','debug_traceTransaction'])
def test_audit_rpc_rejects_all_write_admin_and_arbitrary_debug_methods(method):
    with pytest.raises(ValueError,match='read only'):
        AuditRPC('http://127.0.0.1:1').call(method,[])


@pytest.mark.parametrize('path',['/v1/agent/actions/propose','/v1/actions/reserve','/operator/v1/review','/internal/v1/tools/execute','/audit-api/v1/actions/protocol-0000/verify'])
def test_console_has_no_mutating_endpoints(path):
    response=TestClient(create_audit_app(catalog(),Offline())).post(path,json={'signature':'ignored'})
    assert response.status_code in [404,405]


def test_api_offline_headers_host_and_missing_entry():
    client=TestClient(create_audit_app(catalog(),Offline()))
    assert client.get('/health/live').json()['read_only']
    response=client.get('/audit-api/v1/network')
    assert response.status_code==503 and response.json()['status']=='UNAVAILABLE'
    assert response.headers['cache-control']=='no-store' and "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert client.get('/audit-api/v1/actions/missing').status_code==404
    assert client.get('/audit-api/v1/actions',headers={'Host':'evil.example'}).status_code==400
    assert not client.get('/audit-api/v1/actions').headers.get('access-control-allow-origin')


def test_tampered_catalog_rejected_before_serving(tmp_path):
    from chainguard_gateway.audit_projection import file_sha
    path=tmp_path/'catalog.json'
    path.write_text(json.dumps(catalog()),encoding='utf8')
    path.with_suffix('.sha256').write_text(file_sha(path))
    assert load_catalog(path)['schema_version']==1
    path.write_text(json.dumps(dict(catalog(),generated_at_utc='altered')),encoding='utf8')
    with pytest.raises(ValueError,match='digest'):load_catalog(path)


def test_central_data_never_claims_chain_verification():
    a=dict(fixture(),group='B')
    result=verify_action(Offline(),a)
    assert result['status']=='HISTORICAL_ONLY' and result['snapshot'] is None


def test_forged_action_cannot_use_valid_transaction_with_another_action():
    # Healthy unit stub isolates early identity mismatch; real receipts are tested by smoke.
    class Healthy:
        def healthy(self):return {'number':'1'}
    a=fixture();a['action_id']='0x'+'00'*32
    assert verify_action(Healthy(),a)['status']=='INVALID'
