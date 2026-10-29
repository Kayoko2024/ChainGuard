"""Tool SQLite/capability boundaries in a non-root container; transport is a fixture."""
import hashlib
import time
import unittest
from unittest.mock import patch
from chainguard_sandbox.storage import Store
from chainguard_sandbox.custom_library import CustomLibrary
from chainguard_sandbox.protocol import ToolError
from chainguard_gateway.custom_tools import prepare
from chainguard_gateway.http_tools import HTTPFailure
from chainguard_gateway.canonical import canonical

TASK='0x'+'61'*32;AGENT='0x'+'62'*20

class HTTPToolTests(unittest.TestCase):
    def setUp(self):
        self.store=Store.create();self.key=self.store.private_read('operator.key').decode();self.library=CustomLibrary(self.store);self.fetches=[]
        self.value=dict(name='custom.http_query',label='HTTP',description='Reviewed query',adapter='http.request',risk=1,key_field='profile',output_fields=['profile','response'],
            http={'url':'https://vision.example.com/query','method':'POST','purpose':'query_or_inference'},records=[{'profile':'photo','query':{},'body':{'image_url':'https://example.com/photo.png'}},{'profile':'other','query':{},'body':{}}])
        self.m=prepare(self.value,1);self.rev=self.m['revision'];self.failure=False;self.after_fetch=None
        self.mock=patch('chainguard_sandbox.http_client.request',self.request);self.mock.start()
        self.library.install(self.key,self.m,self.value['records'])
        self.library.grant(self.key,TASK,AGENT,[{'name':self.m['name'],'revision':self.rev,'allowed_keys':['photo']}],int(time.time())+600)
    def tearDown(self):self.mock.stop();self.store.close()
    def request(self,store,op,value):
        if op!='fetch':return {'revision':self.rev,'active':op=='install'}
        self.fetches.append(value)
        if self.failure:raise HTTPFailure('HTTP_UNAVAILABLE')
        if self.after_fetch:self.after_fetch()
        sha=hashlib.sha256(canonical({'http':self.m['http'],'record':self.value['records'][0]})).hexdigest()
        return {'fetch_id':value['execution_id'],'data':{'record':{'profile':'photo','response':'{"labels":["cat"]}'},'source':{'url':self.m['http']['url'],'method':'POST','http_status':200,'fetched_at_utc':'fixture','response_sha256':'a'*64,'request_sha256':sha}}}
    def call(self,arguments=None):return self.library.execute(TASK,AGENT,self.m['name'],self.rev,arguments or {'query':'photo'})
    def test_persistent_result_and_single_request_across_restarts(self):
        first=self.call();self.assertEqual(first,self.call());self.assertEqual(len(self.fetches),1)
        self.assertEqual(first['sha256'],hashlib.sha256(canonical(first['data'])).hexdigest())
        self.assertNotIn(b'labels',(self.store.root/'state.sqlite3').read_bytes())
        self.library=CustomLibrary(self.store);self.assertEqual(self.call(),first)
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_tool_reads').fetchone()[0],1)
    def test_parameter_injection_scope_and_disabled_version_do_not_fetch(self):
        for arguments in [{'query':'other'},{'query':'photo','url':'https://other.com'},{'query':'photo','body':{}}]:
            with self.assertRaises(ToolError):self.call(arguments)
        self.assertFalse(self.library.disable(self.key,self.rev)['active'])
        with self.assertRaisesRegex(ToolError,'POLICY_REVOKED'):self.call()
        self.assertEqual(self.fetches,[])
    def test_timeout_preserves_unknown_without_automatic_retry(self):
        self.failure=True;self.assertEqual(self.call()['error_code'],'HTTP_UNAVAILABLE')
        self.library=CustomLibrary(self.store);self.assertEqual(self.call()['error_code'],'HTTP_EXECUTION_UNKNOWN');self.assertEqual(len(self.fetches),1)
    def test_revoke_while_waiting_withholds_result(self):
        self.after_fetch=lambda:self.library.disable(self.key,self.rev)
        with self.assertRaisesRegex(ToolError,'POLICY_REVOKED'):self.call()
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_tool_reads').fetchone()[0],0)
    def test_reader_response_must_match_the_exact_admitted_request(self):
        original=self.request
        def tampered(store,op,value):
            result=original(store,op,value)
            if op=='fetch':result['data']['source']['request_sha256']='0'*64
            return result
        with patch('chainguard_sandbox.http_client.request',tampered):
            with self.assertRaisesRegex(ToolError,'PARAMS_MISMATCH'):self.call()
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_tool_reads').fetchone()[0],0)

if __name__=='__main__':unittest.main()
