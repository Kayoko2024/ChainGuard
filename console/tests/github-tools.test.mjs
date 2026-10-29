import test from 'node:test';
import assert from 'node:assert/strict';
import {githubRegistration} from '../src/github-tools.mjs';
import fs from 'node:fs';
import {prepareReadTask} from '../src/custom-management.mjs';
test('GitHub registration binds exact repo and issue without adding write authority',()=>{
 const v=githubRegistration('custom.github_lookup','PSF/Requests\npsf/requests#1');assert.equal(v.adapter,'github.read');assert.equal(v.risk,0);
 assert.deepEqual(v.records,[{resource:'psf/requests'},{resource:'psf/requests#1'}]);assert.ok(v.output_fields.includes('body'));
});
test('GitHub scope excludes URLs arbitrary hosts wildcard paths and ambiguous issues',()=>{
 for(const resources of ['','https://github.com/a/b','a/*','a/b#01','a/b#0','a/b\na/b','../etc/passwd','a/b?token=x'])assert.throws(()=>githubRegistration('custom.github_lookup',resources));
});
test('VS Code acceptance deliberately reaches chain denial through locally permitted other repo',()=>{
 const plan=JSON.parse(fs.readFileSync(new URL('../src/github-acceptance.json',import.meta.url)));
 assert.ok(plan.allowed_resources.includes('facebook/react#1'));
 assert.ok(!plan.allowed_resources.includes('microsoft/vscode#2'));
 assert.deepEqual(plan.chain_scope_policy.allowed_repositories,['microsoft/vscode']);
 assert.equal(plan.cases.find(c=>c.id==='other_repo_denied').expected,'GITHUB_REPOSITORY_DENIED');
 assert.equal(plan.github_token_required,false);
});
test('preparing acceptance keeps negative scope but defaults the normal prompt to one VS Code issue',()=>{
 const resources=['microsoft/vscode','microsoft/vscode#1','facebook/react#1'];
 const task=prepareReadTask({name:'custom.github_vscode',revision:'rev',enabled:true,state:'ACTIVE',adapter:'github.read',resources},resources);
 assert.deepEqual(task.custom[0].allowed_keys,resources);assert.ok(task.text.includes('query 精确为 microsoft/vscode#1'));assert.ok(!task.text.includes('facebook/react'));
});
