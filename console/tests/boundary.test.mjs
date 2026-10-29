import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {tone,verificationLabels} from '../../dashboard/src/format.mjs';
test('unanchored signed receipt stays pending, never verified',()=>{
 assert.equal(tone('PENDING_ANCHOR'),'pending');assert.match(verificationLabels.PENDING_ANCHOR,/待链上确认/);
});
test('business UI contains no browser-side private signing or direct RPC client',()=>{
 const source=fs.readFileSync(new URL('../src/main.jsx',import.meta.url),'utf8');
 for(const forbidden of ['eth_sendRawTransaction','privateKey','signTypedData','CHAINGUARD_LLM_API_KEY','Bearer '])assert.ok(!source.includes(forbidden));
 assert.ok(source.includes('/ops/v1/tasks'));assert.ok(source.includes('intent_digest'));
});
