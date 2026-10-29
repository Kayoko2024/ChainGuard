const assert=require('node:assert/strict');
const hre=require('hardhat');
const H=require('../../scripts/lib/phase5.cjs');
const {ethers,label,encode}=H;
const types={ToolReview:[['revision','bytes32'],['riskLevel','uint8'],['enabled','bool'],['nonce','uint64'],['epoch','uint64'],['issuedAt','uint64'],['expiresAt','uint64']].map(([name,type])=>({name,type}))};
const sessions={SessionGrant:[['requester','address'],['agent','address'],['taskId','bytes32'],['toolsHash','bytes32'],['nonce','uint64'],['issuedAt','uint64'],['expiresAt','uint64'],['maxCalls','uint32']].map(([name,type])=>({name,type}))};
describe('Additive tool risk / sessions / batch roots',function(){
 let f,r,anchor,domain;
 beforeEach(async()=>{
  const ss=await hre.ethers.getSigners(),names=['deployer','govA','govB','requester','agent','biz','security','human','mailTool','deleteTool','reconciler','outsider'];
  f=Object.fromEntries(names.map((n,i)=>[n,ss[i]]));Object.assign(f,await(await H.deploy(f.deployer))(f.govA,f.govB));await H.govern(f,H.registration(f));
  r=await(await hre.ethers.getContractFactory('ToolAdmissionRegistry')).deploy(await f.policy.getAddress(),label('org','OrgB_Security'));
  anchor=await(await hre.ethers.getContractFactory('LowRiskAuditAnchor')).deploy(f.deployer.address);
  domain={name:'ChainGuard ToolAdmissionRegistry',version:'1',chainId:31337,verifyingContract:await r.getAddress()};
 });
 async function review(override={},signer=f.security,d=domain){const now=(await hre.ethers.provider.getBlock('latest')).timestamp;const m={revision:ethers.id('weather'),riskLevel:1,enabled:true,nonce:await r.epoch(),epoch:await r.epoch(),issuedAt:now,expiresAt:now+300,...override};return {m,s:await signer.signTypedData(d,types,m)};}
 const submit=e=>r.review(...Object.values(e.m),e.s);
 const denied=async cb=>assert.rejects(async()=>{const tx=await cb();if(tx.wait)await tx.wait();});
 it('only OrgB security/admin can label LOW/HIGH; exact revision and generation recorded',async()=>{
  for(const s of [f.requester,f.biz,f.govA])await denied(async()=>submit(await review({},s)));
  let e=await review();assert.equal(await r.reviewDigest(...Object.values(e.m)),ethers.TypedDataEncoder.hash(domain,types,e.m));await(await submit(e)).wait();
  assert.deepEqual(Array.from(await r.tools(e.m.revision)).slice(0,3),[1n,true,1n]);
  await(await submit(await review({riskLevel:2}))).wait();assert.equal((await r.tools(e.m.revision)).riskLevel,2n);
 });
 it('rejects forged/replayed/expired/tampered review and current role revocation',async()=>{
  const e=await review();await denied(()=>submit({...e,m:{...e.m,riskLevel:2}}));await(await submit(e)).wait();await denied(()=>submit(e));
  await denied(async()=>submit(await review({expiresAt:1})));await denied(async()=>submit(await review({},f.security,{...domain,chainId:1})));
  const old=await review();await H.govern(f,[encode(1,[f.security.address,label('role','SECURITY_APPROVER'),false])]);await denied(()=>submit(old));
 });
 async function grant(overrides={}){const now=(await hre.ethers.provider.getBlock('latest')).timestamp;const m={requester:f.requester.address,agent:f.agent.address,taskId:ethers.id('task'),toolsHash:ethers.id('tools'),nonce:7,issuedAt:now,expiresAt:now+86400,maxCalls:50,...overrides};return {m,s:await f.requester.signTypedData(domain,sessions,m)};}
 it('matches SessionGrant EIP-712; rejects tampered limit, wrong signer, expiration and removed agent binding',async()=>{
  let e=await grant();assert.equal(await r.sessionDigest(e.m),ethers.TypedDataEncoder.hash(domain,sessions,e.m));assert.equal(await r.validateSession(e.m,e.s),f.requester.address);
  await denied(()=>r.validateSession({...e.m,maxCalls:500},e.s));await denied(()=>r.validateSession(e.m,'0x'+'00'.repeat(65)));
  e=await grant({expiresAt:1});await denied(()=>r.validateSession(e.m,e.s));
  e=await grant();await H.govern(f,[encode(3,[f.requester.address,f.agent.address,false])]);await denied(()=>r.validateSession(e.m,e.s));
 });
 it('publishes exactly one immutable root per batch, only by publisher',async()=>{
  const args=[ethers.id('batch'),ethers.id('root'),2,1,2];await denied(()=>anchor.connect(f.outsider).anchor(...args));
  await(await anchor.anchor(...args)).wait();await(await anchor.anchor(...args)).wait();
  assert.equal((await anchor.batches(args[0])).root,args[1]);await denied(()=>anchor.anchor(args[0],ethers.id('changed'),2,1,2));
  await denied(()=>anchor.anchor(ethers.id('bad'),args[1],51,1,51));
 });
 it('matches the shared fixed SessionGrant vector in Solidity and ethers',async()=>{
  const v=require('../../spec/vectors/session-v1.json');
  const code=await hre.ethers.provider.getCode(await r.getAddress());
  await hre.network.provider.send('hardhat_setCode',[v.domain.verifyingContract,code]);
  const fixed=await hre.ethers.getContractAt('ToolAdmissionRegistry',v.domain.verifyingContract);
  assert.equal(await fixed.sessionDigest(v.message),v.digest);
  assert.equal(ethers.TypedDataEncoder.hash(v.domain,sessions,v.message),v.digest);
  assert.equal(ethers.verifyTypedData(v.domain,sessions,v.message,v.signature).toLowerCase(),v.message.requester);
 });
});
