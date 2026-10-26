"""Replaceable model boundary, independent of authorization and tool execution."""
from dataclasses import dataclass,field
import ipaddress
import json
import os
import time
from typing import Protocol
from urllib.parse import urlsplit
import urllib.request
import urllib.error

from chainguard_gateway.canonical import parse_json
from chainguard_sandbox.protocol import ToolError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        # An endpoint redirect must never forward model credentials elsewhere.
        raise ValueError('Model endpoint redirects are disabled')

ALIASES={'doc_read':'doc.read','mail_send':'mail.send','doc_delete':'doc.delete'}


@dataclass(frozen=True)
class ToolCall:
    id:str
    name:str
    arguments:dict


@dataclass(frozen=True)
class Turn:
    content:str=''
    calls:tuple[ToolCall,...]=()


class ModelBackend(Protocol):
    mode:str
    def next_turn(self,messages:list[dict],tools:list[dict])->Turn: ...


@dataclass(frozen=True)
class LLMConfig:
    model:str
    base_url:str
    api_key:str=field(repr=False)
    timeout:int=30

    @classmethod
    def from_env(cls,environ=None):
        values=os.environ if environ is None else environ
        model=values.get('CHAINGUARD_LLM_MODEL','').strip()
        base=values.get('CHAINGUARD_LLM_BASE_URL','').rstrip('/')
        key=values.get('CHAINGUARD_LLM_API_KEY','')
        if not model or not base or not key: raise ValueError('LLM model, base URL and API key must be configured independently')
        parsed=urlsplit(base)
        local=parsed.hostname=='localhost'
        try: local=local or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError: pass
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname or parsed.scheme not in {'https','http'} or parsed.scheme=='http' and not local:
            raise ValueError('Use HTTPS, or explicit loopback HTTP for a local model')
        timeout=int(values.get('CHAINGUARD_LLM_TIMEOUT_SECONDS','30'))
        if not 1<=timeout<=120: raise ValueError('Invalid model timeout')
        return cls(model,base,key,timeout)

    def public(self):
        return {'model':self.model,'base_url':self.base_url,'timeout_seconds':self.timeout,'api_key_configured':bool(self.api_key)}


class HTTPModelBackend:
    """Chat Completions tool-call boundary for configured API/local models.

    This module never approves, signs, reserves or executes sensitive tools.
    The optional recorder receives redacted exchanges, including HTTP failures.
    """
    mode='real_llm'
    def __init__(self,config,*,parameters=None,recorder=None):
        self.config,self.parameters,self.recorder=config,dict(parameters or {}),recorder
        if set(self.parameters)-{'temperature','top_p','thinking','max_tokens','tool_choice'}:
            raise ValueError('Only explicit sampling/thinking parameters may extend model requests')

    def next_turn(self,messages,tools):
        body={'model':self.config.model,'messages':messages,'tools':tools,'parallel_tool_calls':False,'temperature':0}
        body.update(self.parameters)
        request=urllib.request.Request(self.config.base_url+'/chat/completions',json.dumps(body).encode(),
            {'Content-Type':'application/json','Authorization':'Bearer '+self.config.api_key})
        started=time.perf_counter()
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request,timeout=self.config.timeout) as response:
                raw=response.read(1048577)
                if len(raw)>1048576: raise ValueError()
                value=json.loads(raw)
            message=value['choices'][0]['message']
            if self.recorder:
                from .local_config import redact
                self.recorder(redact({'request':body,'response':value,'http_status':200,'elapsed_ms':(time.perf_counter()-started)*1000},self.config.api_key))
            if message['role']!='assistant': raise ValueError()
            calls=[]
            for raw in message.get('tool_calls') or []:
                if raw['type']!='function': raise ValueError()
                fn=raw['function']
                args=parse_json(fn['arguments'].encode())
                calls.append(ToolCall(raw['id'],ALIASES.get(fn['name'],fn['name']),args))
            return Turn(message.get('content') or '',tuple(calls))
        except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
            if self.recorder:
                from .local_config import redact
                failure={'request':body,'error_type':type(error).__name__,
                         'http_status':getattr(error,'code',None),'elapsed_ms':(time.perf_counter()-started)*1000}
                if isinstance(error,urllib.error.HTTPError):
                    failure['provider_error']=error.read(8192).decode('utf8',errors='replace')
                self.recorder(redact(failure,self.config.api_key))
            raise ToolError('EXECUTION_UNKNOWN') from None


def configured_backend(mode,*,steps=None,environ=None):
    """Swapping models does not change the proxy, task grants or gateway APIs."""
    if mode=='fixed_trace':
        from .runner import FixedTraceBackend
        if steps is None: raise ValueError('Explicit trace required')
        return FixedTraceBackend(steps)
    if mode=='real_llm': return HTTPModelBackend(LLMConfig.from_env(environ))
    raise ValueError('Explicit backend selection required')
