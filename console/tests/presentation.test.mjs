import test from 'node:test';
import assert from 'node:assert/strict';
import {executionStages,stateTone,stateLabel} from '../../shared/presentation.mjs';

test('approval count and a terminal state cannot manufacture execution evidence',()=>{
 const stages=executionStages({state:'FINALIZED_OK',action_id:'original',approval_signatures:['a','b']});
 assert.deepEqual(stages.map(s=>s.done),[true,true,false,false,false]);
 assert.deepEqual(executionStages(null).map(s=>s.done),[false,false,false,false,false]);
});
test('UNKNOWN with an actual reservation still needs a signed receipt and audit transaction',()=>{
 const record={action_id:'original',approval_signatures:['a','b'],reservation_evidence:{tx_hash:'real'},state:'UNKNOWN'};
 assert.deepEqual(executionStages(record).map(s=>s.done),[true,true,true,false,false]);
 assert.equal(stateTone('UNKNOWN'),'warning');assert.notEqual(stateTone('UNAVAILABLE'),'good');
 assert.notEqual(stateTone('APPROVAL_EXPIRED'),'good');assert.equal(stateLabel('UNKNOWN'),'执行结果未知');
 record.receipt={};assert.equal(executionStages(record)[3].done,false);
 record.tool_signature='signature';assert.equal(executionStages(record)[3].done,true);
 assert.equal(executionStages(record)[4].done,false);
});
