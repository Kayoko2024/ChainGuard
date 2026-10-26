"""Recreate the independent, hashed Windows CPython 3.14 benchmark environment."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--download',action='store_true')
    args=parser.parse_args()
    if sys.platform!='win32' or sys.version_info[:2]!=(3,14):
        raise SystemExit('This platform lock is Windows CPython 3.14; generate/review a separate lock for another runtime.')
    lock=json.loads((ROOT/'evaluation/agentdojo.lock.json').read_text())
    artifact=ROOT/lock['artifact']
    assert hashlib.sha256(artifact.read_bytes()).hexdigest()==lock['sha256']
    env=ROOT/'.local/phase7-agentdojo-venv'; wheels=ROOT/'.local/phase7-agentdojo-wheels'
    python=env/'Scripts/python.exe'
    if not python.exists(): subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
    requirements=ROOT/lock['runtime_lock']
    wheels.mkdir(parents=True,exist_ok=True)
    if args.download:
        subprocess.run([str(python),'-m','pip','download','--only-binary=:all:','--require-hashes',
            '--dest',str(wheels),'-r',str(requirements)],check=True)
    subprocess.run([str(python),'-m','pip','install','--no-index','--find-links',str(wheels),
        '--require-hashes','-r',str(requirements)],check=True)
    subprocess.run([str(python),'-m','pip','check'],check=True)
    print('Independent AgentDojo pinned environment ready; gateway environment unchanged.')


if __name__=='__main__': main()
