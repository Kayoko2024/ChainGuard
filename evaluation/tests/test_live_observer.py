"""Only observer selection is unit-tested here; no synthetic experiment samples."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_live_agent import observer_for

ORIGINAL = 'sha256:' + '1' * 64
OBSERVER = 'sha256:' + '2' * 64


@pytest.mark.parametrize('image', ['latest', 'sha256:1234', 'repo:tag', '', '../other', None])
def test_unpinned_observer_is_rejected_before_docker(monkeypatch, image):
    def forbidden(*args, **kwargs):
        pytest.fail('Unpinned input reached Docker')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    with pytest.raises(ValueError, match='full SHA-256'):
        observer_for(['docker'], image)


def test_missing_original_has_no_implicit_fallback(monkeypatch):
    calls = []
    def missing(command, **kwargs):
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(subprocess, 'run', missing)
    with pytest.raises(subprocess.CalledProcessError):
        observer_for(['docker'], ORIGINAL)
    assert calls == [['docker', 'image', 'inspect', ORIGINAL]]


@pytest.mark.parametrize('identity,user', [(ORIGINAL, '10001:10001'), (OBSERVER, '0:0')])
def test_wrong_identity_or_root_observer_is_rejected(monkeypatch, identity, user):
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(
        stdout=json.dumps([{'Id': identity, 'Config': {'User': user}}])))
    with pytest.raises(ValueError, match='mismatch'):
        observer_for(['docker'], ORIGINAL, OBSERVER)


def test_explicit_observer_uses_pinned_identity_without_rewriting_original(monkeypatch):
    calls = []
    def inspect(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps([{'Id': OBSERVER, 'Config': {'User': '10001:10001'}}]))
    monkeypatch.setattr(subprocess, 'run', inspect)
    manifest = {'image': ORIGINAL}
    assert observer_for(['docker'], manifest['image'], OBSERVER) == OBSERVER
    assert manifest == {'image': ORIGINAL}
    assert calls == [['docker', 'image', 'inspect', OBSERVER]]
