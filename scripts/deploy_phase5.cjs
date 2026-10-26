// Real Besu deployment/contract integration. No gateway or sensitive tool dispatch.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const H = require('./lib/phase5.cjs');
const {ethers,root,label,encode,rule} = H;
const stamp = new Date().toISOString().replace(/[:.]/g,'-');
const outArg = process.argv.indexOf('--out');
const out = path.resolve(root,outArg < 0 ? `results/phase5/runs/${stamp}` : process.argv[outArg+1]);
const resultsRoot = path.join(root,'results','phase5') + path.sep;
if (!out.startsWith(resultsRoot)) throw Error('--out must be a new results/phase5 subdirectory');
if (fs.existsSync(out)) throw Error('Output exists; choose a new directory to preserve evidence');
fs.mkdirSync(out,{recursive:true});
const report = {status:'RUNNING',recordedAt:new Date().toISOString(),chainId:20261026,
  scope:'contract integration only; signed receipt fixtures do not assert mail/delete execution',transactions:[],checks:[]};
const json = data => JSON.stringify(data,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
const write = (file,data) => fs.writeFileSync(path.join(out,file),json(data));
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const providers = [8545,8546,8547,8548].map(port=>{
  const p=new ethers.JsonRpcProvider(`http://127.0.0.1:${port}`,undefined,{cacheTimeout:-1,batchMaxCount:1});
  p.pollingInterval=250; return p;
});
const gas = {gasPrice:0n,gasLimit:8000000n};
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
async function health() {
  const expected=JSON.parse(fs.readFileSync(path.join(root,'.local/phase4/network/deployment.json')));
  const rows=await Promise.all(providers.map(async (p,i)=>{
    const chainId=Number(await p.send('eth_chainId',[])),genesis=await p.send('eth_getBlockByNumber',['0x0',false]);
    const row={rpc:`http://127.0.0.1:${8545+i}`,chainId,genesis:genesis.hash,
      height:Number(await p.send('eth_blockNumber',[])),peers:Number(await p.send('net_peerCount',[])),
      validators:await p.send('qbft_getValidatorsByBlockNumber',['latest']),enode:await p.send('net_enode',[]),
      syncing:await p.send('eth_syncing',[]),client:await p.send('web3_clientVersion',[])};
    assert.equal(row.chainId,20261026); assert.equal(row.peers,3); assert.equal(row.syncing,false);
    assert.match(row.client,/besu\/v25\.10\.0\//);
    assert.equal(row.enode.split('?')[0],expected.enodes[i]);
    assert.deepEqual(row.validators.map(x=>x.toLowerCase()).sort(),expected.validators.map(x=>x.toLowerCase()).sort());
    return row;
  }));
  assert.equal(new Set(rows.map(r=>r.genesis)).size,1);
  const commonHeight=Math.min(...rows.map(r=>r.height));
  const blocks=await Promise.all(providers.map(p=>p.send('eth_getBlockByNumber',[ethers.toQuantity(commonHeight),false])));
  assert.equal(new Set(blocks.map(b=>b.hash)).size,1);
  return {nodes:rows,commonHeight,commonHash:blocks[0].hash};
}
async function recordTx(name,send,expectedStatus=1) {
  const tx=await send();
  // Persist immediately after broadcast; if waiting fails, never silently rebroadcast.
  const item={name,hash:tx.hash,status:'BROADCAST',expectedStatus}; report.transactions.push(item); write('report.json',report);
  let receipt;
  try {receipt=await tx.wait(1,60000);} catch(e) {if(!e.receipt) throw e;receipt=e.receipt;}
  assert.equal(receipt.status,expectedStatus,`${name}: receipt status`);
  const nodes=[];
  for(const p of providers) {
    let raw;
    const deadline=Date.now()+15000;
    do {raw=await p.send('eth_getTransactionReceipt',[tx.hash]); if(!raw) await delay(250);} while(!raw && Date.now()<deadline);
    assert.ok(raw,'missing committed receipt');
    const block=await p.send('eth_getBlockByHash',[raw.blockHash,false]);
    assert.ok(block.transactions.includes(tx.hash));
    assert.equal(block.hash,raw.blockHash);
    assert.equal(await p.send('eth_getBlockByNumber',[raw.blockNumber,false]).then(b=>b.hash),raw.blockHash);
    nodes.push(raw);
  }
  for(const row of nodes) assert.deepEqual(row,nodes[0]);
  item.status=receipt.status; item.blockNumber=receipt.blockNumber; item.blockHash=receipt.blockHash;
  item.gasUsed=receipt.gasUsed.toString();
  write(`tx-${String(report.transactions.length).padStart(2,'0')}-${name}.json`,{hash:tx.hash,nodes});
  write('report.json',report); console.log(`${name}: status=${receipt.status} block=${receipt.blockNumber} tx=${tx.hash}`);
  return receipt;
}
async function gov(f,changes) {
  const e=await H.govEnvelope(f,changes),m=e.message;
  return recordTx(`governance-${m.governanceEpoch}`,()=>f.policy.executeGovernance(changes,m.nonce,m.governanceEpoch,m.issuedAt,m.expiresAt,e.signatures,gas));
}
async function sendReserve(f,s,name,expected=1) {
  return recordTx(name,()=>f.execution.reserve(s.value,s.requesterSignature,s.approvals,gas),expected);
}
async function main() {
  report.before=await health(); write('report.json',report);
  // Existing phase4 local test-chain funding key, never printed or passed on CLI.
  const privateAccounts=JSON.parse(fs.readFileSync(path.join(root,'.local/phase4/accounts.private.json')));
  const deployer=new ethers.NonceManager(new ethers.Wallet(privateAccounts.sender,providers[0]));
  const names=['govA','govB','requester','agent','biz','security','human','mailTool','deleteTool','reconciler','outsider'];
  const localDir=path.join(root,'.local/phase5',stamp); fs.mkdirSync(localDir,{recursive:true});
  const keys=Object.fromEntries(names.map(n=>[n,ethers.Wallet.createRandom().privateKey]));
  fs.writeFileSync(path.join(localDir,'accounts.private.json'),json(keys),{mode:0o600,flag:'wx'});
  const f=Object.fromEntries(names.map(n=>[n,new ethers.Wallet(keys[n],providers[0])]));
  // Deploy manually so every constructor transaction has all four raw receipts.
  async function make(name,args) {
    const a=H.artifact(name),factory=new ethers.ContractFactory(a.abi,a.bytecode,deployer);
    const c=await factory.deploy(...args,gas);
    await recordTx(`deploy-${name}`,async()=>c.deploymentTransaction()); await c.waitForDeployment(); return c;
  }
  f.policy=await make('PolicyRegistry',[f.govA.address,label('org','OrgA_Business'),f.govB.address,label('org','OrgB_Security')]);
  const predicted=ethers.getCreateAddress({from:await deployer.getAddress(),nonce:await deployer.getNonce('pending')+1});
  f.execution=await make('ExecutionRegistry',[await f.policy.getAddress(),predicted]);
  f.audit=await make('AuditRegistry',[await f.policy.getAddress(),await f.execution.getAddress(),0]);
  assert.equal(await f.audit.getAddress(),predicted);
  report.contracts={};
  for(const [name,c] of [['PolicyRegistry',f.policy],['ExecutionRegistry',f.execution],['AuditRegistry',f.audit]]) {
    const address=await c.getAddress(); const code=await providers[0].getCode(address); assert.notEqual(code,'0x');
    for(const p of providers) assert.equal(await p.getCode(address),code);
    report.contracts[name]={address,codeHash:ethers.keccak256(code),runtimeBytes:(code.length-2)/2};
    write(`${name}.abi.json`,H.artifact(name).abi);
  }
  report.publicSigners=Object.fromEntries(names.map(n=>[n,f[n].address]));
  report.privateMaterial='ignored .local/phase5/<run timestamp>/accounts.private.json (local test identities only)';
  await gov(f,H.registration(f));
  // Only the reconciler needs to send its own transaction; all approval keys sign offline.
  await recordTx('fund-reconciler',()=>deployer.sendTransaction({to:f.reconciler.address,value:10n**15n,gasPrice:0n,gasLimit:21000n}));
  const value=await H.intent(f,2,{nonce:9007199254740993n}),signed=await H.signedIntent(f,value);
  report.intentFixture=signed;
  await sendReserve(f,signed,'reserve-R2');
  const reservation=await f.execution.getReservation(value.actionId); assert.equal(reservation.status,1n);
  assert.deepEqual([...reservation.approvers],[f.biz.address,f.security.address]);
  const domain={name:'ChainGuard ExecutionRegistry',version:'1',chainId:20261026,verifyingContract:await f.execution.getAddress()};
  assert.equal(reservation.intentHash,ethers.TypedDataEncoder.hash(domain,{ActionIntent:H.protocol.types.ActionIntent},value));
  await sendReserve(f,signed,'replay-action',0);
  await sendReserve(f,await H.signedIntent(f,await H.intent(f,2,{nonce:value.nonce})),'replay-nonce',0);
  const tampered=await H.signedIntent(f,await H.intent(f)); tampered.value.paramsCommit=ethers.id('tampered fixture commitment');
  await sendReserve(f,tampered,'tampered-params',0);
  const forged=await H.signedIntent(f,await H.intent(f),[f.biz,f.outsider]); await sendReserve(f,forged,'forged-approval',0);
  const now=BigInt((await providers[0].getBlock('latest')).timestamp);
  const expired=await H.signedIntent(f,await H.intent(f,2,{issuedAt:now-20n,expiresAt:now-1n})); await sendReserve(f,expired,'expired-intent',0);
  const pending=await H.signedIntent(f,await H.intent(f));
  await gov(f,[encode(1,[f.security.address,label('role','SECURITY_APPROVER'),false])]);
  await sendReserve(f,pending,'revoked-approval',0);
  await gov(f,[encode(1,[f.security.address,label('role','SECURITY_APPROVER'),true])]);
  const deletion=await H.signedIntent(f,await H.intent(f,3)); await sendReserve(f,deletion,'reserve-R3');
  const unknownValue=await H.intent(f),unknownSigned=await H.signedIntent(f,unknownValue); await sendReserve(f,unknownSigned,'reserve-unknown');
  await recordTx('mark-unknown',()=>f.audit.connect(f.reconciler).markUnknown(unknownValue.actionId,ethers.hexlify(ethers.randomBytes(32)),gas));
  assert.equal((await f.execution.getReservation(unknownValue.actionId)).status,2n);
  await sendReserve(f,unknownSigned,'unknown-cannot-replay',0);
  // Cryptographic fixtures only. REJECTED explicitly means no tool side effect.
  const r=await H.receipt(f,value,{outcome:2}); report.receiptFixture=r;
  await recordTx('finalize-R2-rejected-fixture',()=>f.audit.finalize(r.data,r.signature,gas));
  const conflict=await H.receipt(f,value,{outcome:0}); await recordTx('conflicting-receipt',()=>f.audit.finalize(conflict.data,conflict.signature,gas),0);
  await recordTx('idempotent-receipt',()=>f.audit.finalize(r.data,r.signature,gas));
  const unknownReceipt=await H.receipt(f,unknownValue,{outcome:2});
  await recordTx('unknown-cannot-finalize',()=>f.audit.finalize(unknownReceipt.data,unknownReceipt.signature,gas),0);
  await recordTx('reconcile-rejected-fixture',()=>f.audit.reconcile(unknownReceipt.data,unknownReceipt.signature,gas));
  const deleteReceipt=await H.receipt(f,deletion.value,{outcome:2},f.deleteTool);
  await gov(f,[encode(1,[f.deleteTool.address,label('role','TOOL_SIGNER'),false])]);
  await recordTx('revoked-tool-receipt',()=>f.audit.finalize(deleteReceipt.data,deleteReceipt.signature,gas),0);
  await gov(f,[encode(1,[f.deleteTool.address,label('role','TOOL_SIGNER'),true]),rule(3,false)]);
  await recordTx('finalize-R3-late-evidence-fixture',()=>f.audit.finalize(deleteReceipt.data,deleteReceipt.signature,gas));
  report.finalStates=[];
  for(const original of [value,deletion.value,unknownValue]) {
    for(const p of providers) {
      const e=f.execution.connect(p),a=f.audit.connect(p);
      assert.equal((await e.getReservation(original.actionId)).status,5n);
      assert.equal(await e.usedNonce(original.requester,original.nonce),true);
      assert.notEqual(await a.receiptHash(original.actionId),ethers.ZeroHash);
    }
    report.finalStates.push({actionId:original.actionId,status:'FINALIZED_REJECTED',nonce:original.nonce.toString()});
  }
  assert.equal(await f.execution.usedNonce(f.requester.address,tampered.value.nonce),false);
  report.after=await health(); assert.ok(report.after.commonHeight>report.before.commonHeight);
  report.sourceSha256={};
  for(const file of ['contracts/PolicyRegistry.sol','contracts/ExecutionRegistry.sol','contracts/AuditRegistry.sol','spec/phase5/governance.json','scripts/lib/phase5.cjs','scripts/deploy_phase5.cjs']) report.sourceSha256[file]=sha(fs.readFileSync(path.join(root,file)));
  report.status='PASS'; report.completedAt=new Date().toISOString();
  write('report.json',report); console.log(`PASS: real four-node Besu, ${report.transactions.length} transactions; evidence ${path.relative(root,out)}`);
}
main().catch(error=>{
  report.status='FAIL'; report.error={name:error.name,code:error.code,message:error.shortMessage||error.message};
  write('report.json',report); console.error(json(report.error)); process.exitCode=1;
}).finally(()=>{for(const p of providers) p.destroy();});
