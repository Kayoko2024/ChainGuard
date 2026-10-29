"""Actual encrypted dataset/SQLite operations inside the isolated tool container."""
import hashlib
import time
import unittest
from chainguard_sandbox.storage import Store
from chainguard_sandbox.custom_library import CustomLibrary
from chainguard_sandbox.protocol import ToolError
from chainguard_gateway.custom_tools import prepare
from chainguard_gateway.canonical import canonical

TASK='0x'+'31'*32;AGENT='0x'+'32'*20
class CustomTests(unittest.TestCase):
    def setUp(self):
        self.store=Store.create();self.key=self.store.private_read('operator.key').decode();self.library=CustomLibrary(self.store)
        self.rows=[{'id':'P1','owner':'PRIVATE_ALICE','private':'never returned'},{'id':'P2','owner':'Bob','private':'secret'}]
        self.value=dict(name='custom.project_lookup',label='Lookup',description='Lookup record',adapter='dataset.lookup',risk=0,key_field='id',output_fields=['id','owner'],records=self.rows)
        self.m=prepare(self.value,1);self.rev=self.m['revision']
        self.library.install(self.key,self.m,self.rows)
        self.grant=dict(task_id=TASK,agent=AGENT,tools=[dict(name=self.m['name'],revision=self.rev,allowed_keys=['P1'])],expires_at=int(time.time())+600)
        self.library.grant(self.key,**self.grant)
    def tearDown(self):self.store.close()
    def call(self,query='P1',**kw):return self.library.execute(kw.get('task',TASK),kw.get('agent',AGENT),self.m['name'],kw.get('revision',self.rev),{'query':query})
    def test_actual_result_encrypted_storage_and_persistent_read_log(self):
        r=self.call();self.assertEqual(r['data'],{'record':{'id':'P1','owner':'PRIVATE_ALICE'}})
        self.assertEqual(r['sha256'],hashlib.sha256(canonical(r['data'])).hexdigest())
        self.assertNotIn(b'PRIVATE_ALICE',(self.store.root/'state.sqlite3').read_bytes())
        root=self.store.root;self.store.close();self.store=Store(root);self.library=CustomLibrary(self.store)
        with self.store.connect() as db:
            row=db.execute('SELECT * FROM custom_tool_reads WHERE id=?',(r['read_execution_id'],)).fetchone()
            self.assertEqual(row['result_sha256'],r['sha256']);self.assertEqual(row['revision'],self.rev)
    def test_scope_identity_revision_expiry_and_invalid_arguments(self):
        for kwargs in [dict(task='0x'+'44'*32),dict(agent='0x'+'44'*20),dict(revision='0x'+'44'*32)]:
            with self.assertRaises(ToolError):self.call(**kwargs)
        with self.assertRaisesRegex(ToolError,'UNAUTHORIZED_SCOPE'):self.call('P2')
        for args in [{'query':'P1','path':'/etc/passwd'},{'query':[]},{'query':''}]:
            with self.assertRaisesRegex(ToolError,'SCHEMA_INVALID'):self.library.execute(TASK,AGENT,self.m['name'],self.rev,args)
        with self.store.transaction() as db:db.execute("UPDATE custom_tool_capabilities SET data=replace(data,?,?)",(str(self.grant['expires_at']),'1'))
        with self.assertRaisesRegex(ToolError,'RESERVATION_EXPIRED'):self.call()
    def test_revocation_is_persistent_and_install_retry_cannot_reenable(self):
        self.assertFalse(self.library.disable(self.key,self.rev)['active'])
        self.assertFalse(self.library.install(self.key,self.m,self.rows)['active'])
        with self.assertRaisesRegex(ToolError,'POLICY_REVOKED'):self.call()
    def test_operator_only_grants_and_manifests_tamper_detection(self):
        for op,args in [(self.library.install,(self.m,self.rows)),(self.library.disable,(self.rev,)),(self.library.grant,())]:
            with self.assertRaisesRegex(ToolError,'FORBIDDEN'):op('fake',*args,**(self.grant if op==self.library.grant else {}))
        with self.assertRaisesRegex(ToolError,'POLICY_DENY'):self.library.install(self.key,dict(self.m,risk=3),self.rows)
        with self.assertRaisesRegex(ToolError,'PARAMS_MISMATCH'):self.library.install(self.key,dict(self.m,dataset_sha256='0'*64),self.rows)
        with self.store.transaction() as db:db.execute("UPDATE custom_tool_catalog SET data=?",(b'tampered',))
        with self.assertRaises((ValueError,KeyError)):self.call()

if __name__=='__main__':unittest.main()
