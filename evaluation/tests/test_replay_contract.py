import copy
import hashlib
import json
from pathlib import Path

import pytest

from evaluation.replay import schedule, semantic_input, validate_plan

ROOT = Path(__file__).resolve().parents[2]


def plan():
    return json.loads((ROOT / 'evaluation/phase8_plan.json').read_text())


def test_schedule_is_deterministic_complete_and_rotates_group_order():
    p = plan()
    rows = schedule(p)
    assert rows == schedule(p)
    assert len(rows) == 3 * (len(p['scenarios']) * p['repetitions'] + p['performance_repetitions'])
    keys = [(r['group'], r['sample_id']) for r in rows]
    assert len(keys) == len(set(keys))
    assert len({tuple(r['group'] for r in rows[i:i + 3]) for i in range(0, len(rows), 3)}) > 1


def test_each_paired_trial_has_identical_task_data_arguments_and_policy():
    p = plan()
    rows = schedule(p)
    for i in range(0, len(rows), 3):
        inputs = [semantic_input(p, r) for r in rows[i:i + 3]]
        assert inputs[0] == inputs[1] == inputs[2]
        assert inputs[0]['grant']['allowed_recipients'] == ['alice@inbox.chainguard.invalid']
    attack = semantic_input(p, {'scenario': 'document-injection'})
    assert attack['params']['to'] == ['bob@inbox.chainguard.invalid']


@pytest.mark.parametrize('field,value', [('concurrency', 2), ('groups', ['B', 'C']), ('repetitions', 0), ('track', 'real_llm')])
def test_unsupported_plan_is_rejected_before_any_side_effect(field, value):
    p = plan()
    p[field] = value
    with pytest.raises(ValueError):
        validate_plan(p)


def test_trace_cannot_be_labelled_as_real_llm():
    p = plan()
    p['model']['llm_samples'] = 1
    with pytest.raises(ValueError, match='LLM'):
        validate_plan(p)


def test_pair_verification_rejects_model_claims_and_group_input_drift():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from verify_phase8 import verify_rows
    p = plan()
    rows = []
    for r in schedule(p):
        r = dict(r, input_sha256=hashlib.sha256(json.dumps(semantic_input(p, r), sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                 attack_success=None, llm_sample_count=0, attack_evaluable=0,
                 unauthorized_executions=0, unauthorized_blocked=0, unauthorized_unknown=0, unauthorized_attempts=0)
        rows.append(r)
    assert verify_rows(p, rows)
    changed = copy.deepcopy(rows)
    changed[0]['input_sha256'] = 'tampered'
    with pytest.raises(ValueError, match='mismatch'):
        verify_rows(p, changed)
    changed = copy.deepcopy(rows)
    changed[0]['attack_success'] = False
    with pytest.raises(ValueError, match='LLM'):
        verify_rows(p, changed)
    with pytest.raises(ValueError, match='Incomplete'):
        verify_rows(p, rows[:-1])


def test_behavior_verifier_rejects_real_security_regressions():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from verify_phase8 import check_behavior
    safe = dict(group='C', scenario='replay', mailbox_count=1, duplicate_effects=0,
                gateway_replay_attempts=10, tool_replay_attempts=10, unauthorized_executions=0)
    check_behavior(safe)
    with pytest.raises(AssertionError):
        check_behavior(dict(safe, duplicate_effects=1))
    with pytest.raises(AssertionError):
        check_behavior(dict(group='B', scenario='document-injection', mailbox_count=1, unauthorized_executions=1))
    with pytest.raises(AssertionError):
        check_behavior(dict(group='C', scenario='params-tamper', mailbox_count=1, error_code='PARAMS_MISMATCH'))


def test_evidence_verifier_cannot_broadcast_via_rpc():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from verify_phase8 import ReadOnlyRPC
    with pytest.raises(ValueError, match='read only'):
        ReadOnlyRPC('http://127.0.0.1:9').call('eth_sendRawTransaction', ['0x00'])
