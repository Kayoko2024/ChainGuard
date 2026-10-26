const fs = require('node:fs');
const path = require('node:path');
const { ethers } = require('ethers');
const root = path.resolve(__dirname, '../..');
const protocol = JSON.parse(fs.readFileSync(path.join(root, 'spec/eip712.json')));
const govSpec = JSON.parse(fs.readFileSync(path.join(root, 'spec/phase5/governance.json')));
const abi = ethers.AbiCoder.defaultAbiCoder();
const label = (kind, value) => ethers.id(`ChainGuard/${kind}/${value}`);
const scopeMail = label('scope', 'ORG_A_INTERNAL_MAIL');
const scopeDelete = label('scope', 'ORG_A_DISPOSABLE_DOCS');
const encode = (kind, values) => ({kind, data: kind === 6 ? '0x' : abi.encode(govSpec.payloads[kind].abi, values)});
function rule(risk, enabled = true, lifetime = risk === 2 ? 120 : 60) {
  return encode(5, [label('policy', risk === 2 ? 'POLICY_R2_MAIL' : 'POLICY_R3_DELETE'),
    label('tool', risk === 2 ? 'mail.send' : 'doc.delete'), risk === 2 ? scopeMail : scopeDelete, lifetime, risk, enabled]);
}
function artifact(name) { return JSON.parse(fs.readFileSync(path.join(root, `artifacts/contracts/${name}.sol/${name}.json`))); }
async function deploy(deployer) {
  const orgA = label('org', 'OrgA_Business'), orgB = label('org', 'OrgB_Security');
  return async (govA, govB) => {
    const make = (name, args) => new ethers.ContractFactory(artifact(name).abi, artifact(name).bytecode, deployer).deploy(...args);
    const policy = await make('PolicyRegistry', [govA.address, orgA, govB.address, orgB]);
    await policy.waitForDeployment();
    const nextNonce = await deployer.getNonce('pending');
    const predictedAudit = ethers.getCreateAddress({from: await deployer.getAddress(), nonce: nextNonce + 1});
    const execution = await make('ExecutionRegistry', [await policy.getAddress(), predictedAudit]);
    await execution.waitForDeployment();
    const audit = await make('AuditRegistry', [await policy.getAddress(), await execution.getAddress(), 0]);
    await audit.waitForDeployment();
    if ((await audit.getAddress()).toLowerCase() !== predictedAudit.toLowerCase()) throw Error('Audit deployment nonce changed');
    return {policy, execution, audit};
  };
}
async function govEnvelope(f, changes, options = {}) {
  const now = BigInt((await f.policy.runner.provider.getBlock('latest')).timestamp);
  const message = {changesHash: ethers.keccak256(abi.encode([govSpec.change_abi], [changes])),
    nonce: options.nonce ?? await f.policy.governanceEpoch(), governanceEpoch: options.epoch ?? await f.policy.governanceEpoch(),
    issuedAt: options.issuedAt ?? now, expiresAt: options.expiresAt ?? now + 3600n};
  const domain = {name: 'ChainGuard PolicyRegistry', version: '1',
    chainId: (await f.policy.runner.provider.getNetwork()).chainId, verifyingContract: await f.policy.getAddress()};
  const signatures = await Promise.all((options.signers ?? [f.govA, f.govB]).map(s => s.signTypedData(domain, govSpec.types, message)));
  return {changes, message, domain, signatures};
}
function submitGov(f, e) {
  const m = e.message;
  return f.policy.executeGovernance(e.changes, m.nonce, m.governanceEpoch, m.issuedAt, m.expiresAt, e.signatures);
}
async function govern(f, changes, options) { const e = await govEnvelope(f, changes, options); return (await submitGov(f, e)).wait(); }
function registration(f) {
  const orgA = label('org', 'OrgA_Business'), orgB = label('org', 'OrgB_Security');
  const entries = [[f.requester,orgA,'REQUESTER'],[f.agent,orgA,'AGENT'],[f.biz,orgA,'BUSINESS_APPROVER'],
    [f.security,orgB,'SECURITY_APPROVER'],[f.human,orgA,'HUMAN_APPROVER'],[f.mailTool,orgA,'TOOL_SIGNER'],
    [f.deleteTool,orgA,'TOOL_SIGNER'],[f.reconciler,orgB,'RECONCILER']];
  return [...entries.flatMap(([s, org, role]) => [encode(0,[s.address,org,true]), encode(1,[s.address,label('role',role),true]),
    encode(2,[s.address,scopeMail,true]), encode(2,[s.address,scopeDelete,true])]),
    encode(3,[f.requester.address,f.agent.address,true]),
    encode(4,[label('tool','mail.send'),f.mailTool.address,true]),
    encode(4,[label('tool','doc.delete'),f.deleteTool.address,true]),rule(2),rule(3)];
}
async function intent(f, risk = 2, overrides = {}) {
  const now = BigInt((await f.execution.runner.provider.getBlock('latest')).timestamp);
  const policyId = label('policy',risk === 2 ? 'POLICY_R2_MAIL' : 'POLICY_R3_DELETE');
  return {schemaVersion:1, actionId:ethers.hexlify(ethers.randomBytes(32)), taskId:ethers.hexlify(ethers.randomBytes(32)),
    requester:f.requester.address, agent:f.agent.address, toolId:label('tool',risk === 2 ? 'mail.send' : 'doc.delete'),
    resourceScope:risk === 2 ? scopeMail : scopeDelete, paramsCommit:ethers.hexlify(ethers.randomBytes(32)), policyId,
    policyEpoch:(await f.policy.getEffectiveRule(policyId)).policyEpoch, nonce:BigInt(ethers.hexlify(ethers.randomBytes(8))),
    issuedAt:now, expiresAt:now + (risk === 2 ? 120n : 60n), risk,...overrides};
}
async function signedIntent(f, value, approvers, domainOverride = {}) {
  const domain = {name:'ChainGuard ExecutionRegistry',version:'1',
    chainId:(await f.execution.runner.provider.getNetwork()).chainId,verifyingContract:await f.execution.getAddress(),...domainOverride};
  const types = {ActionIntent:protocol.types.ActionIntent};
  return {value, requesterSignature:await f.requester.signTypedData(domain,types,value),
    approvals:await Promise.all((approvers ?? (value.risk === 3 ? [f.biz,f.security,f.human] : [f.biz,f.security])).map(async s => ({signature:await s.signTypedData(domain,types,value)})))};
}
function reserve(f, s) { return f.execution.reserve(s.value,s.requesterSignature,s.approvals); }
async function receipt(f, value, overrides = {}, signer = f.mailTool) {
  const now = BigInt((await f.audit.runner.provider.getBlock('latest')).timestamp);
  const data = {schemaVersion:1,actionId:value.actionId,paramsCommit:value.paramsCommit,
    resultCommit:ethers.hexlify(ethers.randomBytes(32)),evidenceIndexCommit:ethers.hexlify(ethers.randomBytes(32)),
    executedAt:now,outcome:0,...overrides};
  const domain = {name:'ChainGuard AuditRegistry',version:'1',chainId:(await f.audit.runner.provider.getNetwork()).chainId,verifyingContract:await f.audit.getAddress()};
  return {data,signature:await signer.signTypedData(domain,{ExecutionReceipt:protocol.types.ExecutionReceipt},data)};
}
module.exports = {ethers,root,protocol,govSpec,abi,label,encode,rule,artifact,deploy,govEnvelope,submitGov,govern,registration,intent,signedIntent,reserve,receipt,scopeMail,scopeDelete};
