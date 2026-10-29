const assert=require('node:assert/strict');
const hre=require('hardhat');
const H=require('../../scripts/lib/phase5.cjs');
const {ethers,label,encode}=H;
const vector=require('../../spec/vectors/conversation-v2.json');
const types={ConversationGrant:vector.types.ConversationGrant};
describe('Conversation LOW sessions independent domain',function(){
 let f,registry,domain;
 beforeEach(async()=>{
  const ss=await hre.ethers.getSigners(),names=['deployer','govA','govB','requester','agent','biz','security','human','mailTool','deleteTool','reconciler','outsider'];
  f=Object.fromEntries(names.map((n,i)=>[n,ss[i]]));Object.assign(f,await(await H.deploy(f.deployer))(f.govA,f.govB));await H.govern(f,H.registration(f));
  registry=await(await hre.ethers.getContractFactory('ConversationSessionRegistry')).deploy(await f.policy.getAddress(),f.deployer.address);
  domain={name:'ChainGuard ConversationSessionRegistry',version:'1',chainId:31337,verifyingContract:await registry.getAddress()};
 });
 const denied=async cb=>assert.rejects(async()=>{const tx=await cb();if(tx.wait)await tx.wait();});
 async function grant(changes={}){const now=(await hre.ethers.provider.getBlock('latest')).timestamp;const m={requester:f.requester.address,agent:f.agent.address,sessionId:ethers.id('conversation'),toolsHash:ethers.id('LOW tools'),nonce:7,issuedAt:now,expiresAt:now+3600,maxCalls:50,...changes};return {m,s:await f.requester.signTypedData(domain,types,m)};}
 it('verifies signature binding and rejects tampered quota/session, expiration and revoked identity',async()=>{
  let e=await grant();assert.equal(await registry.validateGrant(e.m,e.s),f.requester.address);
  assert.equal(await registry.grantDigest(e.m),ethers.TypedDataEncoder.hash(domain,types,e.m));
  await denied(()=>registry.validateGrant({...e.m,maxCalls:51},e.s));await denied(()=>registry.validateGrant({...e.m,sessionId:ethers.id('another')},e.s));
  e=await grant({expiresAt:1});await denied(()=>registry.validateGrant(e.m,e.s));
  e=await grant();await H.govern(f,[encode(3,[f.requester.address,f.agent.address,false])]);await denied(()=>registry.validateGrant(e.m,e.s));
 });
 it('keeps immutable cumulative LOW roots, separate sessions and final closure',async()=>{
  const sid=ethers.id('s'),zero=ethers.ZeroHash,r1=ethers.id('r1'),r2=ethers.id('r2');
  await denied(()=>registry.connect(f.outsider).anchor(sid,1,r1,2,zero,false));
  await(await registry.anchor(sid,1,r1,2,zero,false)).wait();await(await registry.anchor(sid,1,r1,2,zero,false)).wait();
  await denied(()=>registry.anchor(sid,1,r2,2,zero,false));await denied(()=>registry.anchor(sid,2,r2,3,zero,false));
  await(await registry.anchor(sid,2,r2,3,r1,false)).wait();await(await registry.anchor(sid,3,r2,3,r2,true)).wait();
  await denied(()=>registry.anchor(sid,4,ethers.id('bad'),4,r2,false));
  await(await registry.anchor(ethers.id('other'),1,r1,1,zero,false)).wait();assert.equal(await registry.latest(sid),3n);
 });
 it('matches frozen additive Python/Solidity vector without modifying V1',async()=>{
  await hre.network.provider.send('hardhat_setCode',[vector.domain.verifyingContract,await hre.ethers.provider.getCode(await registry.getAddress())]);
  const fixed=await hre.ethers.getContractAt('ConversationSessionRegistry',vector.domain.verifyingContract);
  assert.equal(await fixed.grantDigest(vector.message),vector.digest);
  assert.equal(ethers.TypedDataEncoder.hash(vector.domain,types,vector.message),vector.digest);
  assert.equal(ethers.verifyTypedData(vector.domain,types,vector.message,vector.signature).toLowerCase(),vector.message.requester);
 });
});
