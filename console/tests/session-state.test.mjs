import {test} from 'node:test';
import assert from 'node:assert/strict';
import {conversationBusy,messageRequest,renewableError,canRetryMessage} from '../src/session-state.mjs';
test('pending and UNKNOWN block interleaved turns; final runs allow followup',()=>{
 for(const state of ['AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL','UNKNOWN','AGENT_RUNNING'])assert.equal(conversationBusy({runs:[{scheduler_state:state}]}),true);
 assert.equal(conversationBusy({runs:[{scheduler_state:'READ_COMPLETED'}]}),false);
 assert.deepEqual(messageRequest('继续',2,'unique-message'),{message_id:'unique-message',text:'继续',expected_version:2});
});
test('renewal retries only a definitely unaccepted message in its original current session',()=>{
 const pending={sessionId:'s1',request:messageRequest('继续',2,'m1')};
 const c={id:'s1',version:2,authorization:{status:'ACTIVE'},runs:[]};
 assert.equal(renewableError({code:'AUTH_EXPIRED',details:{accepted:false}}),true);
 for(const e of [{code:'AUTH_EXPIRED'},{code:'EXECUTION_UNKNOWN',details:{accepted:false}},{code:'AUTH_REQUIRED',details:{accepted:false}}])assert.equal(renewableError(e),false);
 assert.equal(canRetryMessage(pending,c,'s1'),true);
 assert.equal(canRetryMessage(pending,c,'s2'),false);
 assert.equal(canRetryMessage(pending,{...c,version:3},'s1'),false);
 assert.equal(canRetryMessage(pending,{...c,authorization:{status:'EXPIRED'}},'s1'),false);
 assert.equal(canRetryMessage(pending,{...c,blocking_run:{reason:'WAITING_APPROVAL'}},'s1'),false);
});
