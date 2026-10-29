import copy
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from evaluation.bc_live import validate_plan, schedule, metrics, volume_verify, verify_observation


def plan():
    return json.loads((Path(__file__).resolve().parents[1] / 'bc_live_plan.json').read_text())


def test_schedule_is_complete_paired_and_reproducible():
    p = plan()
    rows = schedule(p)
    assert rows == schedule(p)
    assert len(rows) == (8 * 2 - 1) * p['repetitions'] + 2 * p['performance_repetitions']
    assert sum(r['scenario'] == 'one-rpc-outage' for r in rows) == 3
    assert all(r['group'] == 'C' for r in rows if r['scenario'] == 'one-rpc-outage')
    assert p['llm_samples'] == 0


@pytest.mark.parametrize('field,value', [('llm_samples', 1), ('groups', ['A', 'C']), ('timeout_seconds', 121), ('repetitions', 0)])
def test_plan_rejects_changed_scope_and_deadlines(field, value):
    p = plan()
    p[field] = value
    with pytest.raises(ValueError):
        validate_plan(p)


def observations():
    # Statistics-only synthetic fixture; never saved or counted as actual experiments.
    return [dict(c, input_sha256='same', error=False, acknowledged=True, elapsed_ms=100,
                 gas_used=0, state_bytes=100, metadata_recovered=False, full_replica_recovered=True)
            for c in schedule(plan())]


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'input'])
def test_metrics_fail_closed_on_incomplete_or_mismatched_pairs(mutation):
    rows = observations()
    if mutation == 'missing':
        rows.pop()
    elif mutation == 'duplicate':
        rows.append(rows[0])
    else:
        target = next(r for r in rows if r['scenario'] != 'one-rpc-outage')
        target['input_sha256'] = 'different'
    with pytest.raises(ValueError):
        metrics(rows, plan())


def test_full_replica_is_separate_control_and_asr_is_never_invented():
    result = metrics(observations(), plan())
    replica = [m for m in result if m['group'] == 'B+log']
    assert len(replica) == 1 and replica[0]['n'] == 3 and replica[0]['estimate'] == 1
    assert not any(m['metric'] == 'ASR' for m in result)


def test_performance_excludes_failed_observations_without_removing_failures():
    rows = observations()
    next(r for r in rows if r['group'] == 'B' and r['scenario'] == 'performance')['error'] = True
    result = metrics(rows, plan())
    assert next(m for m in result if m['group'] == 'B' and m['metric'] == 'elapsed_ms_P50')['n'] == 9
    failure = next(m for m in result if m['group'] == 'B' and m['scenario'] == 'performance' and m['metric'] == 'error')
    assert failure['k'] == 1 and failure['n'] == 10


def test_volume_verifier_rejects_host_paths():
    case = dict(primary=dict(tool_root='C:/real-data', mailbox=[]), replicas=[], intervention={},
                observation=dict(group='B', mailbox_count=0, sample_id='x'))
    with pytest.raises(AssertionError):
        volume_verify([case])


def test_evidence_index_metadata_does_not_mask_changed_execution_fields():
    row = dict(action_id='a', mailbox_count=2, evidence_file='case.json')
    verify_observation(row, dict(row))
    verify_observation(row, dict(action_id='a', mailbox_count=2))
    with pytest.raises(ValueError):
        verify_observation(row, dict(action_id='a', mailbox_count=1))


def test_fresh_registries_do_not_inherit_live_window_or_legacy_signing_domains():
    from evaluation.bc_live import isolated_deployment
    from chainguard_gateway.mail_window import mail_lifetime
    source = dict(chainId=20261026, genesisHash='0x' + '00' * 32, validators=['validator-a'],
        contracts={'PolicyRegistry': {'address': '0x' + '11' * 20},
                   'SourcePolicyRegistry': {'address': '0x' + '22' * 20}},
        mailApprovalWindow={'version': 1, 'seconds': 86400, 'source_policy': '0x' + '22' * 20},
        legacyDeployments=[{'contracts': {'ExecutionRegistry': {'address': '0x' + '33' * 20}}}])
    contracts = {name: {'address': '0x' + value * 20} for name, value in [
        ('PolicyRegistry', '44'), ('ExecutionRegistry', '55'), ('AuditRegistry', '66')]}
    original, addresses = copy.deepcopy(source), copy.deepcopy(contracts)
    isolated = isolated_deployment(source, contracts)
    assert mail_lifetime(source) == 86400 and mail_lifetime(isolated) == 120
    assert set(isolated) == {'chainId', 'genesisHash', 'validators', 'contracts'}
    assert isolated['contracts'] == contracts
    assert source == original and contracts == addresses
    isolated['validators'].append('other')
    isolated['contracts']['PolicyRegistry']['address'] = 'changed'
    assert source == original and contracts == addresses
