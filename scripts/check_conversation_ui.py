"""Restore completed real conversation in a new web process; read-only business acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('New output directory required')
    a.out.mkdir(parents=True);source=json.loads((a.source/'smoke.json').read_text());web=json.loads((a.source/'browser/browser.json').read_text());assert source['status']==web['status']=='PASS'
    runtime=Path(source['private_runtime']);c=json.loads(runtime.read_text());env=dict(os.environ,PYTHONPATH=os.pathsep.join(str(ROOT/q) for q in ['gateway/src','sandbox_tools/src','agent/src']),PYTHONUTF8='1')
    def durable_snapshot():
        snapshots={}
        uri='file:'+(Path(c['private_root'])/'operations.sqlite3').as_posix()+'?mode=ro'
        with sqlite3.connect(uri,uri=True) as db:
            for table in ['jobs','events','conversations','conversation_runs']:
                rows=db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                encoded=json.dumps([[v.hex() if isinstance(v,bytes) else v for v in row] for row in rows],ensure_ascii=False,separators=(',',':')).encode()
                snapshots[table]=dict(rows=len(rows),sha256=hashlib.sha256(encoded).hexdigest())
        return snapshots
    before=durable_snapshot()
    with (a.out/'server.txt').open('wb') as log:
        process=subprocess.Popen([sys.executable,'-m','chainguard_gateway.phase10_api','--config',str(runtime)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(60):
                try:opener.open(f"http://127.0.0.1:{c['port']}/health/live",timeout=1);break
                except Exception:time.sleep(.3)
            with (a.out/'browser.txt').open('wb') as browser_log:
                r=subprocess.run(['node','console/tests/session-memory-readonly.mjs',str(runtime),str(a.config.resolve()),str((a.out/'browser').resolve()),web['session_id']],cwd=ROOT,env=env,stdout=browser_log,stderr=subprocess.STDOUT,timeout=90)
            if r.returncode:raise RuntimeError('Read-only browser check failed; evidence retained')
        finally:process.terminate();process.wait(timeout=10)
    after=durable_snapshot()
    evidence=dict(status='PASS' if before==after else 'FAIL',before=before,after=after,new_model_calls=0,new_tool_calls=0,new_tasks=0)
    (a.out/'persistence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf8')
    if before!=after:raise AssertionError('Persisted conversation changed during read-only browser verification')
    print('PASS: real web-process restart, persisted conversation, LOW root, responsive layout; no new task/model/tool')

if __name__=='__main__':main()
