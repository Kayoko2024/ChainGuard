const assert = require('node:assert/strict');
const hre = require('hardhat');
const H = require('../../scripts/lib/phase5.cjs');
const {ethers,label,encode}=H;
const types={MailApprovalWindow:[{name:'sourcePolicy',type:'address'},{name:'mailLifetime',type:'uint64'},{name:'nonce',type:'uint64'},{name:'issuedAt',type:'uint64'},{name:'expiresAt',type:'uint64'}]};
describe('Explicit 24h mail approval window (legacy protocol preserved)',function(){
 let f,source,overlay;
 async function install(signers){
  const sourcePolicy=await source.getAddress(),issuedAt=(await hre.ethers.provider.getBlock('latest')).timestamp;
  const predicted=ethers.getCreateAddress({from:f.deployer.address,nonce:await f.deployer.getNonce('pending')});
  const message={sourcePolicy,mailLifetime:86400,nonce:1,issuedAt,expiresAt:issuedAt+3600};
  const domain={name:'ChainGuard MailApprovalWindowPolicy',version:'1',chainId:31337,verifyingContract:predicted};
  const signatures=await Promise.all((signers??[f.govA,f.govB]).map(s=>s.signTypedData(domain,types,message)));
  return (await hre.ethers.getContractFactory('MailApprovalWindowPolicy',f.deployer)).deploy(sourcePolicy,1,issuedAt,issuedAt+3600,signatures);
 }
 beforeEach(async()=>{
  const s=await hre.ethers.getSigners(),names=['deployer','govA','govB','requester','agent','biz','security','human','mailTool','deleteTool','reconciler','outsider'];
  f=Object.fromEntries(names.map((n,i)=>[n,s[i]]));Object.assign(f,await(await H.deploy(f.deployer))(f.govA,f.govB));await H.govern(f,H.registration(f));
  source=f.policy;overlay=await install();await overlay.waitForDeployment();
  f.policy=new ethers.Contract(await overlay.getAddress(),source.interface,f.deployer);
  const predicted=ethers.getCreateAddress({from:f.deployer.address,nonce:await f.deployer.getNonce('pending')+1});
  f.execution=await(await hre.ethers.getContractFactory('ExecutionRegistry',f.deployer)).deploy(await overlay.getAddress(),predicted);await f.execution.waitForDeployment();
  f.audit=await(await hre.ethers.getContractFactory('AuditRegistry',f.deployer)).deploy(await overlay.getAddress(),await f.execution.getAddress(),0);await f.audit.waitForDeployment();
 });
 it('keeps original 120s/R3 60s, exposes mail 24h only, and rejects one-org/forged admission',async()=>{
  assert.equal((await source.getEffectiveRule(label('policy','POLICY_R2_MAIL'))).maxLifetime,120n);
  assert.equal((await f.policy.getEffectiveRule(label('policy','POLICY_R2_MAIL'))).maxLifetime,86400n);
  assert.equal((await f.policy.getEffectiveRule(label('policy','POLICY_R3_DELETE'))).maxLifetime,60n);
  for(const signers of [[f.govA],[f.govA,f.govA],[f.govA,f.outsider]])await assert.rejects(install(signers));
  await assert.rejects(f.policy.executeGovernance([],1,1,1,2,[]));
 });
 it('accepts exact 24h, remains executable after the former 120s limit, and blocks replay',async()=>{
  const value=await H.intent(f),s=await H.signedIntent(f,{...value,expiresAt:value.issuedAt+86400n});
  await hre.network.provider.send('evm_increaseTime',[901]);await hre.network.provider.send('evm_mine');
  await(await H.reserve(f,s)).wait();assert.equal((await f.execution.getReservation(s.value.actionId)).status,1n);
  await assert.rejects(H.reserve(f,s));
 });
 it('rejects >24h and exact expiration, including signatures tampered to extend their deadline',async()=>{
  const value=await H.intent(f),s=await H.signedIntent(f,{...value,expiresAt:value.issuedAt+86401n});
  await assert.rejects(H.reserve(f,s));
  const valid=await H.signedIntent(f,{...value,expiresAt:value.issuedAt+86400n});
  await assert.rejects(H.reserve(f,{...valid,value:{...valid.value,expiresAt:value.issuedAt+86399n}}));
  await hre.network.provider.send('evm_setNextBlockTimestamp',[Number(value.issuedAt+86400n)]);await hre.network.provider.send('evm_mine');
  await assert.rejects(H.reserve(f,valid));
 });
 it('immediately respects source role revocation, pause and tighter policy limits',async()=>{
  const value=await H.intent(f),signed=await H.signedIntent(f,{...value,expiresAt:value.issuedAt+86400n});
  const original={...f,policy:source};await H.govern(original,[encode(1,[f.biz.address,label('role','BUSINESS_APPROVER'),false])]);
  await assert.rejects(H.reserve(f,signed));
  await H.govern(original,[H.rule(2,true,60)]);assert.equal((await f.policy.getEffectiveRule(label('policy','POLICY_R2_MAIL'))).maxLifetime,60n);
  await(await source.connect(f.govA).emergencyPause()).wait();assert.equal(await f.policy.paused(),true);
 });
 it('does not accept old ExecutionRegistry domain signatures in the new deployment',async()=>{
  const legacy=await(await H.deploy(f.deployer))(f.govA,f.govB);
  const value=await H.intent(f);const signed=await H.signedIntent(f,value,undefined,{verifyingContract:await legacy.execution.getAddress()});
  await assert.rejects(H.reserve(f,signed));
 });
});
