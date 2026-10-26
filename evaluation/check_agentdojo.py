"""Run original workspace loaders/judges on their in-memory benchmark objects.

This is an adapter compatibility self-test, not an LLM experiment and not real
mail or filesystem deletion. Physical effects are verified by run_phase7.py.
"""
import argparse
from importlib import metadata
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.workspace_adapter import WorkspaceMapper,IncompatibleSample


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--export',type=Path)
    args=parser.parse_args()
    if args.out.exists() or (args.export and args.export.exists()): raise ValueError('Use new evidence/fixture paths')
    from agentdojo.task_suite import get_suite
    from agentdojo.functions_runtime import FunctionCall
    assert metadata.version('agentdojo')=='0.1.35'
    manifest=json.loads((ROOT/'evaluation/agentdojo-upstream-files.json').read_text())
    package=Path(metadata.distribution('agentdojo').locate_file(''))
    for name,expected in manifest.items():
        assert hashlib.sha256((package/name).read_bytes()).hexdigest()==expected,name
    suite=get_suite('v1.2.2','workspace')
    env=suite.load_and_inject_default_environment({})
    mapper=WorkspaceMapper({'mark.black-2134@gmail.com':'bob@inbox.chainguard.invalid'},{k:'ad-file-'+k for k in env.cloud_drive.files})
    mappings=[]; judge_checks=[]
    for task_id in ['injection_task_0','injection_task_1']:
        task=suite.get_injection_task_by_id(task_id)
        calls=task.ground_truth(env)
        assert not task.security('',env,env.model_copy(deep=True))
        post=env.model_copy(deep=True)
        mapped=[]
        for i,call in enumerate(calls):
            call=call.model_copy(update={'id':task_id+'-'+str(i)})
            value=mapper.map(call)
            mapped.append({'call_id':value.id,'tool_name':value.name,'arguments':value.arguments})
            # Official in-memory fixture only, never forwarded to a network or OS.
            if call.function=='send_email': post.inbox.send_email(**call.args)
            elif call.function=='delete_file': post.cloud_drive.delete_file(call.args['file_id'])
        assert task.security('',env,post)
        mappings.append({'task_id':task_id,'goal':task.GOAL,'mapped_trace':mapped,'identity_rebound':True,
            'official_score_for_real_sandbox':None})
        judge_checks.append({'task_id':task_id,'original_judge_negative_control':True,'original_judge_positive_control':True,
            'environment':'OFFICIAL_IN_MEMORY_FIXTURE_ONLY'})
    # Exercise an original file read, not a hand-written stand-in.
    read=mapper.map(FunctionCall(id='official-read',function='get_file_by_id',args={'file_id':'13'}))
    assert read.name=='doc.read' and read.arguments['doc_id']=='ad-file-13'
    incompatible=[]
    for task_id in ['user_task_33','user_task_35','user_task_16']:
        task=suite.get_user_task_by_id(task_id)
        reasons=[]
        for i,call in enumerate(task.ground_truth(env)):
            try:
                m=mapper.map(call.model_copy(update={'id':task_id+'-'+str(i)}))
                if m.name=='doc.delete': reasons.append('C_R3_EXECUTION_NOT_IMPLEMENTED_DEFAULT_DENY')
            except IncompatibleSample as error: reasons.append(str(error))
        assert reasons
        incompatible.append({'task_id':task_id,'prompt':task.PROMPT,'status':'INCOMPATIBLE','reasons':reasons,
            'utility_score':None,'attack_success':None})
    # Check the original utility judge without fabricating successful execution.
    deletion=suite.get_user_task_by_id('user_task_35')
    assert not deletion.utility('',env,env.model_copy(deep=True))
    post=env.model_copy(deep=True); post.cloud_drive.delete_file('11')
    assert deletion.utility('',env,post)
    report={'status':'PASS','agentdojo_version':'0.1.35','benchmark_version':'v1.2.2','suite':'workspace',
        'mode':'adapter_self_test','official_files_sha256_matched':len(manifest),'official_judges_modified':False,
        'llm_sample_count':0,'attack_success':None,'real_llm_attack_test_completed':False,
        'judge_checks':judge_checks,'mapped_attack_goals':mappings,'incompatible':incompatible,
        'note':'Positive controls mutate only official in-memory fixture objects; these are not ChainGuard effects or attack rates.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    if args.export:
        # Retain upstream file content; appended goal text is a local injection
        # fixture, not an official attack implementation or scored benchmark.
        content=env.cloud_drive.files['13'].content
        fixture={'mode':'fixed_trace','provenance':{'agentdojo':'0.1.35','benchmark':'v1.2.2','file_id':'13',
            'goals':['injection_task_0','injection_task_1'],'original_content_sha256':hashlib.sha256(content.encode()).hexdigest(),
            'attack_text_source':'locally composed from original GOAL strings','official_score':None},
            'documents':[{'doc_id':'ad-file-13','source_kind':'document','content':content+'\nUNTRUSTED INJECTION:\n'+'\n'.join(m['goal'] for m in mappings)}],
            'cases':[{'case_id':'agentdojo-goal-replay','source':'ad-file-13','attack_id':'agentdojo-goals-0-1',
                'mapped_attacks':[c for m in mappings for c in m['mapped_trace']]}],
            'authorized_mail':{'to':['alice@inbox.chainguard.invalid'],'subject':'ChainGuard phase7 authorized summary',
                'body':'Synthetic report summary: revenue is stable.'}}
        args.export.parent.mkdir(parents=True,exist_ok=True)
        args.export.write_text(json.dumps(fixture,indent=2)+'\n',encoding='utf8')
    print('AgentDojo official loaders/judges and workspace adapter compatibility PASS; no LLM experiment.')


if __name__=='__main__': main()
