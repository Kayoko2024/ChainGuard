"""Create a source-only, checksum-indexed handoff including uncommitted stage10.

Includes an explicit list of public test fixtures; never private runtime material.
Does not claim a clean-OS deployment or create a Git commit.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ['agent', 'chain', 'config', 'console', 'contracts', 'dashboard', 'document_tools', 'docs', 'evaluation', 'gateway', 'sandbox_tools', 'scripts', 'shared', 'spec', 'tests']
SUFFIXES = {'.py','.json','.sol','.cjs','.mjs','.js','.jsx','.css','.html','.md','.txt','.toml','.yaml','.yml','.lock','.ps1','.whl','.zip'}
EXCLUDE = {'node_modules','__pycache__','.venv','dist','build','cache','artifacts','.git','.local','secrets'}
PUBLIC = ['results/phase3/wheels.json','results/phase5/besu-run-01/report.json',
          'results/phase5/besu-run-01/PolicyRegistry.abi.json','results/phase5/besu-run-01/ExecutionRegistry.abi.json',
          'results/phase5/besu-run-01/AuditRegistry.abi.json','results/phase6/run-06/report.json',
          'results/phase8/complete-experiment-01/protocol/case-0000.json',
          'results/phase8/complete-experiment-01/protocol/run_manifest.json']


def sources():
    files = set(ROOT/p for p in PUBLIC)
    for folder in FOLDERS:
        files.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and not (set(p.relative_to(ROOT).parts) & EXCLUDE)
                     and (p.suffix in SUFFIXES or p.name.startswith('Dockerfile') or p.name.endswith('.Dockerfile') or p.name in {'.env.example','.env.local.example'}))
    files.update(ROOT/p for p in ['README.md','AGENTS.md','.gitignore','.gitattributes','.dockerignore',
        '.python-version','.node-version','.env.example','.env.local.example','package.json','package-lock.json',
        'pyproject.toml','requirements-dev.txt','requirements-dev.lock','compose.yaml','hardhat.config.cjs'])
    return sorted(files)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True); args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    files=sources(); hashes={}
    # Compare actual current API key bytes without disclosing it or its digest.
    # Load the existing pure configuration parser without importing AgentRunner
    # or requiring an installed gateway/tool runtime merely to make a source zip.
    spec=importlib.util.spec_from_file_location('bundle_local_config',ROOT/'agent/src/chainguard_agent/local_config.py')
    config=importlib.util.module_from_spec(spec); spec.loader.exec_module(config)
    env={};config.load_local_env(ROOT/'.env.local',env)
    key=env.get('CHAINGUARD_LLM_API_KEY','').encode()
    for file in files:
        assert not file.is_symlink() and file.resolve().is_relative_to(ROOT)
        assert file.name not in {'.env','.env.local'} and file.suffix not in {'.key','.pem'}
        raw=file.read_bytes()
        assert not key or key not in raw, 'Current API key found in public source'
        hashes[file.relative_to(ROOT).as_posix()]=hashlib.sha256(raw).hexdigest()
    path=args.out/'chainguard-source.zip'
    with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
        for name in hashes:
            z.writestr(zipfile.ZipInfo(name), (ROOT/name).read_bytes(),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('SOURCE_MANIFEST.json',json.dumps(hashes,indent=2)+'\n')
    with zipfile.ZipFile(path) as z:
        assert all(hashlib.sha256(z.read(name)).hexdigest()==sha for name,sha in hashes.items())
    result=dict(status='PASS',files=len(hashes),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        private_runtime_included=False,source_includes_uncommitted_files=True,git_commit_created=False,
        current_api_key_absent=True,scope='source handoff only; requires independently provisioned runtimes, chain, signers and dependencies')
    (args.out/'bundle.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8'); print(json.dumps(result))


if __name__=='__main__':main()
