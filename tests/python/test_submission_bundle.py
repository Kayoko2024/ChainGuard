"""Submission packaging must preserve bytes and exclude private material."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('submission', ROOT / 'scripts/prepare_competition_submission.py')
submission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submission)


@pytest.mark.parametrize('name', ['.env.local', 'a/signing.key', '.local/runtime.json', '../outside.txt',
    'C:/private.txt', 'a\\b.txt', 'a/accounts.private.json', 'a/history.sqlite3'])
def test_private_and_traversal_inputs_are_rejected(name):
    with pytest.raises(ValueError):
        submission.assert_public(name, b'anything')


def test_key_and_home_path_rejected_without_disclosing_the_key():
    with pytest.raises(ValueError) as error:
        submission.assert_public('source.txt', b'prefix confidential-value', [b'confidential-value'])
    assert 'confidential-value' not in str(error.value)
    with pytest.raises(ValueError):
        submission.assert_public('source.txt', b'C:/Users/' + b'HP/private')
    with pytest.raises(ValueError):
        submission.assert_public('source.txt', b'-----BEGIN ' + b'PRIVATE KEY-----')


def test_source_archive_preserves_frozen_bytes_reopens_and_refuses_overwrite(tmp_path):
    source = tmp_path / 'spec.json'
    source.write_bytes(b'{"frozen": true}\r\n')
    target = tmp_path / 'source.zip'
    result = submission.archive(target, {'spec/spec.json': source})
    with zipfile.ZipFile(target) as check:
        assert check.read('ChainGuard/spec/spec.json') == source.read_bytes()
        manifest = json.loads(check.read('ChainGuard/DELIVERY_MANIFEST.json'))
        assert manifest['files']['spec/spec.json'] == submission.sha(source)
    assert result['files'] == 1
    with pytest.raises(FileExistsError):
        submission.archive(target, {})


def test_nested_archive_is_scanned_without_mutation(tmp_path):
    source = tmp_path / 'history.zip'
    with zipfile.ZipFile(source, 'w') as output:
        output.writestr('docs/old.md', b'original public bytes')
    before = source.read_bytes()
    submission.inspect_nested('history.zip', before, ())
    assert source.read_bytes() == before
    with zipfile.ZipFile(source, 'w') as output:
        output.writestr('.env.local', b'forbidden')
    with pytest.raises(ValueError):
        submission.inspect_nested('history.zip', source.read_bytes(), ())


def test_template_and_public_vector_are_allowed():
    submission.assert_public('.env.local.example', b'CHAINGUARD_LLM_API_KEY=\n')
    submission.assert_public('spec/vectors/eip712-v1.json', b'{"public_test_key": "fixture"}')
