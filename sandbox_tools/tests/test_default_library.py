"""Actual file/MIME reads in a networkless, non-root disposable container."""
import hashlib
import json
import time
import unittest
from unittest.mock import patch
from email.message import EmailMessage
from chainguard_sandbox.storage import Store
from chainguard_sandbox.default_library import DefaultLibrary
from chainguard_sandbox.read_broker import ReadBroker
from chainguard_sandbox.protocol import ToolError
from chainguard_gateway.default_tools import DOCUMENTS

TASK='0x'+'11'*32
AGENT='0x'+'22'*20
ALICE='alice@inbox.chainguard.invalid'
BOB='bob@inbox.chainguard.invalid'

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.store=Store.create();self.key=self.store.private_read('operator.key').decode()
        self.library=DefaultLibrary(self.store)
        self.cap=dict(task_id=TASK,agent=AGENT,tools=['doc.list','doc.search','doc.read','mail.list','mail.read'],
            documents=['meeting-notes'],mailboxes=[ALICE],expires_at=int(time.time())+600)
        self.library.grant(self.key,**self.cap)
    def tearDown(self): self.store.close()
    def call(self,name,args=None): return self.library.execute(TASK,AGENT,name,args or {})
    def mail(self,recipient):
        message=EmailMessage(); message['To']=recipient;message['Subject']='Actual local message';message.set_content('Actual sandbox body')
        raw=message.as_bytes();sha=hashlib.sha256(raw).hexdigest()
        # Read fixture is an actual MIME record, not a claim of R2 authorization.
        with self.store.transaction() as db:
            db.execute("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?)",(TASK,'fixture','mail.send','sha','COMPLETED','1','1','{}',None))
            return str(db.execute('INSERT INTO mailbox(action_id,recipient,mime,mime_sha256) VALUES (?,?,?,?)',(TASK,recipient,raw,sha)).lastrowid)
    def test_actual_documents_search_read_and_persistent_execution(self):
        listed=self.call('doc.list')['data']['documents']
        self.assertEqual([d['doc_id'] for d in listed],['meeting-notes'])
        result=self.call('doc.search',{'query':'Alice'})
        self.assertIn('Alice',result['data']['documents'][0]['snippet'])
        self.assertEqual(self.call('doc.search',{'query':'no-matching-content'})['data']['documents'],[])
        read=ReadBroker(self.store).read(TASK,AGENT,'meeting-notes')
        self.assertEqual(read['content'],DOCUMENTS['meeting-notes'][1])
        root=self.store.root;self.store.close();self.store=Store(root);self.library=DefaultLibrary(self.store)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM library_reads').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT result_sha256 FROM library_reads WHERE id=?',(result['read_execution_id'],)).fetchone()[0],result['sha256'])
    def test_real_mail_scope_and_tampered_mime(self):
        self.assertEqual(self.call('mail.list')['data']['messages'],[])
        id=self.mail(ALICE)
        self.assertEqual(self.call('mail.read',{'message_id':id})['data']['messages'][0]['body'].strip(),'Actual sandbox body')
        with self.store.transaction() as db: db.execute("UPDATE mailbox SET mime=? WHERE message_id=?",(b'tampered',id))
        with self.assertRaisesRegex(ToolError,'RECEIPT_INVALID'): self.call('mail.read',{'message_id':id})
    def test_other_mailbox_is_invisible_and_id_cannot_bypass(self):
        id=self.mail(BOB)
        self.assertEqual(self.call('mail.list')['data']['messages'],[])
        with self.assertRaisesRegex(ToolError,'UNAUTHORIZED_SCOPE'): self.call('mail.read',{'message_id':id})
    def test_no_cross_task_agent_path_privilege_or_expired_capability(self):
        for task,agent in [('0x'+'33'*32,AGENT),(TASK,'0x'+'44'*20)]:
            with self.assertRaisesRegex(ToolError,'UNAUTHORIZED_SCOPE'): self.library.execute(task,agent,'doc.list',{})
        for name,args in [('doc.list',{'path':'/etc/passwd'}),('mail.read',{'message_id':'../secret'}),('mail.send',{}),('doc.delete',{})]:
            with self.assertRaises(ToolError): self.call(name,args)
        with self.assertRaisesRegex(ToolError,'UNAUTHORIZED_SCOPE'): ReadBroker(self.store).read(TASK,AGENT,'project-brief')
        with self.store.transaction() as db:
            cap=json.loads(db.execute('SELECT data FROM library_capabilities').fetchone()[0]);cap['expires_at']=1
            db.execute('UPDATE library_capabilities SET data=?',(json.dumps(cap),))
        with self.assertRaisesRegex(ToolError,'RESERVATION_EXPIRED'): self.call('doc.list')
    def test_agent_cannot_provision_or_expand_existing_grant(self):
        with self.assertRaisesRegex(ToolError,'FORBIDDEN'): self.library.grant('fake',**self.cap)
        with self.assertRaisesRegex(ToolError,'IDEMPOTENCY_CONFLICT'): self.library.grant(self.key,**dict(self.cap,mailboxes=[ALICE,BOB]))
        self.assertTrue(self.library.grant(self.key,**self.cap)['granted'])

    def test_full_day_capability_reads_real_files_persists_and_expires(self):
        cap=dict(self.cap,task_id='0x'+'55'*32,expires_at=1000000+86400)
        with patch('time.time',return_value=1000000):self.library.grant(self.key,**cap)
        root=self.store.root;self.store.close();self.store=Store(root);self.library=DefaultLibrary(self.store)
        with patch('time.time',return_value=1000000+3601):
            listed=self.library.execute(cap['task_id'],AGENT,'doc.list',{})
            self.assertEqual([d['doc_id'] for d in listed['data']['documents']],['meeting-notes'])
        with patch('time.time',return_value=cap['expires_at']-1):
            self.assertEqual(ReadBroker(self.store).read(cap['task_id'],AGENT,'meeting-notes')['content'],DOCUMENTS['meeting-notes'][1])
        with patch('time.time',return_value=cap['expires_at']):
            with self.assertRaisesRegex(ToolError,'RESERVATION_EXPIRED'):self.library.execute(cap['task_id'],AGENT,'doc.list',{})
            with self.assertRaisesRegex(ToolError,'RESERVATION_EXPIRED'):ReadBroker(self.store).read(cap['task_id'],AGENT,'meeting-notes')
        with self.store.connect() as db:
            original=json.loads(db.execute('SELECT data FROM library_capabilities WHERE task_id=?',(cap['task_id'],)).fetchone()[0])
            self.assertEqual(original['expires_at'],cap['expires_at'])

    def test_excessive_or_invalid_lifetime_never_installs_a_capability(self):
        task='0x'+'66'*32
        with patch('time.time',return_value=1000000):
            for expires,code in [(1000000,'RESERVATION_EXPIRED'),(1086401,'READ_CAPABILITY_WINDOW_INVALID'),('1086400','SCHEMA_INVALID'),(True,'SCHEMA_INVALID')]:
                with self.assertRaisesRegex(ToolError,code):self.library.grant(self.key,**dict(self.cap,task_id=task,expires_at=expires))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM library_capabilities WHERE task_id=?',(task,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM read_capabilities WHERE task_id=?',(task,)).fetchone()[0],0)

    def test_existing_grant_cannot_be_extended_during_retry(self):
        with self.assertRaisesRegex(ToolError,'IDEMPOTENCY_CONFLICT'):
            self.library.grant(self.key,**dict(self.cap,expires_at=self.cap['expires_at']+60))
        with self.store.connect() as db:
            value=json.loads(db.execute('SELECT data FROM library_capabilities WHERE task_id=?',(TASK,)).fetchone()[0])
        self.assertEqual(value['expires_at'],self.cap['expires_at'])

if __name__=='__main__': unittest.main()
