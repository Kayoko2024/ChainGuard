import test from 'node:test';
import assert from 'node:assert/strict';
import {workflow} from '../src/workflow.mjs';
const job=(state,count=2,expires='200')=>({record:{state,intent:{expires_at:expires},approval_signatures:Array(count).fill('signature'),reservation_evidence:null}});
test('both approvals still require requester reserve, not automatic sending',()=>{
 const result=workflow(job('AWAITING_APPROVAL'),'security',100000);
 assert.match(result.label,/等待请求者/);assert.match(result.hint,/切换到请求者/);assert.equal(result.executeLabel,'发起链上预约并执行');
 assert.match(workflow(job('AWAITING_APPROVAL',1),'requester',100000).label,/1\/2/);
});
test('expired intent cannot be presented as ready; final receipt does not expire with intent',()=>{
 assert.equal(workflow(job('AWAITING_APPROVAL'),'requester',201000).blocked,true);
 assert.match(workflow(job('AWAITING_APPROVAL'),'requester',201000).hint,/新建任务/);
 assert.equal(workflow(job('FINALIZED_OK'),'requester',201000).blocked,false);
});
test('unknown never offers a fresh reservation or resend',()=>{
 const result=workflow(job('UNKNOWN'),'requester',201000);
 assert.match(result.label,/禁止再次发送/);assert.match(result.executeLabel,/不会重发/);
});
test('24h signatures remain available after the old 120s window and block at their own deadline',()=>{
 const next=job('AWAITING_APPROVAL',2,'87400');next.record.intent.issued_at='1000';
 assert.equal(workflow(next,'requester',1901000).blocked,false);
 assert.equal(workflow(next,'requester',87400000).blocked,true);
 const old=job('AWAITING_APPROVAL',2,'1120');old.record.intent.issued_at='1000';
 assert.equal(workflow(old,'requester',1901000).blocked,true);
});
