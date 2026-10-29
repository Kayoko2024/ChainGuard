import test from 'node:test';
import assert from 'node:assert/strict';
import {taskBody,selectionValid,selectionIssues,toolAuthorizationLabel} from '../src/tool-selection.mjs';

test('read-only task has no send recipients and keeps distinct mailbox scope',()=>{
 const body=taskBody('read',['mail.list','mail.read'],['meeting-notes'],['alice@inbox.chainguard.invalid'],['bob@inbox.chainguard.invalid']);
 assert.deepEqual(body.allowed_recipients,[]);assert.deepEqual(body.allowed_document_ids,[]);
 assert.deepEqual(body.read_mailboxes,['alice@inbox.chainguard.invalid']);
});
test('a selected resource tool requires an explicit nonempty scope',()=>{
 assert.equal(selectionValid([],[],[],[]),false);
 assert.equal(selectionValid(['doc.read'],[],[],[]),false);
 assert.equal(selectionValid(['mail.read'],[],[],[]),false);
 assert.equal(selectionValid(['mail.send'],[],[],[]),false);
 assert.equal(selectionValid(['doc.search','mail.send'],['meeting-notes'],[],['alice']),true);
});
test('custom task binds the selected immutable revision and explicit keys',()=>{
 const grants=[{name:'custom.project_lookup',revision:'0x123',allowed_keys:['DEMO-1']}];
 assert.equal(selectionValid(['custom.project_lookup'],[],[],[],[]),false);
 assert.equal(selectionValid(['custom.project_lookup'],[],[],[],grants),true);
 assert.deepEqual(taskBody('lookup',['custom.project_lookup'],[],[],['alice'],grants).custom_tools,grants);
 assert.deepEqual(taskBody('read',['doc.list'],['notes'],[],[],grants).custom_tools,undefined);
});
test('task picker distinguishes session approval, per-call review and original R2 reservation',()=>{
 assert.equal(toolAuthorizationLabel({enabled:true,custom:true,risk_level:'LOW'}),'LOW · 有效会话内免逐次审批');
 assert.equal(toolAuthorizationLabel({enabled:true,custom:true,risk_level:'HIGH',requires_approval:true}),'HIGH · 每次调用须双组织审批');
 assert.equal(toolAuthorizationLabel({enabled:true,custom:true}),'尚无链上风险标签 · 需 OrgB 复审');
 assert.equal(toolAuthorizationLabel({enabled:true,requires_approval:true}),'双组织审批 + 链上预约');
 assert.equal(toolAuthorizationLabel({enabled:false,custom:true,risk_level:'LOW'}),'尚未开放');
});
test('selecting a custom tool does not grant its resources and explains why send is blocked',()=>{
 const tools=['doc.list','doc.search','doc.read','mail.list','mail.read','mail.send','custom.vision'];
 const docs=['meeting-notes'],boxes=['alice@inbox.chainguard.invalid'];
 const catalog=[{name:'custom.vision',label:'图片识别',revision:'revision-1'}];
 const issues=selectionIssues(tools,docs,boxes,boxes,[],null,catalog);
 assert.equal(issues.length,1);assert.equal(issues[0].code,'CUSTOM_SCOPE_MISSING');
 assert.equal(issues[0].tool,'custom.vision');assert.match(issues[0].message,/图片识别.*custom\.vision.*记录或资源/);
 const grants=[{name:'custom.vision',revision:'revision-1',allowed_keys:['image-check']}];
 assert.deepEqual(selectionIssues(tools,docs,boxes,boxes,grants,null,catalog),[]);
 assert.equal(selectionValid(tools,docs,boxes,boxes,grants,null,catalog),true);
 assert.deepEqual(taskBody('task',tools,docs,boxes,boxes,grants).custom_tools,grants);
});
test('readable mailboxes, send recipients and documents each have independent guidance',()=>{
 const issues=selectionIssues(['doc.read','mail.read','mail.send'],[],[],[]);
 assert.deepEqual(issues.map(i=>i.code),['DOCUMENT_SCOPE_MISSING','MAILBOX_SCOPE_MISSING','RECIPIENT_SCOPE_MISSING']);
 assert.equal(selectionValid(['mail.read'],[],[],['alice']),false);
 assert.equal(selectionIssues(['mail.read'],[],['alice'],[]).length,0);
});
test('custom selection must match the current catalog revision rather than reuse old authorization',()=>{
 const grants=[{name:'custom.lookup',revision:'old',allowed_keys:['one']}];
 const catalog=[{name:'custom.lookup',revision:'new',label:'查询'}];
 assert.equal(selectionValid(['custom.lookup'],[],[],[],grants,null,catalog),false);
 assert.equal(selectionIssues(['custom.lookup'],[],[],[],grants,null,catalog)[0].code,'CUSTOM_SCOPE_MISSING');
 assert.equal(selectionValid(['doc.list'],['notes'],[],[],grants,null,catalog),true);
});
test('empty or malformed custom scopes remain blocked without inventing an authorization',()=>{
 for(const allowed_keys of [[],null,undefined]){
  const grants=[{name:'custom.lookup',revision:'one',allowed_keys}];
  assert.equal(selectionValid(['custom.lookup'],[],[],[],grants),false);
  assert.deepEqual(grants,[{name:'custom.lookup',revision:'one',allowed_keys}]);
 }
});
test('attachment-only and document-output tasks retain their existing valid selection',()=>{
 assert.equal(selectionIssues([],[],[],[])[0].code,'TOOLS_MISSING');
 assert.deepEqual(selectionIssues([],[],[],[],[],{attachment_ids:['source'],allow_create:false}),[]);
 assert.deepEqual(selectionIssues([],[],[],[],[],{attachment_ids:[],allow_create:true}),[]);
});
