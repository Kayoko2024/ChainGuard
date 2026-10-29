import test from 'node:test';
import assert from 'node:assert/strict';
import {taskBody,selectionValid} from '../src/tool-selection.mjs';
import {taskError,serviceError,outputTruncation} from '../src/task-error.mjs';
test('attachments and output permission bind to this task without adding mail scope',()=>{
 const scope={attachment_ids:['0x'+'12'.repeat(32)],allow_create:true};
 const task=taskBody('revise',[],[],[],[],[],scope);
 assert.deepEqual(task.document_scope,scope);assert.deepEqual(task.allowed_recipients,[]);assert.deepEqual(task.allowed_tools,[]);
 assert.equal(selectionValid([],[],[],[],[],scope),true);
 assert.equal(selectionValid([],[],[],[],[],{attachment_ids:[],allow_create:false}),false);
 assert.equal(selectionValid(['mail.send'],[],[],[],[],scope),false);
 assert.ok(!('document_scope' in taskBody('old task',['doc.read'],['meeting-notes'],[],[])));
});

test('truncation explains historical failures from evidence without changing stored state',()=>{
 const job={error:'SCHEMA_INVALID',display_state:'MODEL_ERROR',events:[{kind:'MODEL_EXCHANGE',exchange:{response:{choices:[{finish_reason:'length'}]}}}]};
 const original=JSON.stringify(job);
 assert.match(taskError(job),/被截断/);
 assert.equal(JSON.stringify(job),original);
 assert.equal(taskError({...job,events:[]}), 'SCHEMA_INVALID');
 assert.match(taskError({error:'MODEL_OUTPUT_TRUNCATED'}),/不会自动重放/);
 assert.equal(taskError({}), '');
});
test('backend outage and chain verification outage give distinct non-resending guidance',()=>{
 assert.match(serviceError('BACKEND_UNAVAILABLE'),/执行网关暂时失联/);
 assert.match(serviceError('CHAIN_UNAVAILABLE'),/联盟链核验暂不可用/);
 assert.match(taskError({error:'BACKEND_UNAVAILABLE'}),/不要重复发送/);
 assert.equal(serviceError('NOT_FOUND'),'NOT_FOUND');
});
test('capability lifetime overflow differs from expiry and preserves historical records',()=>{
 assert.match(serviceError('READ_CAPABILITY_WINDOW_INVALID'),/超过工具允许的24小时上限/);
 const original={error:'RESERVATION_EXPIRED',display_state:'MODEL_ERROR',events:[]};
 const snapshot=JSON.stringify(original);
 assert.match(taskError(original),/旧版本也曾用此代码表示期限上限不匹配/);
 assert.match(taskError(original),/不会自动重发/);
 assert.equal(JSON.stringify(original),snapshot);
});

const truncatedJob=(message,limit=4096,error='MODEL_OUTPUT_TRUNCATED')=>({error,events:[{kind:'MODEL_EXCHANGE',exchange:{request:{max_tokens:limit},response:{choices:[{finish_reason:'length',message}]}}}]});
test('plain text truncation identifies the actual historical limit and allows same-session follow-up',()=>{
 const job=truncatedJob({role:'assistant',content:'partial reply',tool_calls:[]},512);
 const original=JSON.stringify(job);
 assert.deepEqual(outputTruncation(job),{kind:'reply',max_tokens:512});
 assert.match(taskError(job),/文字回复.*512 tokens/);
 assert.match(taskError(job),/原会话.*无需新建会话/);
 assert.doesNotMatch(taskError(job),/工具调用参数|请新建任务/);
 assert.equal(JSON.stringify(job),original);
});
test('truncated tool batches never present a complete first call as executable',()=>{
 const message={role:'assistant',content:'partial answer',tool_calls:[
  {function:{name:'mail_send',arguments:'{}'}},{function:{name:'document_create',arguments:'{"content":"'}}
 ]};
 const job=truncatedJob(message,8192);
 assert.deepEqual(outputTruncation(job),{kind:'tool_arguments',max_tokens:8192});
 assert.match(taskError(job),/工具调用参数.*8192 tokens/);
 assert.match(taskError(job),/阻止.*全部工具调用/);
 assert.match(taskError(job),/不会自动重放/);
 assert.doesNotMatch(taskError(job),/请新建任务/);
});
test('legacy schema failures are classified only with recorded length evidence',()=>{
 const job=truncatedJob({role:'assistant',content:'partial'},4096,'SCHEMA_INVALID');
 assert.equal(outputTruncation(job).kind,'reply');
 assert.match(taskError(job),/4096 tokens/);
 job.events[0].exchange.response.choices[0].finish_reason='stop';
 assert.equal(outputTruncation(job),null);assert.equal(taskError(job),'SCHEMA_INVALID');
});
test('missing or inconsistent model evidence stays unknown without fabricating a limit',()=>{
 assert.deepEqual(outputTruncation({error:'MODEL_OUTPUT_TRUNCATED'}),{kind:'unknown',max_tokens:null});
 const missing=truncatedJob(undefined,-1);
 assert.match(taskError(missing),/不足以区分/);assert.doesNotMatch(taskError(missing),/-1 tokens/);
 const malformed=truncatedJob({role:'assistant',content:'partial',tool_calls:'invalid'});
 assert.equal(outputTruncation(malformed).kind,'unknown');
 const contradictory=truncatedJob({role:'assistant',tool_calls:[{function:{name:'mail_send'}}]});
 contradictory.events[0].exchange.response.choices[0].finish_reason='stop';
 assert.equal(outputTruncation(contradictory).kind,'unknown');
 assert.equal(outputTruncation(undefined),null);
});
