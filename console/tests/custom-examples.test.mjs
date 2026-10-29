import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {taskBody,selectionValid} from '../src/tool-selection.mjs';
const examples=JSON.parse(fs.readFileSync(new URL('../src/custom-tool-examples.json',import.meta.url),'utf8'));

test('contact and inventory examples use the admitted adapter and explicit resource keys',()=>{
 assert.deepEqual(examples.map(e=>e.id),['contacts','inventory']);
 for(const example of examples){const value=example.registration;
  assert.equal(value.adapter,'dataset.lookup');assert.equal(value.risk,0);
  assert.ok(value.output_fields.includes(value.key_field));
  const keys=value.records.map(r=>r[value.key_field]);assert.equal(new Set(keys).size,keys.length);
  const grant={name:value.name,revision:'0x'+'ab'.repeat(32),allowed_keys:[keys[0]]};
  assert.equal(selectionValid([value.name],[],[],[],[]),false);
  const task=taskBody(example.task_example,[value.name],[],[],['should-not-send'],[grant]);
  assert.deepEqual(task.allowed_recipients,[]);assert.deepEqual(task.custom_tools,[grant]);
 }
});

test('contact email addresses stay in the local test mailbox domain',()=>{
 for(const record of examples.find(e=>e.id==='contacts').registration.records)assert.match(record.email,/^[a-z]+@inbox\.chainguard\.invalid$/);
});

test('inventory counts remain numbers and cover both sides of the reorder threshold',()=>{
 const records=examples.find(e=>e.id==='inventory').registration.records;
 assert.ok(records.some(r=>r.quantity>=r.reorder_level));assert.ok(records.some(r=>r.quantity<r.reorder_level));
 for(const r of records){assert.equal(Number.isInteger(r.quantity),true);assert.equal(Number.isInteger(r.reorder_level),true);}
});
