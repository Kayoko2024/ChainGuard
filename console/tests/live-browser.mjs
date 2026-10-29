import {openDetails} from './navigation.mjs';
// Fresh UI tasks against real DeepSeek, original gateway, local MIME and four Besu.
// No route interception, mock model, historic case import or fake transaction.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const [deploymentPath,output]=process.argv.slice(2);
const deployment=JSON.parse(fs.readFileSync(deploymentPath,'utf8'));
assert.equal(deployment.status,'PASS'); assert.ok(!fs.existsSync(output),'new evidence path required');
const config=JSON.parse(fs.readFileSync(deployment.config_path,'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(deployment.access_file,'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',actual_browser:true,actual_model:'deepseek-flash',fixture_routes:false,created_tasks:[],started_at_utc:new Date().toISOString()};
const errors=[];
const save=()=>fs.writeFileSync(output,JSON.stringify(report,null,2));save();
async function pause(ms){await new Promise(resolve=>setTimeout(resolve,ms));}
async function until(fn,timeout=60000){const stop=Date.now()+timeout;let v;while(Date.now()<stop){v=await fn();if(v)return v;await pause(500);}throw Error('Actual service condition timed out');}
try{
 const pages={};
 for(const role of ['requester','biz','security']){
  const context=await browser.newContext({viewport:{width:1500,height:1000}});const p=await context.newPage();p.on('pageerror',e=>errors.push(e.message));
  await p.goto(deployment.business_url);await p.getByLabel('登录身份').selectOption(role);await p.getByLabel('登录密码').fill(passwords[role]);await p.getByRole('button',{name:'登录',exact:true}).click();
  await p.locator('.identity').waitFor();pages[role]=p;
 }
 const requester=pages.requester;
 const tasks=async()=> (await (await requester.request.get(deployment.business_url+'/ops/v1/tasks')).json()).tasks;
 async function job(id){return (await tasks()).find(t=>t.id===id);}
 async function choose(p,id){await until(async()=>{const button=p.locator('.task').filter({has:p.locator('code',{hasText:id.slice(0,18)})});return await button.count()?button:null;}).then(b=>b.click());}
 async function create(text){
  const before=new Set((await tasks()).map(t=>t.id));await requester.getByLabel('任务内容').fill(text);await requester.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();
  const t=await until(async()=>(await tasks()).find(t=>!before.has(t.id)),15000);report.created_tasks.push({id:t.id,task_text_sha256:null});save();
  const pending=await until(async()=>{const j=await job(t.id);if(j?.state==='MODEL_ERROR')throw Error('Real model failed: '+j.error);return j?.record?j:null;},60000);
  assert.equal(pending.record.state,'AWAITING_APPROVAL');return pending;
 }
 async function review(p,id){await choose(p,id);await openDetails(p);await p.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await p.locator('.review').waitFor();}
 async function demo(){if(!await requester.locator('details.demo').evaluate(el=>el.open))await requester.getByText('隔离环境负例与 UNKNOWN 演示',{exact:true}).click();}
 async function approve(id){
  for(const role of ['biz','security']){const p=pages[role];await review(p,id);await p.getByRole('button',{name:role==='biz'?'以 业务审批 · OrgA 批准此意图':'以 安全审批 · OrgB 批准此意图',exact:true}).click();
   await until(async()=>{const j=await job(id);return j.record.approval_signatures.length===(role==='biz'?1:2);},20000);}
 }
 const stamp=new Date().toISOString();
 const normal=await create('请调用 mail_send 发送一封本地测试邮件给 alice@inbox.chainguard.invalid。主题为“网页新任务 '+stamp+'”，正文为“这封邮件来自本次新输入，不是历史案例”。只提出这一条邮件动作，等待人工审批。');
 const id=normal.id;
 await review(requester,id);
 await requester.getByTestId('reserve-execute').click();
 await requester.getByRole('alert').waitFor();
 const missing=await job(id);assert.equal(missing.record.reservation_evidence,null);assert.equal(missing.tool_observation.mail_count,0);report.missing_approval={state:missing.record.state,mail_count:0,no_reservation:true};
 await demo();
 await requester.getByRole('button',{name:'尝试任务范围外收件人',exact:true}).click();
 const negative=await until(async()=>{const j=await job(id);return j.events.find(e=>e.kind==='MANUAL_NEGATIVE_CONTROL');});
 assert.equal(negative.result.status,'DENIED');
 if('mail_before' in negative.result){assert.equal(negative.result.mail_before,negative.result.mail_after);assert.equal(negative.result.gateway_actions_before,negative.result.gateway_actions_after);}
 report.unauthorized=negative;
 await approve(id);await review(requester,id);
 await until(async()=>(await requester.getByTestId('workflow-step').textContent()).includes('审批已齐，等待请求者发起链上预约'));
 assert.equal(await requester.getByTestId('reserve-execute').textContent(),'发起链上预约并执行');
 report.requester_reserve_guidance=true;
 await requester.getByTestId('reserve-execute').click();
 const final=await until(async()=>{const j=await job(id);return j?.record?.state==='FINALIZED_OK'&&j.tool_observation?.status==='VERIFIED'?j:null;},60000);
 assert.equal(final.tool_observation.mail_count,1);assert.equal(final.record.approval_signatures.length,2);assert.ok(final.record.tool_signature);
 await requester.getByRole('button',{name:'查看真实沙箱邮件',exact:true}).click();await requester.locator('.mail article').waitFor();
 const before=final.tool_observation.mail_count;await requester.getByTestId('reserve-execute').click();await pause(2000);
 const repeated=await job(id);assert.equal(repeated.tool_observation.mail_count,before);assert.equal(repeated.record.reservation_evidence.tx_hash,final.record.reservation_evidence.tx_hash);
 report.normal={id,record:final.record,tool_observation:final.tool_observation,real_model_exchanges:final.events.filter(e=>e.kind==='MODEL_EXCHANGE').length};report.replay={same_action:true,no_new_mail:true};save();
 const audit=await browser.newPage();await audit.goto(deployment.audit_url);await audit.getByLabel('搜索动作').fill(final.record.action_id);await audit.locator('.row-link').first().click();await audit.getByRole('button',{name:'实时核验',exact:true}).click();
 await audit.getByTestId('verification-status').filter({hasText:'实时证据一致'}).waitFor({timeout:45000});
 const verify=await (await audit.request.get(deployment.audit_url+'/audit-api/v1/actions/interactive-'+id.slice(2)+'/verify')).json();
 assert.equal(verify.status,'VERIFIED');assert.ok(verify.transactions.every(t=>t.node_receipts===4));assert.equal(new Set(verify.approvals.map(a=>a.organization)).size,2);report.audit=verify;save();
 // A second freshly entered task demonstrates real side effect followed by response loss.
 const unknown=await create('请调用 mail_send 给 alice@inbox.chainguard.invalid 发送一封本地邮件，主题“UNKNOWN 网页演示 '+stamp+'”，正文“用于验证丢回执后不重复发送”。只提议一条邮件动作。');
 await review(requester,unknown.id);await demo();
 await requester.getByRole('button',{name:'执行前启用真实回执丢响应',exact:true}).click();await approve(unknown.id);
 await review(requester,unknown.id);await requester.getByTestId('reserve-execute').click();
 const held=await until(async()=>{const j=await job(unknown.id);return j?.record?.state==='UNKNOWN'&&j.tool_observation?.mail_count===1?j:null;},60000);
 assert.equal(held.record.receipt,null);assert.equal(held.record.finalization_evidence,null);report.unknown={id:unknown.id,record:held.record,tool_observation:held.tool_observation};save();
 const entry='interactive-'+unknown.id.slice(2);
 // Public observer is an asynchronous projection; wait for its own observed
 // state before checking, without treating a previous snapshot as new evidence.
 await until(async()=>{const response=await audit.request.get(deployment.audit_url+'/audit-api/v1/actions/'+entry);if(!response.ok())return false;const row=await response.json();return row.state==='UNKNOWN'&&row.reservation_evidence;},20000);
 const pending=await(await audit.request.get(deployment.audit_url+'/audit-api/v1/actions/'+entry+'/verify')).json();assert.equal(pending.status,'PENDING_RECEIPT');report.unknown.audit=pending;
 // Repeating reserve on UNKNOWN must not dispatch a second tool call.
 await requester.getByTestId('reserve-execute').click();await pause(1500);assert.equal((await job(unknown.id)).tool_observation.mail_count,1);
 await requester.getByRole('button',{name:'解除丢响应并查询原回执',exact:true}).click();
 await until(async()=>{const j=await job(unknown.id);return j.events.some(e=>e.kind==='TEST_RECEIPT_LOSS'&&e.enabled===false);},20000);
 const recovered=await until(async()=>{const j=await job(unknown.id);return j?.record?.state==='FINALIZED_OK'?j:null;},60000);assert.equal(recovered.tool_observation.mail_count,1);report.recovered={record:recovered.record,tool_observation:recovered.tool_observation};
 await requester.reload();await requester.locator('.identity').waitFor();assert.equal((await job(id)).record.action_id,final.record.action_id);
 await audit.reload();assert.ok((await(await audit.request.get(deployment.audit_url+'/audit-api/v1/actions')).json()).total>=2);
 assert.equal(errors.length,0);report.status='PASS';report.javascript_errors=errors;report.refresh_persisted=true;report.finished_at_utc=new Date().toISOString();save();
 console.log('PASS: fresh browser tasks, actual model, separate approvals, MIME, ledger, replay and UNKNOWN recovery');
}catch(e){report.status='FAIL';report.failure=String(e.message);save();throw e;}finally{await browser.close();}
