"""Fixed-origin GitHub public GET adapter. No arbitrary URLs, writes, or credentials."""
from datetime import datetime,timezone
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.request
from .canonical import canonical
from chainguard_sandbox.protocol import ToolError

RESOURCE=re.compile(r'([a-z0-9][a-z0-9-]{0,38})/([a-z0-9_][a-z0-9_.-]{0,99})(?:#([1-9][0-9]{0,8}))?\Z')
FIELDS=['resource','kind','repository','title','description','url','state','number','updated_at','stars','open_issues','body']

def resource(value):
    match=RESOURCE.fullmatch(value) if type(value) is str else None
    if not match:raise ToolError('SCHEMA_INVALID')
    owner,repo,issue=match.groups()
    return owner+'/'+repo, int(issue) if issue else None

def output_schema():
    properties={k:{'type':'integer' if k in {'number','stars','open_issues'} else 'string'} for k in FIELDS}
    source={k:{'type':'integer' if k=='http_status' else 'string'} for k in ['url','http_status','fetched_at_utc','response_sha256','github_request_id','api_version','rate_limit_remaining']}
    return {'type':'object','properties':{'record':{'type':'object','properties':properties,'required':FIELDS,'additionalProperties':False},
        'source':{'type':'object','properties':source,'required':list(source),'additionalProperties':False}},'required':['record','source'],'additionalProperties':False}

class GitHubFailure(Exception):
    def __init__(self,code,status=0,*,repository_policy=None):
        self.code,self.status,self.repository_policy=code,status,repository_policy
        super().__init__(code)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch(query,*,opener=None):
    repository,issue=resource(query)
    url='https://api.github.com/repos/'+repository+('/issues/'+str(issue) if issue else '')
    # Deliberately bypass inherited HTTP proxies; endpoint and TLS root checks are fixed.
    opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    request=urllib.request.Request(url,method='GET',headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ChainGuard-public-readonly/0.10'})
    try:
        with opener.open(request,timeout=5) as response:
            if response.status!=200:raise GitHubFailure('GITHUB_HTTP_ERROR',response.status)
            if response.headers.get_content_type()!='application/json':raise GitHubFailure('GITHUB_RESPONSE_INVALID',200)
            raw=response.read(1048577)
            if len(raw)>1048576:raise GitHubFailure('GITHUB_RESPONSE_TOO_LARGE',200)
            value=json.loads(raw)
            if type(value) is not dict:raise GitHubFailure('GITHUB_RESPONSE_INVALID',200)
            expected='https://github.com/'+repository+('/issues/'+str(issue) if issue else '')
            actual=value.get('html_url','').lower()
            # PRs appear on the issues endpoint but are explicitly outside this adapter.
            if value.get('private') is True or 'pull_request' in value or actual!=expected:raise GitHubFailure('GITHUB_RESOURCE_MISMATCH',200)
            if issue is None and (value.get('full_name','').lower()!=repository or value.get('private') is not False):raise GitHubFailure('GITHUB_RESOURCE_MISMATCH',200)
            if issue and value.get('number')!=issue:raise GitHubFailure('GITHUB_RESOURCE_MISMATCH',200)
            def text(key,limit):
                v=value.get(key)
                if v is None:return ''
                if type(v) is not str:raise GitHubFailure('GITHUB_RESPONSE_INVALID',200)
                return v[:limit]
            def number(key):
                v=value.get(key,0)
                if type(v) is not int or not 0<=v<=2**53-1:raise GitHubFailure('GITHUB_RESPONSE_INVALID',200)
                return v
            record={'resource':query,'kind':'issue' if issue else 'repository','repository':repository,
                'title':text('title',500) if issue else text('full_name',200),'description':text('description',1000),
                'url':expected,'state':text('state',30),'number':issue or 0,'updated_at':text('updated_at',50),
                'stars':number('stargazers_count'),'open_issues':number('open_issues_count'),'body':text('body',4000)}
            data={'record':record,'source':{'url':url,'http_status':200,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),
                'response_sha256':hashlib.sha256(raw).hexdigest(),'github_request_id':response.headers.get('X-GitHub-Request-Id',''),
                'api_version':'2022-11-28','rate_limit_remaining':response.headers.get('X-RateLimit-Remaining','')}}
            canonical(data)
            return data,raw
    except urllib.error.HTTPError as error:
        code='GITHUB_RATE_LIMITED' if error.code==429 or error.code==403 and error.headers.get('X-RateLimit-Remaining')=='0' else 'GITHUB_NOT_FOUND' if error.code==404 else 'GITHUB_REDIRECT_REJECTED' if 300<=error.code<400 else 'GITHUB_HTTP_ERROR'
        raise GitHubFailure(code,error.code) from None
    except (OSError,TimeoutError,urllib.error.URLError):raise GitHubFailure('GITHUB_UNAVAILABLE') from None
    except (ValueError,UnicodeError,KeyError,TypeError):raise GitHubFailure('GITHUB_RESPONSE_INVALID') from None
