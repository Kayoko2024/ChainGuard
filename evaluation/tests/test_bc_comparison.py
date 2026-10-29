import copy

import pytest

from evaluation.bc_comparison import pair_rows, comparison_metrics


def rows():
    base=dict(sample_id='fault-after-tool/0',input_sha256='same',scenario='fault-after-tool',trial=0,
        mechanism_applicable=True,mailbox_count=1,task_completed=1,elapsed_ms=100,
        observed_states=['UNKNOWN'],performance_eligible=False,status='PASS')
    return [dict(base,group='B',final_state='UNKNOWN'),dict(base,group='C',final_state='FINALIZED_OK')]


def test_actual_mail_is_not_the_same_as_acknowledged_completion():
    data=rows();pairs=pair_rows(data)
    assert pairs[0]['B_task_completed']==pairs[0]['C_task_completed']==1
    assert pairs[0]['B_acknowledged']==0 and pairs[0]['C_acknowledged']==1
    metrics=comparison_metrics(data,pairs)
    assert all(m['estimate']==1 for m in metrics if m['metric']=='effect_completed')


@pytest.mark.parametrize('mutation',['missing','duplicate','input_sha256','scenario','trial'])
def test_mismatched_or_missing_pairs_are_never_silently_dropped(mutation):
    data=copy.deepcopy(rows())
    if mutation=='missing':data.pop()
    elif mutation=='duplicate':data.append(data[0])
    else:data[1][mutation]='changed'
    with pytest.raises(ValueError):pair_rows(data)


def test_c_only_failure_is_visible_but_not_a_shared_intervention():
    data=rows();data[0]['mechanism_applicable']=False
    pairs=pair_rows(data)
    assert pairs[0]['comparison_status']=='MECHANISM_NOT_SHARED'
    metrics=comparison_metrics(data,pairs)
    assert all(m['comparison_status']=='MECHANISM_NOT_SHARED' for m in metrics if m['scenario']=='fault-after-tool')


def test_unknown_execution_does_not_become_a_task_success_or_performance_sample():
    data=rows()
    for r in data:r.update(final_state='UNKNOWN',mailbox_count=0,task_completed=0,performance_eligible=True,status='ERROR')
    pairs=pair_rows(data)
    assert all(not p['B_acknowledged'] and not p['C_acknowledged'] for p in pairs)
    metrics=comparison_metrics(data,pairs)
    assert all(m['n']==0 and m['estimate'] is None for m in metrics if m['metric'].endswith('P50'))
    assert all(m['k']==1 and m['n']==1 for m in metrics if m['metric']=='failure_count')


def test_unobserved_physical_effect_retains_bounds_instead_of_becoming_a_failure():
    data=rows()
    for r in data:r.update(final_state='UNKNOWN',task_completed=0,task_unknown=1,mailbox_count=None)
    metrics=comparison_metrics(data,pair_rows(data))
    effects=[m for m in metrics if m['metric']=='effect_completed']
    assert all(m['estimate'] is None and m['ci95_low'] is None and m['unknown']==1 for m in effects)
    assert all(m['observed_lower_bound']==0 and m['possible_upper_bound']==1 for m in effects)
