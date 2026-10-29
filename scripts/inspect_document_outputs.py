"""Render synthetic document acceptance outputs in the networkless application image.

Uses the application's private LibreOffice, never the user's desktop installation.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CODE=r'''
import sys,json,base64,pathlib,subprocess,tempfile
v=json.load(sys.stdin)
with tempfile.TemporaryDirectory() as folder:
 p=pathlib.Path(folder)/('source.'+v['extension']);p.write_bytes(base64.b64decode(v['data']))
 if v['extension']!='pdf':
  r=subprocess.run(['/usr/bin/libreoffice','-env:UserInstallation=file://'+folder+'/lo','--headless','--convert-to','pdf','--outdir',folder,str(p)],capture_output=True,timeout=35)
  assert r.returncode==0;p=p.with_suffix('.pdf')
 r=subprocess.run(['/usr/bin/pdftoppm','-scale-to','1400','-png',str(p),folder+'/page'],capture_output=True,timeout=30)
 assert r.returncode==0
 print(json.dumps({'pages':[base64.b64encode(f.read_bytes()).decode() for f in sorted(pathlib.Path(folder).glob('page-*.png'))]}))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();out=a.out.resolve()
    if not source.is_relative_to(ROOT/'results/documents') or not out.is_relative_to(ROOT/'results/documents') or out.exists():raise ValueError('Use synthetic document evidence and new QA output')
    out.mkdir(parents=True);image=json.loads(a.config.read_text(encoding='utf8'))['document_image'];index=[]
    for file in sorted(source.rglob('*')):
        if file.suffix not in {'.doc','.docx','.pdf'}:continue
        value={'extension':file.suffix[1:],'data':base64.b64encode(file.read_bytes()).decode()}
        args=['wsl.exe','-d','Ubuntu','-u','root','--','docker','run','--rm','-i','--network','none','--read-only','--user','10001:10001','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','768m','--pids-limit','96','--tmpfs','/tmp:rw,noexec,nosuid,size=160m,uid=10001,gid=10001','--entrypoint','python',image,'-c',CODE]
        r=subprocess.run(args,input=json.dumps(value).encode(),capture_output=True,timeout=80)
        if r.returncode:raise RuntimeError('Render failed: '+file.name)
        pages=json.loads(r.stdout)['pages'];assert pages
        names=[];name=file.relative_to(source).as_posix().replace('/','-').replace('.','-')
        for i,data in enumerate(pages,1):
            target=out/(name+'-'+str(i)+'.png');target.write_bytes(base64.b64decode(data));names.append(target.name)
        index.append({'file':file.relative_to(source).as_posix(),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'pages':names})
    (out/'render-index.json').write_text(json.dumps({'status':'RENDERED_AWAITING_VISUAL_REVIEW','image':image,'files':index},indent=2)+'\n')
    print('Rendered '+str(len(index))+' real files; inspect every page before marking visual review passed')

if __name__=='__main__':main()
