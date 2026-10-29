"""Real isolated document effects and optional real DeepSeek web acceptance.

Uses new private state and synthetic fixtures; never sends email or changes contracts.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'gateway/src'),str(ROOT/'sandbox_tools/src'),str(ROOT/'agent/src')]
from chainguard_gateway.document_tools import DocumentSandbox,DocumentLibrary
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.crypto import random_id
from chainguard_agent.model import ToolCall
from chainguard_sandbox.protocol import ToolError

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--web',action='store_true');parser.add_argument('--web-source',choices=['docx','pdf'],default='docx');a=parser.parse_args()
    out=a.out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'results/documents'):raise ValueError('New document results directory required')
    out.mkdir(parents=True);config=json.loads(a.config.read_text(encoding='utf8'));worker=DocumentSandbox(config.get('document_image'))
    private=ROOT/'.local/documents'/secrets.token_hex(12);store=OperationsStore(private);library=DocumentLibrary(store,worker)
    report={'status':'RUNNING','worker_image':worker.image,'synthetic_data':True,'mail_execution_in_scope':False,'chain_transactions_in_scope':False,'checks':[]};server=None
    def save():(out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    def make(format,content):
        task=random_id()
        return worker({'op':'tool','task_id':task,'tool':'document.create','scope':{'task_id':task,'expires_at':int(time.time())+300,'tools':['document.create'],'attachment_ids':[],'allow_create':True},'arguments':{'title':'附件验收计划','format':format,'content':content}})
    try:
        save(); fixtures={}
        prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
        worker_test=prefix+['run','--rm','-i','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','768m','--pids-limit','96','--tmpfs','/tmp:rw,noexec,nosuid,size=160m,mode=0700,uid=10001,gid=10001','--entrypoint','python',worker.image,'-c','import sys;exec(sys.stdin.read())']
        checked=subprocess.run(worker_test,input=(ROOT/'document_tools/test_worker.py').read_bytes(),capture_output=True,timeout=120)
        (out/'worker-tests.txt').write_bytes(checked.stdout+checked.stderr);assert checked.returncode==0,'Worker tests failed'
        report['worker_tests']='4 PASS'
        content='项目负责人：Alice\n预算：1000 元\n下一步：核验真实文档副本。'
        for ext in ['docx','pdf']:
            source_content=content
            if ext=='pdf' and a.web_source=='pdf':
                source_content+='\n'+'\n'.join(f'第{i:02d}条验收要求：核对数据来源与授权范围，保留实际读取位置和原始文件摘要，生成完整文档副本后再检查下载结果。' for i in range(1,41))
            generated=make(ext,source_content);raw=base64.b64decode(generated['content_base64']);(out/('source.'+ext)).write_bytes(raw)
            id=random_id();library.upload(id,'source.'+ext,raw);fixtures[ext]=id
        # Legacy .doc fixture uses the worker's own LibreOffice, with the same isolation.
        prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker']
        code="import sys,base64,tempfile,subprocess,pathlib; p=pathlib.Path('/tmp/source.docx');p.write_bytes(sys.stdin.buffer.read());r=subprocess.run(['/usr/bin/libreoffice','-env:UserInstallation=file:///tmp/lo-profile','--headless','--convert-to','doc','--outdir','/tmp',str(p)],capture_output=True);assert r.returncode==0;sys.stdout.buffer.write(pathlib.Path('/tmp/source.doc').read_bytes())"
        cmd=prefix+['run','--rm','-i','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','768m','--pids-limit','96','--tmpfs','/tmp:rw,noexec,nosuid,size=160m,uid=10001,gid=10001','--entrypoint','python',worker.image,'-c',code]
        legacy=subprocess.run(cmd,input=(out/'source.docx').read_bytes(),capture_output=True,timeout=70)
        assert legacy.returncode==0,'Legacy fixture conversion failed'
        (out/'source.doc').write_bytes(legacy.stdout);id=random_id();library.upload(id,'source.doc',legacy.stdout);fixtures['doc']=id
        for ext,id in fixtures.items():
            task=random_id();store.create(task,{'document_scope':{'attachment_ids':[id],'allow_create':True},'grant':{'expires_at':str(int(time.time())+600)}});store.update(task,state='AGENT_RUNNING')
            read=library.execute(task,ToolCall('read','attachment.read',{'source_id':id,'start':0,'limit':10}))
            assert any('Alice' in u['text'] for u in read['data']['units'])
            format='pdf' if ext=='pdf' else 'docx';call=ToolCall('edit','document.revise',{'source_id':id,'title':'验收修订副本','format':format,'find':'Alice','replace':'Bob'})
            edited=library.execute(task,call);assert library.execute(task,call)==edited
            artifact=library.get(edited['data']['id']);raw=base64.b64decode(artifact['content_base64']);(out/('revised-'+ext+'.'+format)).write_bytes(raw)
            parsed=worker({'op':'extract','extension':format,'content_base64':artifact['content_base64']})
            assert any('Bob' in u['text'] for u in parsed['units']) and not any('Alice' in u['text'] for u in parsed['units'])
            assert library.get(id)['sha256']==hashlib.sha256((out/('source.'+ext)).read_bytes()).hexdigest()
            assert len(library.files_for(store.get(task))['artifacts'])==1
            report['checks'].append({'format':ext,'read_units':len(read['data']['units']),'source_sha256':library.get(id)['sha256'],'output_sha256':artifact['sha256'],'original_unchanged':True,'duplicate_output_count':1})
        # Active content, malformed archives, spoofed extensions, encrypted PDFs and OCR.
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,'w') as z:
            z.writestr('[Content_Types].xml','x');z.writestr('word/document.xml','x');z.writestr('word/vbaProject.bin',b'x')
        failures=[]
        for name,raw in [('bad.docx',bad.getvalue()),('fake.pdf',b'not a PDF'),('empty.txt',b'\x00bad'),('../host.txt',b'x')]:
            try:library.upload(random_id(),name,raw)
            except ToolError as error:failures.append(error.code)
            else:raise AssertionError('Invalid document accepted')
        report['rejected_inputs']=failures
        scope_task=random_id();store.create(scope_task,{'document_scope':{'attachment_ids':[],'allow_create':False},'grant':{'expires_at':str(int(time.time())+600)}});store.update(scope_task,state='AGENT_RUNNING')
        for call in [ToolCall('leak','attachment.read',{'source_id':fixtures['docx'],'start':0,'limit':1}),ToolCall('write','document.create',{'title':'Denied','format':'pdf','content':'Denied'})]:
            try:library.execute(scope_task,call)
            except ToolError as error:assert error.code=='UNAUTHORIZED_SCOPE'
            else:raise AssertionError('Missing scope was not rejected')
        report['scope_rejected_without_output']=library.files_for(store.get(scope_task))['artifacts']==[]
        if a.web:
            # Independent web state; original core containers and credentials remain untouched.
            runtime_dir=ROOT/'.local/phase10'/('documents-'+secrets.token_hex(8));runtime_dir.mkdir(parents=True)
            config.update(private_root=str(runtime_dir/'private'),public_db=str(runtime_dir/'public.sqlite3'),port=8092)
            runtime=runtime_dir/'runtime.json';runtime.write_text(json.dumps(config),encoding='utf8')
            (runtime_dir/'access.local.txt').write_bytes((a.config.parent/'access.local.txt').read_bytes())
            logfile=(runtime_dir/'server.log').open('wb')
            import os
            env=dict(os.environ,PYTHONUTF8='1',PYTHONPATH=';'.join(str(ROOT/p) for p in ['gateway/src','sandbox_tools/src','agent/src']))
            server=subprocess.Popen([sys.executable,'-m','chainguard_gateway.phase10_api','--config',str(runtime)],cwd=ROOT,env=env,stdout=logfile,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            for _ in range(60):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8092/health/live',timeout=1) as response:assert response.status==200
                    break
                except OSError:time.sleep(.5)
            else:raise RuntimeError('Temporary web not ready')
            done=subprocess.run(['node',str(ROOT/'console/tests/document-browser.mjs'),str(runtime),str(out/'browser'),str(out/('source.'+a.web_source))],cwd=ROOT,capture_output=True,timeout=360)
            (out/'browser-command.txt').write_bytes(done.stdout+done.stderr)
            assert done.returncode==0,'Real browser/DeepSeek test failed; see browser evidence'
            for ext in ['docx','pdf']:
                parsed=worker({'op':'extract','extension':ext,'content_base64':base64.b64encode((out/'browser'/('model-output.'+ext)).read_bytes()).decode()})
                text='\n'.join(u['text'] for u in parsed['units'])
                assert ('Alice' if a.web_source=='pdf' else 'Bob') in text and '1000' in text
                if ext=='docx':
                    if a.web_source=='pdf':assert all(f'第{i:02d}条' in text for i in range(1,41))
                    else:assert 'Alice' not in text
            from chainguard_gateway.phase10_store import PublicStore
            from chainguard_gateway.phase10_audit import verify_live_entry
            observed=json.loads((out/'browser/browser.json').read_text(encoding='utf8'))
            entry=next(e for e in PublicStore(config['public_db']).actions() if e['sample_id']==observed['task_id'])
            assert entry['state']=='DOCUMENT_COMPLETED' and entry['risk']==1
            assert verify_live_entry(None,entry)['status']=='LOCAL_DOCUMENT_OBSERVATION'
            from chainguard_gateway.phase10_bridge import DockerBridge
            test_job=OperationsStore(config['private_root']).get(observed['task_id'])
            assert not [r for r in DockerBridge(config).snapshot() if r['task_id']==test_job['grant']['task_id']]
            report['live_public_audit']={'status':'LOCAL_DOCUMENT_OBSERVATION','risk':entry['risk'],'document_events':len(entry['read_observations']),'high_risk_gateway_actions_for_task':0}
            report['real_model_web']='PASS';report['private_runtime']=str(runtime.relative_to(ROOT))
        report['status']='PASS';save();print('PASS: real document parsing, DOC conversion, copy edits, idempotency, scope and optional DeepSeek web')
    except Exception as error:report.update(status='FAIL',error_type=type(error).__name__,error=str(error));save();raise
    finally:
        if server:server.terminate();server.wait(timeout=20);logfile.close()

if __name__=='__main__':main()
