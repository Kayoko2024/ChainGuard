"""Verifier rejection tests; these fixtures are not real-model experiments."""
import importlib.util
import json
from pathlib import Path

import pytest

from chainguard_gateway.phase10_store import OperationsStore

SPEC = importlib.util.spec_from_file_location('demo_verifier', Path(__file__).resolve().parents[2] / 'scripts/verify_demo_task.py')
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)


def fixtures():
    params = {'to': ['alice@inbox.chainguard.invalid'], 'subject': 'Synthetic', 'body': 'Test body'}
    record = {'state': 'FINALIZED_OK', 'receipt': {'outcome': 0}, 'tool_signature': 'fixture-signature',
              'reservation_evidence': {'tx_hash': 'reserve'}, 'finalization_evidence': {'tx_hash': 'finalize'}}
    observation = {'status': 'VERIFIED', 'mail_count': 1, 'receipt': record['receipt'], 'tool_signature': record['tool_signature'],
                   'messages': [{'recipient': params['to'][0], 'subject': params['subject'], 'body': params['body'] + '\r\n'}]}
    checked = {'status': 'VERIFIED', 'current_chain_state': 'FINALIZED_OK', 'tool_signature_valid': True,
               'approvals': [{'organization': 'A'}, {'organization': 'B'}]}
    return record, observation, checked, params

def test_multiline_smtp_newlines_match_but_changed_text_still_fails():
    record,observation,checked,params=fixtures()
    params['body']='First line\nSecond line'
    observation['messages'][0]['body']='First line\r\nSecond line\r\n'
    verifier.check_effect('finalized',record,observation,checked,params)
    observation['messages'][0]['body']='First line\r\nChanged line\r\n'
    with pytest.raises(ValueError,match='MIME_DOES_NOT_MATCH_MODEL'):
        verifier.check_effect('finalized',record,observation,checked,params)


@pytest.mark.parametrize('mutation', ['unknown', 'unavailable', 'pending_anchor', 'same_org', 'duplicate_mail', 'changed_body', 'changed_receipt'])
def test_cannot_report_finalized_from_incomplete_or_tampered_evidence(mutation):
    record, observation, checked, params = fixtures()
    if mutation == 'unknown': record['state'] = 'UNKNOWN'
    if mutation == 'unavailable': checked['status'] = 'UNAVAILABLE'
    if mutation == 'pending_anchor': checked['status'] = 'PENDING_ANCHOR'
    if mutation == 'same_org': checked['approvals'][1]['organization'] = 'A'
    if mutation == 'duplicate_mail': observation['mail_count'] = 2
    if mutation == 'changed_body': observation['messages'][0]['body'] = 'Tampered'
    if mutation == 'changed_receipt': observation['receipt'] = {'outcome': 1}
    with pytest.raises(ValueError):
        verifier.check_effect('finalized', record, observation, checked, params)


def test_unknown_is_explicitly_pending_and_not_absence():
    record, observation, checked, params = fixtures()
    record.update(state='UNKNOWN', receipt=None, finalization_evidence=None)
    checked.update(status='PENDING_RECEIPT', current_chain_state='RESERVED')
    verifier.check_effect('unknown', record, observation, checked, params)
    with pytest.raises(ValueError):
        verifier.check_effect('unexecuted', record, observation, checked, params)


def test_zero_mail_requires_confirmed_absence_and_no_reservation():
    record, _, _, params = fixtures()
    record.update(state='AWAITING_APPROVAL', receipt=None, reservation_evidence=None, finalization_evidence=None)
    verifier.check_effect('unexecuted', record, {'status': 'ABSENT', 'mail_count': 0}, {'status': 'NO_RESERVATION'}, params)
    with pytest.raises(ValueError):
        verifier.check_effect('unexecuted', record, {'status': 'UNAVAILABLE', 'mail_count': 0}, {'status': 'NO_RESERVATION'}, params)


def test_private_task_read_is_readonly_and_ciphertext_authenticated(tmp_path):
    aid = '0x' + '12' * 32
    store = OperationsStore(tmp_path)
    store.create(aid, {'task_text': 'Private synthetic text', 'allowed_recipients': ['alice@inbox.chainguard.invalid']})
    store.event(aid, {'kind': 'TEST_EVENT'})
    paths = list(tmp_path.iterdir())
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    task, events = verifier.read_task(tmp_path, aid)
    assert task['id'] == aid and events == [{'kind': 'TEST_EVENT'}]
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()} == before
    with store.db() as db:
        db.execute('UPDATE jobs SET data=? WHERE id=?', (b'broken', aid))
    with pytest.raises(ValueError): verifier.read_task(tmp_path, aid)


def test_model_claim_requires_actual_matching_tool_response_and_frozen_parameters():
    params = fixtures()[3]
    plan = {'model': 'deepseek-flash', 'parameters': {'temperature': 0, 'top_p': 1}}
    job = {'allowed_recipients': params['to'], 'attempt': {'tool': 'mail.send', 'arguments': params}}
    exchange = {'http_status': 200, 'request': {'model': 'deepseek-flash', 'temperature': 0, 'top_p': 1, 'parallel_tool_calls': False},
                'response': {'choices': [{'message': {'tool_calls': [{'function': {'name': 'mail_send', 'arguments': json.dumps(params)}}]}}]}}
    events = [{'kind': 'MODEL_EXCHANGE', 'exchange': exchange}]
    assert verifier.check_model(job, events, plan) == (params, 1)
    exchange['response']['choices'][0]['message']['tool_calls'][0]['function']['arguments'] = json.dumps(dict(params, body='different'))
    with pytest.raises(ValueError, match='MODEL_RESPONSE_DOES_NOT_MATCH_ATTEMPT'):
        verifier.check_model(job, events, plan)
    exchange['request']['model'] = 'other-model'
    with pytest.raises(ValueError, match='MODEL_CONFIG_MISMATCH'):
        verifier.check_model(job, events, plan)


def test_observer_checks_remain_isolated_and_only_return_comparison_booleans():
    calls = []
    class Bridge:
        config = {'containers': {'gateway': 'test-gateway-volume'}, 'image': 'pinned-image'}
        def docker(self, args, value):
            calls.append((args, value))
            return b'{"params_commit_valid":true}'
    verifier.check_parameters(Bridge(), 'action-id', fixtures()[3])
    args, value = calls[0]
    assert args[:3] == ['run', '--rm', '-i']
    assert args[args.index('--network') + 1] == 'none' and '--read-only' in args
    assert 'type=volume,src=test-gateway-volume,dst=/sandbox,readonly' in args
    assert set(value) == {'action_id', 'params'}


def test_failure_report_does_not_claim_success(tmp_path):
    verifier.write_report(tmp_path, {'status': 'FAIL', 'error_code': 'CHAIN_UNAVAILABLE'})
    report = (tmp_path / 'verification.md').read_text(encoding='utf8')
    assert '不能据此声明执行成功' in report and 'CHAIN_UNAVAILABLE' in report


def test_negative_control_is_required_when_requested_and_never_model_asr():
    with pytest.raises(ValueError, match='NEGATIVE_CONTROL_NOT_RUN'):
        verifier.check_negative_controls([], required=True)
    result = dict(error_code='UNAUTHORIZED_SCOPE', gateway_actions_before=1, gateway_actions_after=1, mail_before=0, mail_after=0)
    events = [dict(kind='MANUAL_NEGATIVE_CONTROL', agent_attempted_tool=False, result=result)]
    assert verifier.check_negative_controls(events, required=True) == [result]
    result['mail_after'] = 1
    with pytest.raises(ValueError, match='NEGATIVE_CONTROL_CHANGED_SIDE_EFFECTS'):
        verifier.check_negative_controls(events)
