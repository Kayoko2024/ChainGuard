import {openDetails} from './navigation.mjs';
// Fresh form input proves automatic audit linkage, one-org denial and real negative control.
import {chromium} from 'playwright';import assert from 'node:assert/strict';import fs from 'node:fs';
const [depPath,out]=process.argv.slice(2);assert.ok(!fs.existsSync(out));
const d=JSON.parse(fs.readFileSync(depPath,'utf8'));const passwords=Object.fromEntries(fs.readFileSync(d.access_file,'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});const report={status:'RUNNING',actual_browser:true,preexported_cases:false};
const save=()=>fs.writeFileSync(out,JSON.stringify(report,null,2));save();
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,timeout=45000){const end=Date.now()+timeout;while(Date.now()<end){const r=await fn();if(r)return r;await sleep(500);}throw Error('Actual observation timed out');}
try{
 const contexts={};const pages={};
 for(const role of ['requester','biz']){contexts[role]=await browser.newContext();const p=await contexts[role].newPage();pages[role]=p;await p.goto(d.business_url);await p.getByLabel('登录身份').selectOption(role);await p.getByLabel('登录密码').fill(passwords[role]);await p.getByRole('button',{name:'登录',exact:true}).click();await p.locator('.identity').waitFor();}
 const requester=pages.requester,biz=pages.biz;const url=d.business_url;
 const list=async()=>(await(await requester.request.get(url+'/ops/v1/tasks')).json()).tasks;
 const old=await list();const audit=await browser.newPage();await audit.goto(d.audit_url);await audit.getByRole('heading',{name:'动作审计',exact:true}).waitFor();
 const text='请调用 mail_send 给 alice@inbox.chainguard.invalid 发一封本地测试邮件。主题为“自动审计联动与审批缺失 '+new Date().toISOString()+'”，正文“仅创建待审批动作，不自动执行”。';
 await requester.getByLabel('任务内容').fill(text);await requester.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();
 const job=await until(async()=>(await list()).find(j=>!old.some(o=>o.id===j.id)));report.id=job.id;save();
 const pending=await until(async()=>{const j=(await list()).find(x=>x.id===job.id);if(j.state==='MODEL_ERROR')throw Error(j.error);return j.record?j:null;});
 report.action_id=pending.record.action_id;
 // This audit page was opened BEFORE task creation. No reload/export/script refresh.
 await audit.getByLabel('搜索动作').fill(pending.record.action_id);await audit.locator('.row-link').first().waitFor({timeout:15000});report.audit_auto_updated_without_reload=true;
 await openDetails(requester);
 await requester.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await requester.locator('.review').waitFor();
 await requester.getByText('隔离环境负例与 UNKNOWN 演示',{exact:true}).click();await requester.getByRole('button',{name:'尝试任务范围外收件人',exact:true}).click();
 const negative=await until(async()=>((await list()).find(x=>x.id===job.id)).events.find(e=>e.kind==='MANUAL_NEGATIVE_CONTROL'));
 assert.equal(negative.result.status,'DENIED');assert.equal(negative.result.error_code,'UNAUTHORIZED_SCOPE');assert.equal(negative.result.mail_before,0);assert.equal(negative.result.mail_after,0);assert.equal(negative.result.gateway_actions_before,negative.result.gateway_actions_after);report.negative_control=negative;
 await until(async()=>{const b=biz.locator('.task').filter({has:biz.locator('code',{hasText:job.id.slice(0,18)})});return await b.count()?b:null;}).then(b=>b.click());
 await biz.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await biz.locator('.review').waitFor();await biz.getByRole('button',{name:'以 业务审批 · OrgA 批准此意图',exact:true}).click();
 await until(async()=>((await list()).find(x=>x.id===job.id)).record.approval_signatures.length===1);
 await requester.getByTestId('reserve-execute').click();await requester.getByRole('alert').waitFor();
 const denied=(await list()).find(x=>x.id===job.id);assert.equal(denied.record.reservation_evidence,null);assert.equal(denied.tool_observation.mail_count,0);report.one_organization_denied={state:denied.record.state,approval_count:denied.record.approval_signatures.length,mail_count:0,no_reservation:true};
 const session=await(await requester.request.get(url+'/ops/v1/session')).json();const headers={'Origin':url,'X-CSRF-Token':session.csrf,'Idempotency-Key':job.id};
 const body={task_text:text,allowed_recipients:['alice@inbox.chainguard.invalid']};
 const same=await requester.request.post(url+'/ops/v1/tasks',{headers,data:body});assert.equal(same.status(),202);assert.equal((await same.json()).id,job.id);
 const changed=await requester.request.post(url+'/ops/v1/tasks',{headers,data:{...body,task_text:'changed'}});assert.equal(changed.status(),409);report.task_request_idempotency=true;
 const deniedRole=await requester.request.post(url+'/ops/v1/tasks/'+job.id+'/approve',{headers,data:{intent_digest:'0x'+'00'.repeat(32)}});assert.equal(deniedRole.status(),403);report.requester_cannot_approve=true;
 const write=await audit.request.post(d.audit_url+'/ops/v1/tasks',{data:body});assert.ok([404,405].includes(write.status()));report.audit_write_rejected=true;
 await requester.reload();await requester.locator('.identity').waitFor();assert.equal(((await list()).find(x=>x.id===job.id)).record.action_id,pending.record.action_id);report.refresh_preserved_original_action=true;
 report.status='PASS';save();console.log('PASS: new task auto appears in read-only audit, unauthorized and one-org calls denied with zero mail');
}catch(e){report.status='FAIL';report.failure=e.message;save();throw e;}finally{await browser.close();}
