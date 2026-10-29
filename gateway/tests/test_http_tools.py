"""Contract/transport fixtures. Not model, blockchain or external-API evidence."""
import copy
import hashlib
import json
import socket
import sqlite3
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.canonical import canonical
from chainguard_gateway.custom_tools import prepare,validate_manifest,ToolRegistry,check_grants,descriptor
from chainguard_gateway.http_tools import HTTPFailure,endpoint
from chainguard_gateway.http_reader import create_app,public_addresses,fetch
from chainguard_gateway.phase10_store import OperationsStore
from chainguard_gateway.phase10_audit import verify_live_entry
from chainguard_sandbox.protocol import ToolError


def registration():
    return dict(name='custom.vision_query',label='Vision',description='Read image labels from approved API.',adapter='http.request',risk=1,
        key_field='profile',output_fields=['profile','response'],http={'url':'https://vision.example.com/recognize','method':'POST','purpose':'query_or_inference'},
        records=[{'profile':'photo','query':{'lang':'zh'},'body':{'image_url':'https://images.example.com/demo.png'}}])


def test_version_binds_endpoint_method_and_params_without_changing_original_contract(tmp_path):
    value=registration();m=prepare(value,1);validate_manifest(m,value['records'])
    for change in [dict(http=dict(value['http'],url='https://other.example.com/query')),dict(http=dict(value['http'],method='GET'),records=[dict(value['records'][0],body=None)]),dict(records=[dict(value['records'][0],body={'image_url':'different'})])]:
        assert prepare(dict(value,**change),1)['revision']!=m['revision']
    registry=ToolRegistry(OperationsStore(tmp_path));item=registry.create(value);rev=item['manifest']['revision']
    grant={'name':value['name'],'revision':rev,'allowed_keys':['photo']}
    with pytest.raises(ToolError,match='POLICY_REVOKED'):check_grants([grant],[value['name']],registry.get)
    registry.state(rev,'ACTIVE');assert check_grants([grant],[value['name']],registry.get)
    new=registry.create(dict(value,http=dict(value['http'],url='https://other.example.com/query')),rev)
    assert new['state']=='DRAFT' and registry.get(rev)['manifest']==m
    assert 'http' in registry.review(new['manifest']['revision'])['changes']['changed_fields']
    assert descriptor(m,value['records'],'ACTIVE')['risk']==1


@pytest.mark.parametrize('url',['http://example.com/a','https://127.0.0.1/x','https://[::1]/','https://localhost/','https://x.internal/','https://x.local/','https://x.test/','https://a:b@example.com','https://example.com/?token=x','https://example.com/#x','https://api.github.com/repos/facebook/react','https://example.com/%2e%2e','https://example.com:444/','https://example.com/../x','https://example.com\\@evil.com/'])
def test_unsafe_endpoint_is_rejected(url):
    with pytest.raises(ToolError):endpoint(url)


@pytest.mark.parametrize('change',[{'risk':0},{'risk':2},{'http':{'url':'https://example.com','method':'DELETE','purpose':'query_or_inference'}},{'records':[{'profile':'photo','query':{},'body':{'api_key':'forbidden'}}]},{'records':[{'profile':'photo','query':{'nested':{}},'body':{}}]}])
def test_invalid_risk_methods_credentials_and_params_are_rejected(change):
    with pytest.raises(ToolError):prepare(dict(registration(),**change),1)


@pytest.mark.parametrize('addresses',[['127.0.0.1'],['10.1.2.3'],['169.254.169.254'],['::1'],['::ffff:8.8.8.8'],['8.8.8.8','192.168.1.1'],['64:ff9b::a00:1'],['2002:7f00:1::']])
def test_dns_rebinding_mixed_or_private_targets_are_rejected(monkeypatch,addresses):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(0,0,0,'',(ip,443)) for ip in addresses])
    with pytest.raises(HTTPFailure,match='HTTP_TARGET_DENIED'):public_addresses('vision.example.com')


def test_dns_approved_address_is_pinned_and_tls_uses_original_hostname(monkeypatch):
    from chainguard_gateway import http_reader
    seen=[]
    sock=SimpleNamespace(close=lambda:None)
    monkeypatch.setattr(socket,'create_connection',lambda address,timeout:seen.append(address) or sock)
    conn=http_reader.PinnedHTTPS('vision.example.com','8.8.8.8')
    conn._context=SimpleNamespace(wrap_socket=lambda socket,server_hostname:seen.append(server_hostname) or socket)
    conn.connect();assert seen==[('8.8.8.8',443),'vision.example.com'];conn.close()


@pytest.mark.parametrize('status,mime,raw,error',[(302,'application/json',b'{}','HTTP_REDIRECT_REJECTED'),(500,'application/json',b'{}','HTTP_REMOTE_ERROR'),(200,'text/html',b'<html>','HTTP_RESPONSE_INVALID'),(200,'application/json',b'x'*131073,'HTTP_RESPONSE_TOO_LARGE'),(200,'application/json',b'bad json','HTTP_RESPONSE_INVALID'),(200,'application/json',b'{"confidence":0.98}',None)],ids=['redirect','remote_error','html','oversized','invalid_json','json_float'])
def test_http_transport_sends_committed_request_and_rejects_unsafe_responses(monkeypatch,status,mime,raw,error):
    from chainguard_gateway import http_reader
    calls=[];chunks=[raw[i:i+8192] for i in range(0,len(raw),8192)]
    class Response:
        def __init__(self):self.status=status
        def getheader(self,name,default=None):return mime if name=='Content-Type' else default
        def read1(self,size):return chunks.pop(0) if chunks else b''
    class Connection:
        def __init__(self,host,address):calls.append(('connect',host,address))
        def request(self,method,path,body,headers):calls.append((method,path,body,headers))
        def getresponse(self):return Response()
        def close(self):calls.append('closed')
    monkeypatch.setattr(http_reader,'PinnedHTTPS',Connection);monkeypatch.setattr(http_reader,'public_addresses',lambda host:['8.8.8.8'])
    v=registration();m=prepare(v,1)
    if error:
        with pytest.raises(HTTPFailure,match=error):fetch(m,v['records'][0])
    else:
        data,actual=fetch(m,v['records'][0]);assert actual==raw and json.loads(data['record']['response'])['confidence']==.98
    assert calls[1][0:3]==('POST','/recognize?lang=zh',canonical(v['records'][0]['body'])) and calls[-1]=='closed'


def test_reader_id_conflict_and_local_rate_limit_do_not_reach_transport(tmp_path):
    v=registration();v['records'].append({'profile':'other','query':{},'body':{}});m=prepare(v,1);calls=[];h={'Authorization':'Bearer '+'t'*64}
    client=TestClient(create_app(tmp_path,'t'*64,fetcher=lambda *a:calls.append(1) or fixture_data(*a)))
    client.post('/install',headers=h,json={'manifest':m,'records':v['records']})
    query={'revision':m['revision'],'profile':'photo','execution_id':'0x'+'20'*32}
    assert client.post('/fetch',headers=h,json=query).status_code==200
    assert client.post('/fetch',headers=h,json=dict(query,profile='other')).json()['error']['code']=='IDEMPOTENCY_CONFLICT'
    for i in range(19):assert client.post('/fetch',headers=h,json=dict(query,execution_id='0x'+f'{i+1:064x}')).status_code==200
    assert client.post('/fetch',headers=h,json=dict(query,execution_id='0x'+'99'*32)).json()['error']['code']=='HTTP_LOCAL_RATE_LIMIT'
    assert len(calls)==20


def fixture_data(manifest,record):
    raw=b'{"labels":["cat"],"confidence":0.98}'
    return {'record':{'profile':record['profile'],'response':raw.decode()},'source':{'url':manifest['http']['url'],'method':manifest['http']['method'],'http_status':200,
        'fetched_at_utc':'fixture','response_sha256':hashlib.sha256(raw).hexdigest(),'request_sha256':hashlib.sha256(canonical({'http':manifest['http'],'record':record})).hexdigest()}},raw


def test_reader_auth_review_idempotency_revocation_and_encrypted_evidence(tmp_path):
    calls=[];v=registration();m=prepare(v,1);token='t'*64
    client=TestClient(create_app(tmp_path,token,fetcher=lambda *args:calls.append(args) or fixture_data(*args)))
    h={'Authorization':'Bearer '+token};body={'manifest':m,'records':v['records']}
    assert client.post('/install',json=body).status_code==401
    query={'revision':m['revision'],'profile':'photo','execution_id':'0x'+'12'*32}
    assert client.post('/fetch',headers=h,json=query).status_code==403 and not calls
    assert client.post('/install',headers=h,json=body).json()['active']
    first=client.post('/fetch',headers=h,json=query);assert first.status_code==200
    assert client.post('/fetch',headers=h,json=query).json()==first.json() and len(calls)==1
    assert client.post('/fetch',headers=h,json=dict(query,profile='other')).status_code==403
    assert b'cat' not in (tmp_path/'http.sqlite3').read_bytes()
    assert client.post('/disable',headers=h,json={'revision':m['revision']}).status_code==200
    assert not client.post('/install',headers=h,json=body).json()['active']
    assert client.post('/fetch',headers=h,json=query).status_code==403 and len(calls)==1


def test_reader_timeout_is_persistent_unknown_and_never_resends(tmp_path):
    calls=[]
    def unavailable(*args):calls.append(1);raise HTTPFailure('HTTP_UNAVAILABLE')
    v=registration();m=prepare(v,1);h={'Authorization':'Bearer '+'t'*64};query={'revision':m['revision'],'profile':'photo','execution_id':'0x'+'13'*32}
    client=TestClient(create_app(tmp_path,'t'*64,fetcher=unavailable));client.post('/install',headers=h,json={'manifest':m,'records':v['records']})
    assert client.post('/fetch',headers=h,json=query).json()['error']['code']=='HTTP_UNAVAILABLE'
    restarted=TestClient(create_app(tmp_path,'t'*64,fetcher=unavailable))
    assert restarted.post('/fetch',headers=h,json=query).json()['error']['code']=='HTTP_EXECUTION_UNKNOWN' and len(calls)==1


def test_revocation_during_fetch_withholds_actual_response(tmp_path):
    v=registration();m=prepare(v,1)
    def revoke(*args):
        with sqlite3.connect(tmp_path/'http.sqlite3') as c:c.execute('UPDATE manifests SET active=0')
        return fixture_data(*args)
    client=TestClient(create_app(tmp_path,'t'*64,fetcher=revoke));h={'Authorization':'Bearer '+'t'*64}
    client.post('/install',headers=h,json={'manifest':m,'records':v['records']})
    r=client.post('/fetch',headers=h,json={'revision':m['revision'],'profile':'photo','execution_id':'0x'+'14'*32})
    assert r.status_code==403 and 'cat' not in r.text
    with sqlite3.connect(tmp_path/'http.sqlite3') as c:assert c.execute('SELECT status FROM fetches').fetchone()[0]=='WITHHELD_POLICY'


def test_external_observation_is_explicitly_not_chain_certification():
    row={'risk':1,'tool':'custom.vision_query','adapter':'http.request'}
    result=verify_live_entry(None,row)
    assert result['status']=='EXTERNAL_TOOL_OBSERVATION' and result['current_chain_state'] is None and result['transactions']==[]


def test_actual_http_registration_and_version_api_accept_http_fields_and_keep_role_guards(tmp_path):
    import threading
    from chainguard_gateway.phase10_api import create_operations_app
    from chainguard_gateway.phase10_service import Operations
    store=OperationsStore(tmp_path);registry=ToolRegistry(store)
    class Ops:
        custom_registry=registry;mutex=threading.RLock();stop=SimpleNamespace(set=lambda:None)
        def __init__(self):self.store=store
        register_custom=Operations.register_custom
        version_custom=Operations.version_custom
        custom_descriptor=staticmethod(Operations.custom_descriptor)
        review_custom=lambda self,rev:registry.review(rev)
    ops=Ops();origin='http://127.0.0.1:8090';client=TestClient(create_operations_app(ops,{},origin,start_worker=False))
    def role(name):
        token,csrf=store.login(name);client.cookies.set('cg_session',token);return {'Origin':origin,'X-CSRF-Token':csrf}
    headers=role('requester');v=registration()
    response=client.post('/ops/v1/custom-tools',headers=headers,json=v);assert response.status_code==201,response.text
    rev=response.json()['revision'];assert response.json()['risk']==1
    assert client.get('/ops/v1/custom-tools/'+rev).json()['manifest']['http']==v['http']
    new=client.post('/ops/v1/custom-tools/'+rev+'/versions',headers=headers,json=dict(v,http=dict(v['http'],url='https://other.example.com/read')))
    assert new.status_code==201 and new.json()['revision']!=rev and new.json()['state']=='DRAFT'
    assert client.post('/ops/v1/custom-tools',headers=role('security'),json=v).status_code==403
