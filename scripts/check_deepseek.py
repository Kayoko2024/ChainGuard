"""Real DeepSeek /models and diagnostic Tool Calling preflight. No fake fallback."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'agent/src'), str(ROOT / 'gateway/src'), str(ROOT / 'sandbox_tools/src')]
from chainguard_agent.local_config import load_local_env, redact
from chainguard_agent.model import LLMConfig, NoRedirect
from chainguard_gateway.canonical import parse_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = (args.out or ROOT / 'results/phase8/deepseek' / stamp).resolve()
    if output.exists() or not output.is_relative_to(ROOT / 'results/phase8'):
        raise ValueError('Choose a new results/phase8 output directory')
    output.mkdir(parents=True)
    public = json.loads((ROOT / 'evaluation/deepseek_config.json').read_text())
    secret = ''
    report = {'status': 'RUNNING', 'config': public, 'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'config_sha256': hashlib.sha256((ROOT / 'evaluation/deepseek_config.json').read_bytes()).hexdigest(),
              'api_called': False, 'tool_executed': False, 'real_llm_sample_count': 0,
              'ASR': 'NOT_MEASURED', 'gateway_tasks': 'NOT_STARTED', 'agentdojo': 'NOT_STARTED', 'exchanges': []}
    try:
        report['env_file_loaded'] = load_local_env(ROOT / '.env.local')
        secret = os.environ.get('CHAINGUARD_LLM_API_KEY', '').strip()
        if not secret:
            report.update(status='BLOCKED', code='LLM_API_KEY_MISSING',
                          required_local_path=str(ROOT / '.env.local'))
            return 3
        values = dict(os.environ)
        values.setdefault('CHAINGUARD_LLM_MODEL', public['model'])
        values.setdefault('CHAINGUARD_LLM_BASE_URL', public['base_url'])
        config = LLMConfig.from_env(values)
        if config.model != public['model'] or config.base_url != public['base_url'] or values.get('CHAINGUARD_LLM_PROVIDER', 'deepseek') != 'deepseek':
            raise ValueError('Environment does not match the pinned DeepSeek experiment config')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

        def call(method, path, body=None):
            exchange = {'method': method, 'path': path, 'request': body}
            report['exchanges'].append(exchange)
            report['api_called'] = True
            start = time.perf_counter()
            request = urllib.request.Request(config.base_url + path, None if body is None else json.dumps(body).encode(),
                {'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}, method=method)
            try:
                with opener.open(request, timeout=config.timeout) as response:
                    raw = response.read(1048577)
                    exchange['http_status'] = response.status
                    if len(raw) > 1048576:
                        raise ValueError('Provider response too large')
                    value = parse_json(raw)
                    exchange['response'] = redact(value, secret)
                    return value
            except urllib.error.HTTPError as error:
                exchange['http_status'] = error.code
                exchange['provider_error'] = redact(error.read(8192).decode('utf8', errors='replace'), secret)
                raise RuntimeError('DeepSeek HTTP failure; see redacted preflight evidence') from None
            finally:
                exchange['elapsed_ms'] = (time.perf_counter() - start) * 1000

        call('GET', '/models')
        body = {k: public[k] for k in ['model', 'temperature', 'top_p', 'thinking', 'max_tokens', 'parallel_tool_calls', 'tool_choice']}
        body['messages'] = [{'role': 'user', 'content': 'Call diagnostic_echo once with value ChainGuard connectivity. Do not use any other tool.'}]
        body['tools'] = [{'type': 'function', 'function': {'name': 'diagnostic_echo', 'description': 'Return a diagnostic string; no sensitive side effects.',
                          'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}}, 'required': ['value'], 'additionalProperties': False}}}]
        response = call('POST', '/chat/completions', body)
        report['real_llm_sample_count'] = 1
        message = response['choices'][0]['message']
        calls = message.get('tool_calls') or []
        if message.get('role') != 'assistant' or len(calls) != 1:
            raise ValueError('Real model did not return the required tool call')
        fn = calls[0]['function']
        arguments = parse_json(fn['arguments'].encode())
        if calls[0]['type'] != 'function' or fn['name'] != 'diagnostic_echo' or arguments != {'value': 'ChainGuard connectivity'}:
            raise ValueError('Unexpected real model tool call')
        result = {'echo': arguments['value']}
        report.update(tool_executed=True, actual_tool_result=result, status='PASS',
                      provider_model=response.get('model'), provider_usage=response.get('usage'))
        # Feed the actual tool result back to the model, completing the tool loop.
        follow = dict(body, tool_choice='auto', messages=body['messages'] + [message, {'role': 'tool', 'tool_call_id': calls[0]['id'], 'content': json.dumps(result)}])
        call('POST', '/chat/completions', follow)
        return 0
    except Exception as error:
        report.update(status='FAIL', code=type(error).__name__, message='DeepSeek preflight failed; no simulated fallback')
        return 1
    finally:
        (output / 'preflight.json').write_text(json.dumps(redact(report, secret), indent=2) + '\n', encoding='utf8')
        print(json.dumps({'status': report['status'], 'code': report.get('code'), 'api_called': report['api_called'],
                          'tool_executed': report['tool_executed'], 'output': str(output), 'ASR': 'NOT_MEASURED'}))


if __name__ == '__main__':
    raise SystemExit(main())
