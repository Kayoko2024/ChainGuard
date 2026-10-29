"""Build anonymous competition archives from explicit public inputs, never runtime volumes.

Reports and image exports are reviewed separately. This command packages their
bytes without claiming that a private installation is portable or fully rebuilt.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {'.git', '.local', '.venv', 'node_modules', '__pycache__', 'secrets'}
DENIED_SUFFIXES = {'.key', '.pem', '.pfx', '.p12', '.sqlite', '.sqlite3', '.db', '.log'}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def public_name(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and not re.match(r'^[A-Za-z]:', name)
            and '\\' not in name and '..' not in p.parts
            and not set(p.parts) & DENIED_PARTS
            and p.suffix.lower() not in DENIED_SUFFIXES
            and (not p.name.startswith('.env') or p.name.endswith('.example'))
            and not p.name.endswith('.private.json')
            and p.name not in {'access.local.txt', 'runtime.json', 'credentials.json'})


def assert_public(name, raw, secrets=()):
    if not public_name(name):
        raise ValueError('Private or unsafe archive path: ' + name)
    if any(s and s in raw for s in secrets):
        raise ValueError('Private credential found in public input: ' + name)
    if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----', raw):
        raise ValueError('Private PEM material found: ' + name)
    # A generic /Users/ regex in source is fine; an actual developer home is not.
    if re.search(rb'[Cc]:[\\/]+Users[\\/]+HP(?:[\\/]|\b)', raw):
        raise ValueError('Personal home path found: ' + name)


def current_secrets():
    """Read solely for byte comparisons. Never return them in logs/manifests."""
    spec = importlib.util.spec_from_file_location('submission_config', ROOT / 'agent/src/chainguard_agent/local_config.py')
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    env = {}
    config.load_local_env(ROOT / '.env.local', env)
    return [v.encode() for k, v in env.items() if v and ('KEY' in k or 'TOKEN' in k or 'SECRET' in k)]


def source_inputs():
    spec = importlib.util.spec_from_file_location('submission_sources', ROOT / 'scripts/make_source_bundle.py')
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    return {p.relative_to(ROOT).as_posix(): p for p in bundle.sources()}


def inspect_nested(name, raw, secrets):
    """Source history archives keep original hashes; scan, never rewrite them."""
    if name.endswith('.zip'):
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for info in archive.infolist():
                if not info.is_dir():
                    assert_public(info.filename, archive.read(info), secrets)


def archive(path, files, *, secrets=(), root='ChainGuard'):
    path = Path(path)
    if path.exists():
        raise FileExistsError('Refusing to replace a delivery archive')
    manifest = {}
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as output:
        for name, source in sorted(files.items()):
            if source.is_symlink():
                raise ValueError('Symlink input: ' + name)
            # Docker tar files are scanner-reviewed separately and may be large.
            if source.suffix == '.tar':
                if not public_name(name):
                    raise ValueError('Unsafe image export path')
            else:
                raw = source.read_bytes()
                assert_public(name, raw, secrets)
                inspect_nested(name, raw, secrets)
            manifest[name] = sha(source)
            output.write(source, f'{root}/{name}')
        output.writestr(f'{root}/DELIVERY_MANIFEST.json', json.dumps(dict(
            files=manifest, private_runtime_included=False,
            public_fixture_keys_only=True, original_frozen_bytes_preserved=True,
            deployment_limit='Full cold installation is not certified; see running instructions.'),
            ensure_ascii=False, indent=2) + '\n')
    # Streaming reopen verifies bytes, names and ZIP CRC without extracting paths.
    with zipfile.ZipFile(path) as check:
        for name, expected in manifest.items():
            h = hashlib.sha256()
            with check.open(f'{root}/{name}') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != expected:
                raise ValueError('Archive byte mismatch: ' + name)
    return dict(file=path.name, files=len(manifest), bytes=path.stat().st_size, sha256=sha(path))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--runtime-input', type=Path)
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    secrets = current_secrets()
    sources = source_inputs()
    results = [archive(out / '作品源码+ChainGuard.zip', sources, secrets=secrets)]
    if args.runtime_input:
        base = args.runtime_input.resolve()
        files = {p.relative_to(base).as_posix(): p for p in base.rglob('*') if p.is_file()}
        results.append(archive(out / '作品执行文件+ChainGuard.zip', files, secrets=secrets))
    (out / 'archive-validation.json').write_text(json.dumps(dict(status='PASS', archives=results,
        source_files=len(sources), current_key_absent=True, volumes_exported=False),
        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='PASS', archives=results), ensure_ascii=False))


if __name__ == '__main__':
    main()
