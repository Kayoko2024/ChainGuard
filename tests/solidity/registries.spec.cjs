const assert = require('node:assert/strict');
const hre = require('hardhat');
const H = require('../../scripts/lib/phase5.cjs');
const {ethers,label,encode,rule,scopeMail,scopeDelete} = H;
let f;
async function denied(work, name) {
  try { const tx = await work(); if (tx.wait) await tx.wait(); }
  catch (e) {
    if (name) {
      let parsed;
      for (const contract of [f.policy,f.execution,f.audit]) {
        try { parsed = contract.interface.parseError(e.data || e.error?.data); if (parsed) break; } catch {}
      }
      assert.equal(parsed?.name,name,`wrong revert: ${e.message}`);
    }
    return;
  }
  assert.fail('transaction unexpectedly accepted');
}
async function live(risk=2, overrides={}) { return H.signedIntent(f,await H.intent(f,risk,overrides)); }
async function booked(risk=2) { const s=await live(risk); await (await H.reserve(f,s)).wait(); return s.value; }
async function change(...changes) { return H.govern(f,changes); }
async function role(s,r,enabled) { return change(encode(1,[s.address,label('role',r),enabled])); }
async function status(value) { return (await f.execution.getReservation(value.actionId)).status; }

describe('Phase 5 business contracts', function () {
beforeEach(async function () {
  const signers=await hre.ethers.getSigners();
  const names=['deployer','govA','govB','requester','agent','biz','security','human','mailTool','deleteTool','reconciler','outsider','alternate'];
  f=Object.fromEntries(names.map((n,i)=>[n,signers[i]]));
  Object.assign(f,await (await H.deploy(f.deployer))(f.govA,f.govB));
  await H.govern(f,H.registration(f));
});

describe('Phase 5 PolicyRegistry: two-organization governance', function () {
  it('matches GovernanceChange EIP-712 and complete changes ABI hash',async function () {
    const e=await H.govEnvelope(f,[rule(2)]),m=e.message;
    assert.equal(await f.policy.governanceDigest(e.changes,m.nonce,m.governanceEpoch,m.issuedAt,m.expiresAt),ethers.TypedDataEncoder.hash(e.domain,H.govSpec.types,m));
    await (await H.submitGov(f,e)).wait();
    assert.equal((await f.policy.getEffectiveRule(label('policy','POLICY_R2_MAIL'))).policyEpoch,2n);
  });
  it('rejects one organization, duplicate accounts and unauthorized extra signatures',async function () {
    await change(encode(1,[f.human.address,label('role','GOVERNANCE_ADMIN'),true]));
    for(const signers of [[f.govA],[f.govA,f.govA],[f.govA,f.human],[f.govA,f.govB,f.outsider]]) {
      const e=await H.govEnvelope(f,[rule(2)],{signers}); await denied(()=>H.submitGov(f,e),'InvalidGovernance');
    }
  });
  it('rejects replay, stale epoch, changed payload, wrong domain and expiry',async function () {
    const old=await H.govEnvelope(f,[rule(2)]); await (await H.submitGov(f,old)).wait();
    await denied(()=>H.submitGov(f,old),'InvalidGovernance');
    const e=await H.govEnvelope(f,[rule(2)]); e.changes=[rule(3)]; await denied(()=>H.submitGov(f,e),'InvalidGovernance');
    const now=BigInt((await hre.ethers.provider.getBlock('latest')).timestamp);
    const expired=await H.govEnvelope(f,[rule(2)],{issuedAt:now-10n,expiresAt:now}); await denied(()=>H.submitGov(f,expired),'InvalidGovernance');
    const wrong=await H.govEnvelope(f,[rule(2)]);
    wrong.signatures=await Promise.all([f.govA,f.govB].map(s=>s.signTypedData({...wrong.domain,chainId:1},H.govSpec.types,wrong.message)));
    await denied(()=>H.submitGov(f,wrong),'InvalidGovernance');
  });
  it('rejects current revoked governance keys and protects remaining independent admins',async function () {
    await change(encode(0,[f.human.address,label('org','OrgC_Audit'),true]),encode(1,[f.human.address,label('role','GOVERNANCE_ADMIN'),true]));
    const pending=await H.govEnvelope(f,[rule(2)],{signers:[f.govA,f.human]});
    await change(encode(0,[f.human.address,label('org','OrgC_Audit'),false]));
    pending.message.governanceEpoch=await f.policy.governanceEpoch(); // re-sign with the revoked key at current epoch
    pending.signatures=await Promise.all([f.govA,f.human].map(s=>s.signTypedData(pending.domain,H.govSpec.types,pending.message)));
    await denied(()=>H.submitGov(f,pending),'InvalidGovernance');
    await denied(()=>change(encode(1,[f.govB.address,label('role','GOVERNANCE_ADMIN'),false])),'InvalidGovernance');
  });
  it('closes every AccessControl mutation bypass and default admin role',async function () {
    for(const method of ['grantRole','revokeRole','renounceRole']) await denied(()=>f.policy[method](label('role','REQUESTER'),f.outsider.address),'GovernanceOnly');
    assert.equal(await f.policy.hasRole(ethers.ZeroHash,f.deployer.address),false);
    await denied(()=>change(encode(1,[f.requester.address,ethers.ZeroHash,true])),'InvalidChange');
  });
  it('allows single-admin pause; requires two organizations to unpause',async function () {
    await denied(()=>f.policy.connect(f.outsider).emergencyPause());
    await (await f.policy.connect(f.govA).emergencyPause()).wait();
    const s=await live(); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    await change(encode(6,[])); assert.equal(await f.policy.paused(),false);
    await (await H.reserve(f,s)).wait();
  });
  it('atomically rejects risk downgrade, excessive lifetime and partial invalid batches',async function () {
    const epoch=await f.policy.governanceEpoch();
    await denied(()=>change(rule(2,false),rule(3,true,61)),'InvalidChange');
    assert.equal(await f.policy.governanceEpoch(),epoch);
    assert.equal((await f.policy.getEffectiveRule(label('policy','POLICY_R2_MAIL'))).enabled,true);
    const bad=encode(5,[label('policy','POLICY_R2_MAIL'),label('tool','mail.send'),scopeMail,120,1,true]);
    await denied(()=>change(bad),'InvalidChange');
  });
});

describe('Phase 5 ExecutionRegistry: exact-intent one-time authorization',function () {
  it('reserves real R2 and stores digest, recovered actors and timestamp',async function () {
    const s=await live(); const tx=await H.reserve(f,s),r=await tx.wait(); const reservation=await f.execution.getReservation(s.value.actionId);
    assert.equal(reservation.status,1n); assert.deepEqual([...reservation.approvers],[f.biz.address,f.security.address]);
    assert.equal(reservation.intentHash,await f.execution.intentDigest(s.value));
    assert.equal(reservation.reservedAt,BigInt((await hre.ethers.provider.getBlock(r.blockNumber)).timestamp));
    assert.equal(await f.execution.usedNonce(f.requester.address,s.value.nonce),true);
    assert.equal(f.execution.interface.parseLog(r.logs[0]).name,'ActionReserved');
  });
  it('requires R3 human approval from a third account with two organizations',async function () {
    const value=await H.intent(f,3);
    await denied(()=>H.signedIntent(f,value,[f.biz,f.security]).then(s=>H.reserve(f,s)),'InvalidApproval');
    await (await H.reserve(f,await H.signedIntent(f,value))).wait(); assert.equal(await status(value),1n);
  });
  it('rejects same-organization approvals and duplicate signatures',async function () {
    await change(encode(0,[f.security.address,label('org','OrgA_Business'),true]));
    const s=await live(); await denied(()=>H.reserve(f,s),'InvalidApproval');
    await change(encode(0,[f.security.address,label('org','OrgB_Security'),true]));
    s.approvals.push(s.approvals[0]); await denied(()=>H.reserve(f,s),'InvalidApproval');
  });
  it('finds a valid role assignment without double-counting multi-role accounts',async function () {
    await role(f.biz,'HUMAN_APPROVER',true); await role(f.human,'BUSINESS_APPROVER',true);
    const value=await H.intent(f,3),s=await H.signedIntent(f,value,[f.biz,f.security,f.human]);
    await (await H.reserve(f,s)).wait();
    const other=await H.intent(f,3); await denied(()=>H.signedIntent(f,other,[f.biz,f.security,f.biz]).then(s=>H.reserve(f,s)),'InvalidApproval');
  });
  it('rejects invalid extra, requester, agent and tool-signer approvals',async function () {
    for (const actor of [f.requester,f.agent,f.mailTool]) await role(actor,'BUSINESS_APPROVER',true);
    for(const actor of [f.requester,f.agent,f.mailTool,f.outsider]) {
      const value=await H.intent(f); const s=await H.signedIntent(f,value,[f.biz,f.security,actor]);
      await denied(()=>H.reserve(f,s),'InvalidApproval');
    }
  });
  it('rejects wrong requester, forged signatures, cross-chain/domain and high-s',async function () {
    let s=await live(); s.requesterSignature=s.approvals[0].signature; await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    for(const domain of [{chainId:1},{verifyingContract:f.outsider.address},{version:'2'}]) {
      s=await H.signedIntent(f,await H.intent(f),undefined,domain); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    }
    s=await live(); s.approvals[0].signature='0x1234'; await denied(()=>H.reserve(f,s));
    s=await live(); const bytes=ethers.getBytes(s.requesterSignature); const n=0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141n;
    const high=n-BigInt(ethers.hexlify(bytes.slice(32,64))); s.requesterSignature=ethers.concat([bytes.slice(0,32),ethers.toBeHex(high,32),ethers.toBeHex(bytes[64]===27?28:27,1)]);
    await denied(()=>H.reserve(f,s),'ECDSAInvalidSignatureS');
  });
  for(const field of ['paramsCommit','taskId','nonce','expiresAt']) it(`rejects signed ${field} tampering without consuming nonce`,async function () {
    const s=await live(); s.value[field]=typeof s.value[field]==='bigint'?s.value[field]-1n:ethers.hexlify(ethers.randomBytes(32));
    await denied(()=>H.reserve(f,s),'InvalidAuthorization'); assert.equal(await f.execution.usedNonce(f.requester.address,s.value.nonce),false);
  });
  it('enforces expiry-exclusive, future issuance, lifetime, schema, nonzero and risk',async function () {
    const now=BigInt((await hre.ethers.provider.getBlock('latest')).timestamp);
    for(const overrides of [{issuedAt:now-10n,expiresAt:now},{issuedAt:now+100n,expiresAt:now+120n},{issuedAt:now,expiresAt:now+121n},{schemaVersion:2},{paramsCommit:ethers.ZeroHash},{risk:1}]) {
      const s=await live(2,overrides); await denied(()=>H.reserve(f,s)); assert.equal(await status(s.value),0n);
    }
  });
  it('never releases nonce/actionId after reservation and isolates requester nonces',async function () {
    const first=await live(2,{nonce:9007199254740993n}); await (await H.reserve(f,first)).wait();
    await denied(()=>H.reserve(f,first),'AlreadyReserved');
    const other=await live(2,{nonce:first.value.nonce}); await denied(()=>H.reserve(f,other),'AlreadyReserved');
    const sameId=await live(2,{actionId:first.value.actionId}); await denied(()=>H.reserve(f,sameId),'AlreadyReserved');
    await change(rule(2,false)); await change(rule(2,true));
    await denied(()=>H.reserve(f,other),'AlreadyReserved');
    assert.equal(await f.execution.usedNonce(f.outsider.address,first.value.nonce),false);
  });
  it('checks current revoked role, scope, agent binding and policy epoch',async function () {
    const s=await live(); await role(f.security,'SECURITY_APPROVER',false); await denied(()=>H.reserve(f,s),'InvalidApproval');
    await role(f.security,'SECURITY_APPROVER',true); await change(encode(2,[f.biz.address,scopeMail,false])); await denied(()=>H.reserve(f,s),'InvalidApproval');
    await change(encode(2,[f.biz.address,scopeMail,true]),encode(3,[f.requester.address,f.agent.address,false])); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    await change(encode(3,[f.requester.address,f.agent.address,true]),rule(2,false)); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    await change(rule(2,true)); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    const fresh=await live(); await (await H.reserve(f,fresh)).wait();
  });
  it('rejects signer-wide revocation and requester scope/role revocation',async function () {
    const s=await live(); await change(encode(0,[f.security.address,label('org','OrgB_Security'),false])); await denied(()=>H.reserve(f,s),'InvalidApproval');
    await change(encode(0,[f.security.address,label('org','OrgB_Security'),true]),encode(2,[f.requester.address,scopeMail,false])); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
    await change(encode(2,[f.requester.address,scopeMail,true]),encode(1,[f.requester.address,label('role','REQUESTER'),false])); await denied(()=>H.reserve(f,s),'InvalidAuthorization');
  });
  it('restricts audit state updates to the immutable AuditRegistry',async function () {
    const value=await booked(); await denied(()=>f.execution.recordAuditOutcome(value.actionId,0),'AuditOnly');
  });
});

describe('Phase 5 AuditRegistry: bound signed receipts and monotone state',function () {
  for(const [outcome,next] of [[0,3n],[1,4n],[2,5n]]) it(`finalizes outcome ${outcome}, idempotently returns identical receipt`,async function () {
    const value=await booked(),r=await H.receipt(f,value,{outcome});
    await (await f.audit.finalize(r.data,r.signature)).wait(); assert.equal(await status(value),next);
    const repeat=await (await f.audit.finalize(r.data,r.signature)).wait(); assert.equal(repeat.logs.length,0);
    const conflict=await H.receipt(f,value,{outcome}); await denied(()=>f.audit.finalize(conflict.data,conflict.signature),'InvalidReceipt');
    await denied(()=>f.audit.connect(f.reconciler).markUnknown(value.actionId,ethers.id('reason')),'InvalidState');
    assert.equal(await f.execution.usedNonce(f.requester.address,value.nonce),true);
  });
  it('accepts late genuine signed evidence after authorization expiry or policy pause/revoke',async function () {
    const value=await booked(); await hre.network.provider.send('evm_increaseTime',[200]); await hre.network.provider.send('evm_mine');
    await change(rule(2,false)); await (await f.policy.connect(f.govA).emergencyPause()).wait();
    const r=await H.receipt(f,value); await (await f.audit.finalize(r.data,r.signature)).wait(); assert.equal(await status(value),3n);
  });
  it('rejects forged/other-tool/revoked/currently unbound tool signatures',async function () {
    const value=await booked();
    for(const signer of [f.outsider,f.deleteTool]) {const r=await H.receipt(f,value,{},signer); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidToolSigner');}
    const r=await H.receipt(f,value); await role(f.mailTool,'TOOL_SIGNER',false); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidToolSigner');
    await role(f.mailTool,'TOOL_SIGNER',true); await change(encode(4,[label('tool','mail.send'),f.mailTool.address,false])); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidToolSigner');
    await change(encode(4,[label('tool','mail.send'),f.mailTool.address,true]),encode(0,[f.mailTool.address,label('org','OrgA_Business'),false])); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidToolSigner');
  });
  it('rejects mismatched commitments, future/preissued time, schema and UNKNOWN finalize',async function () {
    const value=await booked(),now=BigInt((await hre.ethers.provider.getBlock('latest')).timestamp);
    for(const overrides of [{paramsCommit:ethers.id('wrong')},{resultCommit:ethers.ZeroHash},{evidenceIndexCommit:ethers.ZeroHash},{schemaVersion:2},{outcome:3},{executedAt:value.issuedAt-1n},{executedAt:now+100n}]) {
      const r=await H.receipt(f,value,overrides); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidReceipt');
    }
    const r=await H.receipt(f,value); r.data.resultCommit=ethers.id('tamper'); await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidToolSigner');
    assert.equal(await status(value),1n);
  });
  it('requires actual reservation and rejects replay into another action',async function () {
    const value=await H.intent(f),r=await H.receipt(f,value); await denied(()=>f.audit.finalize(r.data,r.signature));
    await (await H.reserve(f,await H.signedIntent(f,value))).wait(); const other=await booked();
    const replay=await H.receipt(f,value);
    replay.data.actionId=other.actionId; replay.data.paramsCommit=other.paramsCommit;
    await denied(()=>f.audit.finalize(replay.data,replay.signature),'InvalidToolSigner');
  });
  it('separates RESERVED/finalize from UNKNOWN/reconcile and preserves uncertainty evidence',async function () {
    const value=await booked(),r=await H.receipt(f,value); const reason=ethers.id('uncertain test observation');
    await denied(()=>f.audit.markUnknown(value.actionId,reason),'Unauthorized');
    await denied(()=>f.audit.reconcile(r.data,r.signature),'InvalidState');
    await (await f.audit.connect(f.reconciler).markUnknown(value.actionId,reason)).wait(); assert.equal(await status(value),2n);
    assert.equal(await f.audit.unknownReason(value.actionId),reason);
    await denied(()=>live(2,{nonce:value.nonce}).then(s=>H.reserve(f,s)),'AlreadyReserved');
    await denied(()=>f.audit.finalize(r.data,r.signature),'InvalidState');
    const done=await (await f.audit.reconcile(r.data,r.signature)).wait(); assert.equal(await status(value),3n);
    assert.deepEqual(done.logs.map(l=>f.audit.interface.parseLog(l).name),['ActionReconciled','ActionFinalized']);
    assert.equal(await f.audit.unknownReason(value.actionId),reason); assert.equal(await f.execution.usedNonce(f.requester.address,value.nonce),true);
  });
});
});
