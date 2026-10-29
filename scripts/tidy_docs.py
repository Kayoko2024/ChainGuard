"""Archive redundant stage narratives byte-for-byte, then remove their loose copies.

Frozen sources and interface contracts are never candidates. Run only as an
explicit repository maintenance operation; --check performs no writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'docs/history.zip'
INDEX = ROOT / 'docs/history-index.json'
NAMES = [*(f'phase{i}-acceptance.md' for i in range(1, 11)),
         *(f'phase{i}-design.md' for i in range(2, 11)),
         'demo-phase9.md', 'demo-phase10.md', 'deepseek-runbook.md',
         'phase10-reservation-troubleshooting.md']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check():
    index = json.loads(INDEX.read_text(encoding='utf8'))
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert set(archive.namelist()) == set(index['files'])
        assert all(sha(archive.read(name)) == digest for name, digest in index['files'].items())
    assert sha(ARCHIVE.read_bytes()) == index['archive_sha256']
    return dict(status='PASS', archived_documents=len(index['files']), remaining_loose_markdown=len(list((ROOT / 'docs').rglob('*.md'))))


def tidy():
    if ARCHIVE.exists() or INDEX.exists():
        raise ValueError('Archive exists; use --check, never overwrite historical originals')
    frozen = set()
    for filename in ['phase0-freeze.json', 'phase3-policy-freeze.json']:
        frozen.update(json.loads((ROOT / 'config' / filename).read_text())['files'])
    candidates = [ROOT / 'docs' / name for name in NAMES]
    # Also preserve the long context logs before replacing them with current state.
    saved = [*candidates, ROOT / 'docs/progress.md', ROOT / 'docs/handoff.md', ROOT / 'README.md']
    originals = {}
    for path in saved:
        resolved = path.resolve(strict=True)
        assert resolved.is_relative_to(ROOT) and not path.is_symlink()
        name = path.relative_to(ROOT).as_posix()
        assert name not in frozen
        originals[name] = path.read_bytes()
    for name in frozen:
        if not name.endswith('.md'):
            continue
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf8')):
            assert (path.parent / target.split('#')[0]).resolve() not in candidates, 'Frozen document references candidate'
    with zipfile.ZipFile(ARCHIVE, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(originals.items()):
            archive.writestr(zipfile.ZipInfo(name), raw, compress_type=zipfile.ZIP_DEFLATED)
    INDEX.write_text(json.dumps(dict(archive_sha256=sha(ARCHIVE.read_bytes()), files={n: sha(v) for n,v in originals.items()}), indent=2) + '\n', encoding='utf8')
    check()
    # Rewrite live navigation before removing verified archived copies.
    all_docs = [ROOT / 'README.md', *(ROOT / 'docs').rglob('*.md'), ROOT / 'evaluation/README.md']
    for path in all_docs:
        if path in candidates or path.relative_to(ROOT).as_posix() in frozen:
            continue
        text = path.read_text(encoding='utf8')
        def replace(match):
            target = match.group(2)
            if '://' in target:
                return match.group(0)
            source = (path.parent / target.split('#')[0]).resolve()
            if source not in candidates:
                return match.group(0)
            import os
            return '[' + match.group(1) + '](' + os.path.relpath(ARCHIVE, path.parent).replace('\\', '/') + ')'
        updated = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace, text)
        if updated != text:
            path.write_text(updated, encoding='utf8', newline='\n')
    for path in candidates:
        # Resolve exact file under docs, verify archive and disk agree before unlink.
        assert path.resolve().is_relative_to((ROOT / 'docs').resolve()) and path.is_file()
        assert path.read_bytes() == originals[path.relative_to(ROOT).as_posix()]
        path.unlink()
    return check()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check() if args.check else tidy()))
