"""Versioned, reviewed HTTP query/inference profiles, separate from R2/R3 tools."""
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit
from .canonical import canonical
from chainguard_sandbox.protocol import ToolError

FIELDS=['profile','response']
SECRET=re.compile(r'(^|_)(authorization|password|secret|token|api_?key|access_?key)($|_)',re.I)


def endpoint(value):
    if type(value) is not str or not 1<=len(value)<=1000 or any(ord(c)<33 or ord(c)>126 for c in value) or any(c in value for c in ['\\','%','?','#']):
        raise ToolError('SCHEMA_INVALID')
    try:
        p=urlsplit(value);host=p.hostname
        if p.scheme!='https' or p.username or p.password or p.port not in {None,443} or not host or p.netloc!=host or host!=host.lower():raise ValueError()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or '.' not in host or len(host)>253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.')):raise ValueError()
        try:ipaddress.ip_address(host)
        except ValueError:pass
        else:raise ToolError('HTTP_TARGET_DENIED')
        if host.endswith(('.localhost','.local','.internal','.home','.lan','.test','.invalid')) or host in {'github.com','api.github.com'} or host.endswith('.github.com'):
            raise ToolError('HTTP_TARGET_DENIED')
        if any(part in {'.','..'} for part in p.path.split('/')):raise ValueError()
    except ValueError:raise ToolError('SCHEMA_INVALID') from None
    return p


def safe_json(value,depth=0):
    if depth>6:raise ToolError('SCHEMA_INVALID')
    if type(value) is dict:
        if len(value)>32:raise ToolError('SCHEMA_INVALID')
        for key,item in value.items():
            if type(key) is not str or not 1<=len(key)<=64 or SECRET.search(key):raise ToolError('HTTP_CREDENTIALS_FORBIDDEN')
            safe_json(item,depth+1)
    elif type(value) is list:
        if len(value)>32:raise ToolError('SCHEMA_INVALID')
        for item in value:safe_json(item,depth+1)
    elif type(value) not in {str,int,bool,type(None)} or type(value) is int and abs(value)>2**53-1 or type(value) is str and len(value)>4000:
        raise ToolError('SCHEMA_INVALID')


def prepare_http(value,version):
    from .custom_tools import is_custom
    fields={'name','label','description','adapter','risk','key_field','output_fields','records','http'}
    if type(value) is not dict or set(value)!=fields:raise ToolError('SCHEMA_INVALID')
    if not is_custom(value['name']) or value['adapter']!='http.request' or type(value['risk']) is not int or value['risk']!=1:raise ToolError('POLICY_DENY')
    if any(type(value[k]) is not str or not 1<=len(value[k])<=limit for k,limit in [('label',60),('description',500)]):raise ToolError('SCHEMA_INVALID')
    h=value['http']
    if type(h) is not dict or set(h)!={'url','method','purpose'} or h['method'] not in ('GET','POST') or h['purpose']!='query_or_inference':raise ToolError('POLICY_DENY')
    endpoint(h['url'])
    if value['key_field']!='profile' or value['output_fields']!=FIELDS:raise ToolError('SCHEMA_INVALID')
    rows=value['records']
    if type(rows) is not list or not 1<=len(rows)<=20:raise ToolError('SCHEMA_INVALID')
    for row in rows:
        if type(row) is not dict or set(row)!={'profile','query','body'}:raise ToolError('SCHEMA_INVALID')
        if type(row['profile']) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',row['profile']):raise ToolError('SCHEMA_INVALID')
        if type(row['query']) is not dict or any(type(v) not in {str,int,bool} for v in row['query'].values()):raise ToolError('SCHEMA_INVALID')
        if h['method']=='GET' and row['body'] is not None or h['method']=='POST' and type(row['body']) is not dict:raise ToolError('SCHEMA_INVALID')
        safe_json(row['query']);safe_json(row['body'])
    if len({r['profile'] for r in rows})!=len(rows) or len(canonical(value))>32768:raise ToolError('SCHEMA_INVALID')
    if type(version) is not int or not 1<=version<=1000000:raise ToolError('SCHEMA_INVALID')
    result={k:v for k,v in value.items() if k!='records'}
    source={k:{'type':'integer' if k=='http_status' else 'string'} for k in ['url','method','http_status','fetched_at_utc','response_sha256','request_sha256']}
    result.update(version=version,schema_version=1,dataset_sha256=hashlib.sha256(canonical(rows)).hexdigest(),
        input_schema={'type':'object','properties':{'query':{'type':'string','enum':[r['profile'] for r in rows]}},'required':['query'],'additionalProperties':False},
        output_schema={'type':'object','properties':{'record':{'type':'object','properties':{'profile':{'type':'string'},'response':{'type':'string','maxLength':16000}},'required':FIELDS,'additionalProperties':False},
            'source':{'type':'object','properties':source,'required':list(source),'additionalProperties':False}},'required':['record','source'],'additionalProperties':False})
    result['revision']='0x'+hashlib.sha256(canonical(result)).hexdigest()
    return result


class HTTPFailure(Exception):
    def __init__(self,code):self.code=code;super().__init__(code)
