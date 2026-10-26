import json
from pathlib import Path

import pytest
from chainguard_agent.local_config import load_local_env, redact


def test_local_loader_is_literal_atomic_and_does_not_override_process_key(tmp_path):
    env = {'CHAINGUARD_LLM_API_KEY': 'process-test-secret'}
    path = tmp_path / '.env.local'
    path.write_text('CHAINGUARD_LLM_MODEL=deepseek-flash\nCHAINGUARD_LLM_API_KEY="file-test-secret"\n')
    assert load_local_env(path, env)
    assert env['CHAINGUARD_LLM_API_KEY'] == 'process-test-secret'
    assert env['CHAINGUARD_LLM_MODEL'] == 'deepseek-flash'
    path.write_text('CHAINGUARD_LLM_MODEL=other\nRELAY_KEY=forbidden\n')
    with pytest.raises(ValueError):
        load_local_env(path, env)
    assert env['CHAINGUARD_LLM_MODEL'] == 'deepseek-flash'


def test_missing_file_no_fake_key_and_duplicate_fields_rejected(tmp_path):
    assert load_local_env(tmp_path / 'absent', {}) is False
    p = tmp_path / 'config'
    p.write_text('CHAINGUARD_LLM_API_KEY=one\nCHAINGUARD_LLM_API_KEY=two')
    with pytest.raises(ValueError):
        load_local_env(p, {})


def test_secrets_redacted_from_nested_provider_error_without_mutating_input():
    raw = {'authorization': 'Bearer synthetic-secret', 'data': ['echo synthetic-secret']}
    public = redact(raw, 'synthetic-secret')
    assert 'synthetic-secret' not in json.dumps(public)
    assert raw['authorization'] == 'Bearer synthetic-secret'


def test_pinned_config_and_template_do_not_contain_actual_key():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / 'evaluation/deepseek_config.json').read_text())
    assert config['model'] == 'deepseek-flash' and config['base_url'] == 'https://api.deepseek.com'
    assert config['model_fallback'] is False and config['thinking'] == {'type': 'disabled'}
    template = {}
    load_local_env(root / '.env.local.example', template)
    assert template['CHAINGUARD_LLM_API_KEY'] == ''
