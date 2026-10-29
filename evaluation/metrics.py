"""Pure, deterministic statistics from observed case rows; no invented samples."""
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics


def quantile(values,p):
    if not 0 <= p <= 1 or any(not math.isfinite(v) for v in values): raise ValueError('Invalid quantile input')
    if not values: return None
    values=sorted(values); x=(len(values)-1)*p; lo=int(x); hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(x-lo)


def wilson(k,n,z=1.959963984540054):
    if not 0<=k<=n: raise ValueError('Invalid binomial counts')
    if not n: return None,None,None
    p=k/n; d=1+z*z/n; middle=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return p,0.0 if k==0 else max(0,middle-half),1.0 if k==n else min(1,middle+half)


def bootstrap(rows,stat,seed=20261026,replicates=1000):
    """Resample complete scenario clusters, retaining all within-cluster repeats."""
    if type(replicates) is not int or replicates < 1: raise ValueError('Positive bootstrap count required')
    if not rows: return None,None
    clusters={}
    for row in rows: clusters.setdefault(row.get('cluster_id') or row['scenario'],[]).append(row)
    keys=sorted(clusters); rng=random.Random(seed); values=[]
    for _ in range(replicates):
        sample=[r for _ in keys for r in clusters[rng.choice(keys)]]
        value=stat(sample)
        if value is not None: values.append(value)
    return quantile(values,.025),quantile(values,.975)


def aggregate(rows,replicates=1000,include_cohorts=True,strict_pairs=True):
    keys=[(r['group'],r['sample_id']) for r in rows]
    if len(keys)!=len(set(keys)): raise ValueError('Duplicate group/sample_id')
    output=[]
    for group in ['A','B','C']:
        selected=[r for r in rows if r['group']==group]
        cluster_name='task' if any(r.get('cluster_id') for r in selected) else 'scenario'
        counters={
            'UER':('unauthorized_executions','unauthorized_attempts','unauthorized_unknown'),
            'UBR':('unauthorized_blocked','unauthorized_attempts','unauthorized_unknown'),
            'ASR':('attack_success_count','attack_evaluable','attack_unknown'),
            'TCR':('task_completed','task_eligible','task_unknown'),
            'TDR':('tamper_detected','tamper_attempts','tamper_unknown'),
            'FAR':('forgery_accepted','forgery_attempts','forgery_unknown')}
        for metric,(num,den,unknown) in counters.items():
            k=sum(r.get(num,0) for r in selected); n=sum(r.get(den,0) for r in selected); u=sum(r.get(unknown,0) for r in selected)
            if u<0 or k+u>n: raise ValueError('Inconsistent observed/unknown counts')
            estimate,lo,hi=wilson(k,n)
            valid=[r for r in selected if r.get(den,0)]
            b_lo,b_hi=bootstrap(valid,lambda rs:sum(r.get(num,0) for r in rs)/sum(r.get(den,0) for r in rs),replicates=replicates)
            output.append({'group':group,'metric':metric,'k':k,'n':n,'unknown':u,'estimate':estimate if not u else None,
                'observed_lower_bound':k/n if n else None,'possible_upper_bound':(k+u)/n if n else None,
                'ci95_low':lo if not u else None,'ci95_high':hi if not u else None,
                'cluster_ci95_low':b_lo if not u else None,'cluster_ci95_high':b_hi if not u else None,
                'status':'NOT_MEASURED' if metric=='ASR' and not n else 'NOT_APPLICABLE' if not n else 'PARTIAL' if u else 'MEASURED',
                'method':f'Wilson95 descriptive + {cluster_name} cluster percentile bootstrap; bounds retain unknowns'})
        performance=[r for r in selected if r.get('performance_eligible')]
        for field in ['elapsed_ms','action_to_receipt_ms','approval_ms','reservation_ms','tool_ms','finalization_ms']:
            valid=[r for r in performance if r.get(field) is not None and r.get('task_completed')]
            values=[r[field] for r in valid]
            for label,p in [('P50',.5),('P95',.95),('P99',.99)]:
                trials=[dict(r,scenario=r['sample_id']) for r in valid]
                lo,hi=bootstrap(trials,lambda rs:quantile([r[field] for r in rs],p),replicates=replicates)
                output.append({'group':group,'metric':field+'_'+label,'n':len(values),'estimate':quantile(values,p),
                    'ci95_low':lo,'ci95_high':hi,'status':'MEASURED_SMALL_SAMPLE' if 0<len(values)<100 else 'MEASURED' if values else 'NOT_APPLICABLE',
                    'method':'linear quantile; task cluster bootstrap95; repeated calls remain within task; successful actions only' if cluster_name=='task' else 'linear quantile; trial percentile bootstrap95 conditional on this single workload; successful actions only, failures separately'})
            if values:
                for label,value in [('mean',statistics.mean(values)),('stddev',statistics.stdev(values) if len(values)>1 else 0),('max',max(values))]:
                    output.append({'group':group,'metric':field+'_'+label,'n':len(values),'estimate':value,'status':'MEASURED'})
        failure_n=len(performance); failed=sum(not r.get('task_completed') for r in performance)
        value,lo,hi=wilson(failed,failure_n)
        output.append({'group':group,'metric':'performance_failure_rate','k':failed,'n':failure_n,'estimate':value,'ci95_low':lo,'ci95_high':hi,'status':'MEASURED' if failure_n else 'NOT_APPLICABLE'})
        replay_n=sum(r.get('replay_attempts',0) for r in selected)
        output.append({'group':group,'metric':'RSE','n':replay_n,
            'estimate':sum(r.get('duplicate_effects',0) for r in selected) if replay_n else None,'status':'MEASURED' if replay_n else 'NOT_APPLICABLE','method':'actual mailbox count increase after original authorized effect; cached returns are not explicit UBR denials'})
    # Exact matching, never compare different scenarios/trials or silently drop errors.
    for metric,field,eligible in [('TCR','task_completed','task_eligible'),('UER','unauthorized_executions','unauthorized_attempts')]:
        b={r['sample_id']:r for r in rows if r['group']=='B' and r.get(eligible)}
        c={r['sample_id']:r for r in rows if r['group']=='C' and r.get(eligible)}
        unmatched=set(b)!=set(c)
        if unmatched and strict_pairs: raise ValueError('Unpaired B/C samples')
        unknown_field='task_unknown' if metric=='TCR' else 'unauthorized_unknown'
        incomplete=any(r.get(unknown_field,0) for r in [*b.values(),*c.values()])
        paired=[] if incomplete or unmatched else [{'scenario':b[k]['scenario'],'cluster_id':b[k].get('cluster_id'),'difference':c[k].get(field,0)/c[k][eligible]-b[k].get(field,0)/b[k][eligible]} for k in sorted(b)]
        lo,hi=bootstrap(paired,lambda rs:statistics.mean(r['difference'] for r in rs),replicates=replicates)
        output.append({'group':'C-minus-B','metric':metric+'_paired_difference','n':len(paired),
            'estimate':statistics.mean(r['difference'] for r in paired) if paired else None,'ci95_low':lo,'ci95_high':hi,
            'status':'UNPAIRED_ATTEMPTS' if unmatched else 'PARTIAL' if incomplete else 'MEASURED' if paired else 'NOT_APPLICABLE','method':'paired scenario-cluster percentile bootstrap95; no significance claim'})
    if include_cohorts:
        for item in output:
            item['cohort']='performance' if item['metric'].startswith(('elapsed_ms','action_to_receipt_ms','approval_ms','reservation_ms','tool_ms','finalization_ms','performance_failure')) else 'all_applicable'
        shared=[r for r in rows if r['scenario'] in {'document-injection','mail-injection','params-tamper'}]
        matched={g:{r['sample_id'] for r in shared if r['group']==g} for g in ['A','B','C']}
        if not matched['A']==matched['B']==matched['C']: raise ValueError('Unpaired common A/B/C cohort')
        for item in aggregate(shared,replicates,include_cohorts=False,strict_pairs=strict_pairs):
            if item['metric'] in {'UER','UBR','UER_paired_difference'}:
                item['cohort']='shared_tool_policy'
                output.append(item)
    return output


def write_csv(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def export(directory,rows,replicates=1000):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    write_csv(directory/'cases.csv',rows)
    metrics=aggregate(rows,replicates)
    write_csv(directory/'aggregated_metrics.csv',metrics)
    lines=['# ChainGuard protocol replay statistics','',
        '**Real LLM/ASR NOT MEASURED.** These are observed local protocol experiments; not formal LLM A/B/C results.','',
        '| Cohort | Group | Metric | k/n | Estimate | 95% CI |','|---|---|---|---|---|---|']
    for m in metrics:
        if m['metric'] not in {'UER','UBR','ASR','TCR','TDR','FAR','elapsed_ms_P50','elapsed_ms_P95','elapsed_ms_P99','RSE'}: continue
        e=m.get('estimate'); lo=m.get('ci95_low'); hi=m.get('ci95_high')
        lines.append(f"| {m['cohort']} | {m['group']} | {m['metric']} | {m.get('k','')}/{m.get('n',0)} | {e if e is not None else m['status']} | {f'[{lo:.4f}, {hi:.4f}]' if lo is not None else ''} |")
    lines+=['','Compare A/B/C UER and UBR using shared_tool_policy (document/mail target calls and parameter swaps) with identical case IDs and denominators. all_applicable also includes B/C-only approval attempts, so its A versus B/C denominators differ. Wilson intervals are descriptive attempt-level bounds; repeated trials share scenario clusters. Ratio/difference bootstrap resamples whole scenarios. Performance intervals resample trials conditional on the single fixed workload, not unseen tasks. Small sample P99 is exploratory. Failures/timeouts remain in cases.csv and denominators. Latency excludes HTTP/mTLS/model time. A retains account-only enforcement and task-policy shadow; B/C enforce the same frozen business policy. No ASR samples exist. Forgery is not applicable to A; C-only faults have normal A/B controls. TCR checks an exact authorized MIME effect, independent of whether acknowledgement arrived.']
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    return metrics
