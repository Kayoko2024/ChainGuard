import math
import pytest
from evaluation.metrics import aggregate,bootstrap,quantile,wilson


def test_wilson_keeps_uncertainty_for_zero_and_all_events():
    p,lo,hi=wilson(0,10)
    assert p==lo==0 and .27<hi<.28
    p,lo,hi=wilson(10,10)
    assert p==hi==1 and .72<lo<.73
    assert wilson(0,0)==(None,None,None)
    with pytest.raises(ValueError): wilson(11,10)


def test_quantiles_interpolate_and_empty_is_missing():
    assert quantile([1,2,3,4],.5)==2.5
    assert quantile([1,2,3,4],.95)==pytest.approx(3.85)
    assert quantile([],.99) is None


def test_unknown_is_not_blocked_and_absent_llm_is_not_zero_asr():
    rows=[dict(group=g,scenario='attack',sample_id='x',unauthorized_attempts=2,unauthorized_executions=0,
        unauthorized_blocked=1,unauthorized_unknown=1) for g in ['A','B','C']]
    result=aggregate(rows,replicates=30)
    uer=next(m for m in result if m['group']=='C' and m['metric']=='UER')
    assert uer['n']==2 and uer['estimate'] is None and uer['possible_upper_bound']==.5
    asr=next(m for m in result if m['group']=='A' and m['metric']=='ASR')
    assert asr['estimate'] is None and asr['n']==0 and asr['status']=='NOT_MEASURED'


def test_failed_performance_sample_stays_in_denominator():
    rows=[dict(group=g,scenario='normal',sample_id='x',task_eligible=1,task_completed=0,performance_eligible=True,
        elapsed_ms=123) for g in ['A','B','C']]
    result=aggregate(rows,replicates=30)
    assert next(m for m in result if m['group']=='B' and m['metric']=='TCR')['estimate']==0
    assert next(m for m in result if m['group']=='B' and m['metric']=='performance_failure_rate')['estimate']==1


def test_bootstrap_deterministic_and_unpaired_samples_rejected():
    rows=[{'scenario':'a','x':1},{'scenario':'a','x':1},{'scenario':'b','x':10}]
    statistic=lambda rs:sum(r['x'] for r in rs)/len(rs)
    assert bootstrap(rows,statistic,replicates=100)==bootstrap(rows,statistic,replicates=100)
    with pytest.raises(ValueError,match='Unpaired'):
        aggregate([dict(group='B',sample_id='missing',scenario='x',task_eligible=1,task_completed=0)],replicates=5)


def test_performance_intervals_resample_trials_not_a_single_scenario_cluster():
    rows=[dict(group=g,scenario='performance',sample_id=str(i),task_eligible=1,task_completed=1,
               performance_eligible=True,elapsed_ms=value) for g in ['A','B','C'] for i,value in enumerate([1,10,100,1000])]
    result=aggregate(rows,replicates=100)
    p50=next(m for m in result if m['group']=='C' and m['metric']=='elapsed_ms_P50')
    assert p50['ci95_low']<p50['estimate']<p50['ci95_high']


def test_invalid_counts_duplicates_and_nonfinite_latency_are_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        aggregate([dict(group='A',sample_id='x',scenario='s')]*2)
    with pytest.raises(ValueError,match='unknown'):
        aggregate([dict(group='A',sample_id='x',scenario='s',unauthorized_attempts=1,unauthorized_executions=1,unauthorized_unknown=1)])
    with pytest.raises(ValueError): quantile([math.inf],.5)


def test_shared_cohort_never_compares_unmatched_approval_denominators():
    rows=[dict(group=g,scenario='document-injection',sample_id='injection',unauthorized_attempts=1,
               unauthorized_executions=int(g=='A'),unauthorized_blocked=int(g!='A')) for g in ['A','B','C']]
    rows += [dict(group=g,scenario='forged-approval',sample_id='forgery',unauthorized_attempts=1,
                  unauthorized_executions=0,unauthorized_blocked=1) for g in ['B','C']]
    result=aggregate(rows,replicates=20)
    common=[m for m in result if m['metric']=='UER' and m['cohort']=='shared_tool_policy']
    assert len(common)==3 and {m['n'] for m in common}=={1}
    assert next(m for m in result if m['group']=='B' and m['metric']=='UER' and m['cohort']=='all_applicable')['n']==2
    with pytest.raises(ValueError,match='common'):
        aggregate(rows[1:],replicates=5)
