"""Container-only independent capability tests; network fixtures are not live evidence."""
import time
import unittest
from unittest.mock import patch
from chainguard_sandbox.storage import Store
from chainguard_sandbox.custom_library import CustomLibrary
from chainguard_sandbox.protocol import ToolError
from chainguard_gateway.custom_tools import prepare
from chainguard_gateway.github_read import FIELDS,GitHubFailure
TASK='0x'+'91'*32;AGENT='0x'+'92'*20
class GitHubLibraryTests(unittest.TestCase):
    def setUp(self):
        self.store=Store.create();self.key=self.store.private_read('operator.key').decode()
        self.proof={'allowed':True,'contract':'fixture','repository_hash':'fixture'}
        self.library=CustomLibrary(self.store,repository_policy=lambda query:self.proof)
        self.rows=[{'resource':'psf/requests'},{'resource':'psf/requests#1'}]
        self.m=prepare(dict(name='custom.github_lookup',label='GitHub',description='Read public GitHub',adapter='github.read',risk=0,key_field='resource',output_fields=FIELDS,records=self.rows),1)
        self.rev=self.m['revision'];self.library.install(self.key,self.m,self.rows)
        self.library.grant(self.key,TASK,AGENT,[dict(name=self.m['name'],revision=self.rev,allowed_keys=['psf/requests'])],int(time.time())+600)
    def tearDown(self):self.store.close()
    def call(self,key='psf/requests',agent=AGENT):return self.library.execute(TASK,agent,self.m['name'],self.rev,{'query':key})
    @patch('chainguard_sandbox.github_client.query')
    def test_scope_and_stop_checked_before_egress(self,query):
        for key,agent in [('other/repo',AGENT),('psf/requests','0x'+'93'*20),('psf/requests#1',AGENT)]:
            with self.assertRaises(ToolError):self.call(key,agent)
        self.library.disable(self.key,self.rev)
        with self.assertRaisesRegex(ToolError,'POLICY_REVOKED'):self.call()
        query.assert_not_called()
    @patch('chainguard_sandbox.github_client.query',side_effect=GitHubFailure('GITHUB_RATE_LIMITED',403))
    def test_transport_failure_is_recorded_without_success_or_chain_receipt(self,query):
        result=self.call();self.assertEqual(result['status'],'READ_FAILED');self.assertEqual(result['error_code'],'GITHUB_RATE_LIMITED')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_tool_reads').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM custom_github_results').fetchone()[0],'GITHUB_RATE_LIMITED')
    @patch('chainguard_sandbox.github_client.query')
    def test_revocation_while_waiting_for_network_cannot_release_data(self,query):
        def revoke(*args):self.library.disable(self.key,self.rev);return {'record':{'resource':'psf/requests'}},'fetch-fixture',self.proof
        query.side_effect=revoke
        with self.assertRaisesRegex(ToolError,'POLICY_REVOKED'):self.call()
    @patch('chainguard_sandbox.github_client.query')
    def test_chain_deny_and_unavailable_prevent_any_reader_call(self,query):
        self.proof['allowed']=False
        self.assertEqual(self.call()['error_code'],'GITHUB_REPOSITORY_DENIED')
        self.library.repository_policy=lambda query:(_ for _ in ()).throw(GitHubFailure('GITHUB_POLICY_UNAVAILABLE'))
        self.assertEqual(self.call()['error_code'],'GITHUB_POLICY_UNAVAILABLE');query.assert_not_called()
    @patch('chainguard_sandbox.github_client.query')
    def test_chain_revocation_after_fetch_withholds_data(self,query):
        def revoke(*args):self.proof['allowed']=False;return {'record':{'resource':'psf/requests'}},'fixture',dict(self.proof,allowed=True)
        query.side_effect=revoke
        result=self.call();self.assertEqual(result['error_code'],'GITHUB_REPOSITORY_DENIED')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM custom_tool_reads').fetchone()[0],0)
if __name__=='__main__':unittest.main()
