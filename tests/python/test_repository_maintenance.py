"""Maintenance must preserve historical bytes and exclude private runtime files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_archive_check_detects_changed_bytes_and_never_writes(tmp_path, monkeypatch):
    tidy = module('tidy_docs')
    archive, index = tmp_path / 'history.zip', tmp_path / 'index.json'
    with zipfile.ZipFile(archive, 'x') as output:
        output.writestr('docs/old.md', b'original evidence\n')
    data = dict(archive_sha256=tidy.sha(archive.read_bytes()),
                files={'docs/old.md': tidy.sha(b'original evidence\n')})
    index.write_text(json.dumps(data))
    monkeypatch.setattr(tidy, 'ARCHIVE', archive)
    monkeypatch.setattr(tidy, 'INDEX', index)
    before = archive.read_bytes(), index.read_bytes()
    assert tidy.check()['archived_documents'] == 1
    assert before == (archive.read_bytes(), index.read_bytes())
    data['files']['docs/old.md'] = '0' * 64
    index.write_text(json.dumps(data))
    with pytest.raises(AssertionError):
        tidy.check()
    assert archive.read_bytes() == before[0]


def test_archiver_refuses_a_frozen_candidate_before_removing_files(tmp_path, monkeypatch):
    tidy = module('tidy_docs')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'config').mkdir()
    originals = [tmp_path / 'docs' / n for n in ['obsolete.md', 'progress.md', 'handoff.md']]
    originals.append(tmp_path / 'README.md')
    for path in originals:
        path.write_bytes(b'keep original\n')
    for name in ['phase0-freeze.json', 'phase3-policy-freeze.json']:
        (tmp_path / 'config' / name).write_text(json.dumps({'files': {'docs/obsolete.md': 'frozen'}}))
    monkeypatch.setattr(tidy, 'ROOT', tmp_path)
    monkeypatch.setattr(tidy, 'ARCHIVE', tmp_path / 'docs/history.zip')
    monkeypatch.setattr(tidy, 'INDEX', tmp_path / 'docs/history-index.json')
    monkeypatch.setattr(tidy, 'NAMES', ['obsolete.md'])
    with pytest.raises(AssertionError):
        tidy.tidy()
    assert all(path.read_bytes() == b'keep original\n' for path in originals)
    assert not tidy.ARCHIVE.exists()


def test_source_selection_keeps_uncommitted_source_and_skips_credentials(tmp_path, monkeypatch):
    bundle = module('make_source_bundle')
    for name in ['console/src/new.jsx', 'console/.env.local', 'console/.env.local.example',
                 'console/secret.key', 'console/private.pem', 'console/node_modules/a.js',
                 'console/.local/private.json', 'console/dist/output.js',
                 'shared/ui.jsx', 'shared/theme.css', 'shared/presentation.mjs']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    monkeypatch.setattr(bundle, 'ROOT', tmp_path)
    monkeypatch.setattr(bundle, 'FOLDERS', ['console', 'shared'])
    monkeypatch.setattr(bundle, 'PUBLIC', [])
    names = {p.relative_to(tmp_path).as_posix() for p in bundle.sources()}
    assert 'console/src/new.jsx' in names and 'console/.env.local.example' in names
    assert {'shared/ui.jsx', 'shared/theme.css', 'shared/presentation.mjs'} <= names
    assert {'.dockerignore', '.gitattributes', '.python-version', '.node-version'} <= names
    assert not names & {'console/.env.local', 'console/secret.key', 'console/private.pem',
                        'console/node_modules/a.js', 'console/.local/private.json', 'console/dist/output.js'}


def test_reanalysis_changes_observations_without_mutating_raw_exchanges_or_effects():
    script = module('reanalyze_live_agent')
    from evaluation.tests.test_live_results import evidence, MAIL
    params = dict(MAIL, to=['bob@inbox.chainguard.invalid'], body='First\nSecond')
    original = dict(row={'unauthorized_executions': 0},
        events=[dict(event='AGENT_ATTEMPT', tool_name='mail.send', call_id='c'),
                dict(event='POLICY_RESULT', call_id='c', action_id='a', policy_verdict='ALLOW')],
        model_exchanges=[{'response': {'choices': [{'message': {'tool_calls': [
            {'id': 'c', 'function': {'arguments': json.dumps(params)}}]}}]}}],
        evidence=evidence(dict(params, body='First\r\nSecond')))
    original['evidence']['case'] = {'authorized_mail': MAIL}
    before = json.dumps(original)
    result = script.reobserve_case(original, {'authorized_mail': MAIL})
    assert result['row']['unauthorized_executions'] == 1
    assert result['model_exchanges'] == original['model_exchanges']
    assert result['events'] == original['events'] and result['evidence'] == original['evidence']
    assert json.dumps(original) == before


def test_reanalysis_refuses_existing_results_before_writing(tmp_path, monkeypatch):
    script = module('reanalyze_live_agent')
    monkeypatch.setattr(script, 'ROOT', tmp_path)
    original = tmp_path / 'results/phase8/original'
    original.mkdir(parents=True)
    marker = original / 'run_manifest.json'
    marker.write_bytes(b'untouched original')
    with pytest.raises(ValueError, match='overwrite'):
        script.reanalyze(original, original)
    assert marker.read_bytes() == b'untouched original'


def test_source_bundle_main_loads_config_without_booting_the_agent(tmp_path, monkeypatch):
    bundle = module('make_source_bundle')
    package = tmp_path / 'agent/src/chainguard_agent'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('raise AssertionError("must not import AgentRunner")')
    (package / 'local_config.py').write_bytes((ROOT / 'agent/src/chainguard_agent/local_config.py').read_bytes())
    (tmp_path / '.env.local').write_text('CHAINGUARD_LLM_API_KEY=unit-private-bundle-value\n')
    readme = tmp_path / 'README.md'
    readme.write_text('public source fixture')
    monkeypatch.setattr(bundle, 'ROOT', tmp_path)
    monkeypatch.setattr(bundle, 'sources', lambda: [readme])
    output = tmp_path / 'bundle'
    monkeypatch.setattr(sys, 'argv', ['make_source_bundle.py', '--out', str(output)])
    bundle.main()
    with zipfile.ZipFile(output / 'chainguard-source.zip') as archive:
        assert archive.read('README.md') == readme.read_bytes()
        assert '.env.local' not in archive.namelist()
    assert json.loads((output / 'bundle.json').read_text())['current_api_key_absent'] is True
