const assert=require('node:assert/strict');
const hre=require('hardhat');
const H=require('../../scripts/lib/phase5.cjs');
const {ethers,label,encode}=H;
const types={RepositoryRuleChange:[['repositoryHash','bytes32'],['enabled','bool'],['nonce','uint64'],['epoch','uint64'],['issuedAt','uint64'],['expiresAt','uint64']].map(([name,type])=>({name,type}))};
const repo=n=>ethers.id('ChainGuard/github/repository/'+n);
describe('Additive GitHub repository policy',function(){
 let p,r,a,b,other,domain;
 beforeEach(async()=>{
  [a,b,other]=await hre.ethers.getSigners();
  p=await(await hre.ethers.getContractFactory('PolicyRegistry')).deploy(a.address,label('org','A'),b.address,label('org','B'));
  r=await(await hre.ethers.getContractFactory('RepositoryReadPolicy')).deploy(await p.getAddress());
  domain={name:'ChainGuard RepositoryReadPolicy',version:'1',chainId:31337,verifyingContract:await r.getAddress()};
 });
 async function envelope(overrides={},signers=[a,b],d=domain){
  const now=(await hre.ethers.provider.getBlock('latest')).timestamp;
  const m={repositoryHash:repo('microsoft/vscode'),enabled:true,nonce:await r.epoch(),epoch:await r.epoch(),issuedAt:now,expiresAt:now+3600,...overrides};
  return {m,s:await Promise.all(signers.map(s=>s.signTypedData(d,types,m)))};
 }
 const submit=e=>r.setRepository(...Object.values(e.m),...e.s);
 async function denied(fn){await assert.rejects(async()=>{const x=await fn();if(x.wait)await x.wait();});}
 it('defaults deny; independent signatures enable only one exact repository',async()=>{
  await denied(()=>r.requireRepository(repo('microsoft/vscode')));
  const e=await envelope();assert.equal(await r.ruleDigest(...Object.values(e.m)),ethers.TypedDataEncoder.hash(domain,types,e.m));
  await(await submit(e)).wait();assert.equal(await r.requireRepository(repo('microsoft/vscode')),2n);
  await denied(()=>r.requireRepository(repo('facebook/react')));assert.equal(await r.repositoryAllowed(repo('facebook/react')),false);
 });
 it('rejects duplicate, same-organization and unauthorized signers',async()=>{
  await H.govern({policy:p,govA:a,govB:b},[encode(0,[other.address,label('org','A'),true]),encode(1,[other.address,label('role','GOVERNANCE_ADMIN'),true])]);
  for(const signers of [[a,a],[a,other]]){const e=await envelope({},signers);await denied(()=>submit(e));}
 });
 it('rejects changed repository, replay, stale epoch, expired and wrong-domain signatures',async()=>{
  let e=await envelope();e.m.repositoryHash=repo('facebook/react');await denied(()=>submit(e));
  e=await envelope({},[a,b],{...domain,chainId:1});await denied(()=>submit(e));
  e=await envelope({expiresAt:1});await denied(()=>submit(e));
  e=await envelope();await(await submit(e)).wait();await denied(()=>submit(e));
  e=await envelope({epoch:1,nonce:99});await denied(()=>submit(e));
 });
 it('rejects a currently revoked signer even with a previously valid signature',async()=>{
  await H.govern({policy:p,govA:a,govB:b},[encode(0,[other.address,label('org','C'),true]),encode(1,[other.address,label('role','GOVERNANCE_ADMIN'),true])]);
  const e=await envelope({},[a,other]);
  await H.govern({policy:p,govA:a,govB:b},[encode(1,[other.address,label('role','GOVERNANCE_ADMIN'),false])]);
  await denied(()=>submit(e));
 });
 it('revocation and upstream emergency pause immediately deny reads',async()=>{
  await(await submit(await envelope())).wait();await(await submit(await envelope({enabled:false}))).wait();
  await denied(()=>r.requireRepository(repo('microsoft/vscode')));
  await(await submit(await envelope())).wait();await(await p.emergencyPause()).wait();
  await denied(()=>r.requireRepository(repo('microsoft/vscode')));await denied(async()=>submit(await envelope()));
 });
});
