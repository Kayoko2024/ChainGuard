"""Build the isolated document worker; pin its immutable ID in the local runtime."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--debian-host',choices=['deb.debian.org','mirrors.ustc.edu.cn'],default='mirrors.ustc.edu.cn')
    parser.add_argument('--pypi-index',choices=['https://pypi.org/simple','https://pypi.tuna.tsinghua.edu.cn/simple'],default='https://pypi.tuna.tsinghua.edu.cn/simple');args=parser.parse_args()
    config=args.config.resolve();out=args.out.resolve()
    if not config.is_relative_to(ROOT/'.local/phase10') or out.exists() or not out.is_relative_to(ROOT/'results/documents'):raise ValueError('Use existing private runtime and new document result directory')
    out.mkdir(parents=True);archive=io.BytesIO();hashes={}
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for name in ['document_tools/Dockerfile','document_tools/requirements.txt','document_tools/worker.py']:
            raw=(ROOT/name).read_bytes();info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644;tar.addfile(info,io.BytesIO(raw));hashes[name]=hashlib.sha256(raw).hexdigest()
    prefix=['wsl.exe','-d','Ubuntu','-u','root','--','docker'];image='chainguard/documents:0.10.5'
    with (out/'build.txt').open('wb') as log:
        built=subprocess.run(prefix+['build','--build-arg','DEBIAN_HOST='+args.debian_host,'--build-arg','PYPI_INDEX='+args.pypi_index,'-f','document_tools/Dockerfile','-t',image,'-'],input=archive.getvalue(),stdout=log,stderr=subprocess.STDOUT,timeout=900)
    if built.returncode:raise RuntimeError('Worker image build failed; see build.txt')
    data=json.loads(subprocess.check_output(prefix+['image','inspect',image]))[0];runtime=json.loads(config.read_text(encoding='utf8'))
    for filename,command in [('python-packages.txt',['python','-m','pip','freeze']),('system-packages.txt',['dpkg-query','-W','-f=${Package}=${Version}\n'])]:
        raw=subprocess.check_output(prefix+['run','--rm','--network','none','--read-only','--cap-drop','ALL','--entrypoint',command[0],data['Id'],*command[1:]])
        (out/filename).write_bytes(raw)
    runtime['document_image']=data['Id'];config.write_text(json.dumps(runtime,indent=2)+'\n',encoding='utf8')
    (out/'setup.json').write_text(json.dumps({'status':'PASS','image':data['Id'],'debian_host':args.debian_host,'pypi_index':args.pypi_index,'source_sha256':hashes,'core_containers_changed':False},indent=2)+'\n')
    print('PASS: document worker built and pinned; core containers/volumes unchanged')

if __name__=='__main__':main()
