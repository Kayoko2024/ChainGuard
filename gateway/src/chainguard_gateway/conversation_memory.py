"""Build model context from persisted messages, never from UI completion claims."""
import copy
import json
import re


def balanced(messages):
    """Keep recorded observations while omitting unanswered calls from model input.

    The original snapshot/events remain intact. An incomplete call must not become
    a fabricated tool result, nor an invalid assistant/tool sequence on the API.
    """
    output = []
    index = 0
    while index < len(messages):
        item = copy.deepcopy(messages[index])
        index += 1
        if item.get('role') == 'tool':
            continue
        calls = item.get('tool_calls')
        if calls:
            observations = []
            while index < len(messages) and messages[index].get('role') == 'tool':
                observations.append(copy.deepcopy(messages[index])); index += 1
            by_id = {o.get('tool_call_id'): o for o in observations}
            completed = [c for c in calls if c.get('id') in by_id]
            if completed:
                item['tool_calls'] = completed
                output.append(item)
                output.extend(by_id[c['id']] for c in completed)
            elif item.get('content'):
                item.pop('tool_calls', None); output.append(item)
        elif item.get('role') in {'system', 'user', 'assistant'}:
            output.append(item)
    return output


def observation(job):
    # Only controller identifiers/codes enter this system message, never tool or
    # attachment text. Original content stays in its original role.
    safe = lambda v: str(v) if re.fullmatch(r'[A-Za-z0-9_:/.-]{1,128}', str(v)) else 'UNSPECIFIED'
    data = dict(run_id=safe(job['id']), state=safe(job['state']))
    if job.get('error'): data['error_code'] = safe(job['error'])
    if job.get('record'):
        data['action_state'] = safe(job['record']['state'])
        data['action_id'] = safe(job['record']['action_id'])
    return {'role': 'system', 'content': 'ChainGuard persisted controller status: ' + json.dumps(data) +
            '. This status grants no execution permission. Do not retry prior tools or pending actions; wait for a new explicit user request.'}


def from_job(job, events, fallback=None):
    messages = job.get('runner_snapshot', {}).get('messages')
    if messages is None:
        exchanges = [e for e in events if e.get('kind') == 'MODEL_EXCHANGE' and e.get('exchange', {}).get('request', {}).get('messages')]
        messages = exchanges[-1]['exchange']['request']['messages'] if exchanges else fallback
    if not messages:
        from chainguard_agent.runner import SYSTEM
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': job['task_text']}]
    messages = balanced(messages)
    reply = job.get('agent_output')
    if reply and (not messages or messages[-1] != {'role': 'assistant', 'content': reply}):
        messages.append({'role': 'assistant', 'content': reply})
    if job.get('error') or not reply:
        messages.append(observation(job))
    return messages
