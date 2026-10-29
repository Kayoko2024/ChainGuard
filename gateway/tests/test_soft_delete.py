"""Visibility changes preserve the original private rows and public audit evidence."""
import json
import secrets
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from chainguard_gateway.phase10_store import OperationsStore,PublicStore
from chainguard_gateway.phase10_service import Operations
from chainguard_gateway.phase10_api import create_operations_app,password_hash
from chainguard_gateway.phase10_audit import create_live_audit_app
from chainguard_gateway.conversation_store import Conversations

ROOT=Path(__file__).resolve().parents[2]
def id(n):return '0x'+format(n,'064x')


@pytest.mark.parametrize('state',['NO_ACTION','READ_COMPLETED','AWAITING_APPROVAL','UNKNOWN','FINALIZED_OK'])
def test_hiding_never_rewrites_execution_memory_signatures_or_public_evidence(tmp_path,state):
    store=OperationsStore(tmp_path/'private');c=Conversations(store);c.create(id(1),'requester/OrgA',{})
    c.append(id(1),'requester/OrgA',id(2),'synthetic input',0)
    store.update(id(2),state=state,record={'tx_hash':id(90),'signature':'original-signature'})
    store.event(id(2),dict(kind='ORIGINAL_EVENT'))
    public=PublicStore(tmp_path/'public.sqlite');public.publish(dict(entry_id='original',state=state,signature='original-signature',tx_hash=id(90)))
    with store.db() as db:before={table:db.execute('SELECT * FROM '+table).fetchall() for table in ['jobs','events','conversations','conversation_runs']}
    assert store.hide('conversation',id(1),'requester/OrgA')['is_hidden']
    assert store.hide('conversation',id(1),'requester/OrgA')['is_hidden']
    restored=OperationsStore(tmp_path/'private')
    assert Conversations(restored).listing('requester/OrgA')==[] and restored.visible_jobs('requester/OrgA')==[]
    assert len(Conversations(restored).listing('requester/OrgA',include_hidden=True))==1
    assert restored.get(id(2))['state']==state and public.actions()[0]['tx_hash']==id(90)
    with store.db() as db:
        for table,rows in before.items():assert [tuple(r) for r in rows]==[tuple(r) for r in db.execute('SELECT * FROM '+table)]


def test_legacy_task_delete_and_session_delete_keep_audit_get_and_verification(tmp_path,monkeypatch):
    config=dict(deployment=json.loads((ROOT/'results/phase5/besu-run-01/report.json').read_text()),repo=str(ROOT))
    store=OperationsStore(tmp_path/'private');public=PublicStore(tmp_path/'public.sqlite')
    ops=Operations(store,public,SimpleNamespace(),config)
    ops.conversations.create(id(1),'requester/OrgA',{});ops.conversations.append(id(1),'requester/OrgA',id(2),'hello',0)
    store.create(id(3),dict(task_text='legacy',allowed_tools=['doc.list'],allowed_recipients=[]))
    public.publish(dict(entry_id='retained',group='C',state='FINALIZED_OK'))
    credentials={}
    for role in ['requester','security']:
        salt=secrets.token_hex(16);credentials[role]=dict(salt=salt,hash=password_hash('password',salt),organization=role)
    client=TestClient(create_operations_app(ops,credentials,'http://testserver',start_worker=False))
    def login(role):
        r=client.post('/ops/v1/login',headers={'Origin':'http://testserver'},json=dict(role=role,password='password'))
        return {'Origin':'http://testserver','X-CSRF-Token':r.json()['csrf']}
    h=login('security');assert client.delete('/ops/v1/conversations/'+id(1),headers=h).status_code==403
    h=login('requester');assert client.delete('/ops/v1/conversations/'+id(1),headers={'Origin':'http://testserver'}).status_code==403
    assert client.delete('/ops/v1/conversations/'+id(1),headers=h).status_code==200
    assert client.delete('/ops/v1/tasks/'+id(3),headers=h).status_code==200
    assert client.get('/ops/v1/tasks').json()['tasks']==[] and client.get('/ops/v1/conversations').json()['conversations']==[]
    login('security');assert len(client.get('/ops/v1/tasks').json()['tasks'])==2
    assert len(client.get('/ops/v1/conversations').json()['conversations'])==1
    monkeypatch.setattr('chainguard_gateway.phase10_audit.verify_live_entry',lambda chain,row:dict(status='VERIFIED',entry_id=row['entry_id']))
    audit=TestClient(create_live_audit_app(public.path,None))
    assert audit.get('/audit-api/v1/actions').json()['total']==1
    assert audit.get('/audit-api/v1/actions/retained/verify').json()['status']=='VERIFIED'


def test_conversation_list_reads_local_snapshot_without_remote_calls(tmp_path):
    from chainguard_gateway.conversation_service import ConversationService
    store=OperationsStore(tmp_path);c=Conversations(store);c.create(id(1),'owner',{})
    class Bridge:
        def conversation(self,*args):raise AssertionError('List must not perform IPC/RPC')
    ops=SimpleNamespace(store=store,conversations=c,config={'tool_sessions':{'conversation':{'configured':True}}},bridge=Bridge())
    store.cache('conversation/'+id(1),dict(logs=['cached-observation']))
    assert ConversationService(ops).detail(id(1),'owner')['low_status']['logs']==['cached-observation']
