import test from 'node:test';
import assert from 'node:assert/strict';
import {tone,short,verificationLabels,effectLabel} from '../src/format.mjs';
test('unknown/outage never uses verified styling or wording',()=>{assert.equal(tone('UNKNOWN'),'pending');assert.equal(tone('UNAVAILABLE'),'pending');assert.notEqual(verificationLabels.UNAVAILABLE,verificationLabels.VERIFIED);assert.equal(tone('INVALID'),'bad');});
test('hash labels retain endpoints and missing values stay empty',()=>{assert.equal(short(null),'—');assert.equal(short('0x'+'ab'.repeat(32)),'0xabababab…ababab');});
test('unknown side effects remain distinct from confirmed absence',()=>{assert.equal(effectLabel(null),'副作用未知');assert.equal(effectLabel(undefined),'副作用未知');assert.equal(effectLabel(false),'未观察到本地邮件');assert.equal(effectLabel(true),'已观察到本地邮件');});
