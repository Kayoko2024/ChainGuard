import {chooseTask} from './navigation.mjs';
// Actual UI regression, no new tasks, approvals, model calls, or tool dispatch.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const [configPath,out]=process.argv.slice(2);
const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
const root=config.repo;
const access=fs.readFileSync(path.join(path.dirname(configPath),'access.local.txt'),'utf8');
const passwords=Object.fromEntries(access.split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const business=`http://127.0.0.1:${config.port}`;
const auditConfig=JSON.parse(fs.readFileSync(config.audit_config,'utf8'));
const auditUrl=`http://127.0.0.1:${auditConfig.port}`;
assert.ok(!fs.existsSync(out),'Use a new output path');fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',real_http:true,fixture_routes:false,business_writes:[],checks:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
async function layout(page,width,height){await page.setViewportSize({width,height});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'horizontal page overflow');}
function observe(page){page.on('pageerror',e=>report.javascript_errors.push(e.message));page.on('request',r=>{if(r.url().startsWith(business)&&r.method()!=='GET')report.business_writes.push({path:new URL(r.url()).pathname,method:r.method()});});}
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}});observe(page);
 await page.goto(business);await page.getByRole('heading',{name:'进入工作空间',exact:true}).waitFor();
 await page.screenshot({path:path.join(out,'business-login.png')});
 await layout(page,390,844);await page.screenshot({path:path.join(out,'business-login-mobile.png')});
 await page.getByLabel('登录密码').fill('invalid-local-test-password');await page.getByRole('button',{name:'登录',exact:true}).click();await page.getByRole('alert').waitFor();
 await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 await layout(page,1500,1000);await page.locator('.task').first().waitFor();
 const response=await page.request.get(business+'/ops/v1/tasks');const before=(await response.json()).tasks;
 assert.ok(before.length>0,'Existing tasks are required for read-only regression');
 const finalized=before.find(t=>t.display_state==='FINALIZED_OK');assert.ok(finalized,'An existing genuine finalized task is required');
 await layout(page,1500,1000);
 await page.getByRole('button',{name:'新建会话',exact:true}).click();await page.getByLabel('任务内容').evaluate(e=>{if(document.activeElement!==e)throw Error('Task input did not receive focus');});
 await page.getByLabel('搜索任务').fill('no-matching-ui-review');await page.getByText('没有匹配任务',{exact:true}).waitFor();await page.getByLabel('搜索任务').fill('');
 await chooseTask(page,finalized.id,{details:true});
 await page.getByTestId('workflow-step').filter({hasText:'已有链上终态'}).waitFor();
 await page.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await page.locator('.review').waitFor();
 await page.getByRole('button',{name:'查看真实沙箱邮件',exact:true}).click();await page.locator('.mail article').first().waitFor();
 const mailbox=await(await page.request.get(business+`/ops/v1/tasks/${finalized.id}/mailbox`)).json();
 assert.equal(mailbox.status,'VERIFIED');assert.equal(mailbox.mail_count,1);
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'business-desktop.png'),fullPage:true});
 await layout(page,390,844);await page.screenshot({path:path.join(out,'business-mobile.png'),fullPage:true});
 const expired=before.find(t=>t.display_state==='APPROVAL_EXPIRED');
 if(expired){await chooseTask(page,expired.id,{details:true});await page.getByTestId('workflow-step').filter({hasText:'动作已过期'}).waitFor();assert.ok(await page.getByTestId('reserve-execute').isDisabled());report.checks.push('expired reservation disabled');}
 report.checks.push('real requester login, task search, focus, review, existing MIME SHA/signature verification');
 const observer=await browser.newPage({viewport:{width:1500,height:1000}});observe(observer);
 await observer.goto(auditUrl);await observer.getByRole('heading',{name:'动作审计',exact:true}).waitFor();
 await observer.getByLabel('搜索动作').fill(finalized.record.action_id);await observer.locator('.row-link').first().click();
 const verificationResponse=observer.waitForResponse(r=>r.url().endsWith(`/audit-api/v1/actions/interactive-${finalized.id.slice(2)}/verify`));
 await observer.getByRole('button',{name:'实时核验',exact:true}).click();
 const observedVerification=await(await verificationResponse).json();report.ui_verification_response=observedVerification;save();
 assert.equal(observedVerification.status,'VERIFIED',JSON.stringify({status:observedVerification.status,error:observedVerification.error_code,reason:observedVerification.reason}));
 await observer.getByTestId('verification-status').filter({hasText:'实时证据一致'}).waitFor({timeout:60000});
 const publicRows=(await(await observer.request.get(auditUrl+'/audit-api/v1/actions')).json()).actions;
 const entry=publicRows.find(a=>a.action_id===finalized.record.action_id);
 const verified=await(await observer.request.get(auditUrl+`/audit-api/v1/actions/${entry.entry_id}/verify`)).json();
 assert.equal(verified.status,'VERIFIED');assert.ok(verified.transactions.every(t=>t.node_receipts===4));
 assert.equal(new Set(verified.approvals.map(a=>a.organization)).size,2);
 report.verified_action={action_id:finalized.record.action_id,entry_id:entry.entry_id,status:verified.status,transactions:verified.transactions,organizations:verified.approvals.map(a=>a.organization_label)};
 await observer.getByLabel('搜索动作').fill('');
 await observer.screenshot({path:path.join(out,'audit-desktop.png'),fullPage:true});
 await layout(observer,390,844);await observer.screenshot({path:path.join(out,'audit-mobile.png'),fullPage:true});
 await observer.getByLabel('搜索动作').fill('no-such-ui-record');await observer.getByText('没有匹配记录',{exact:true}).waitFor();await observer.getByLabel('搜索动作').fill('');
 await observer.getByRole('button',{name:'C · 联盟链',exact:true}).click();assert.ok((await observer.locator('tbody .group').allTextContents()).every(t=>t==='C'));
 report.checks.push('four-node real audit, separate organizations, group filter and search, desktop/mobile overflow');
 const forbidden=await observer.request.post(auditUrl+'/ops/v1/tasks',{data:{}});assert.ok([404,405].includes(forbidden.status()));report.checks.push('audit write route absent');
 for(const role of ['biz','security']){const ctx=await browser.newContext();const p=await ctx.newPage();observe(p);await p.goto(business);await p.getByLabel('登录身份').selectOption(role);await p.getByLabel('登录密码').fill(passwords[role]);await p.getByRole('button',{name:'登录',exact:true}).click();await p.locator('.identity').waitFor();await p.locator('.task').first().waitFor();assert.equal(await p.getByLabel('任务内容').count(),0);await p.locator('.task').filter({has:p.locator(`code[title="${finalized.id}"]`)}).click();await p.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await p.locator('.review').waitFor();assert.equal(await p.getByTestId('reserve-execute').count(),0);await p.getByRole('button',{name:'退出',exact:true}).click();await p.getByRole('heading',{name:'进入工作空间',exact:true}).waitFor();await ctx.close();}
 report.checks.push('independent approver sessions cannot create or execute; logout works');
 const after=(await(await page.request.get(business+'/ops/v1/tasks')).json()).tasks;
 assert.deepEqual(after.map(t=>t.id).sort(),before.map(t=>t.id).sort());
 for(const original of before){const current=after.find(t=>t.id===original.id);for(const kind of ['MODEL_EXCHANGE','AGENT_ATTEMPT','RESERVE_REQUEST'])assert.equal(current.events.filter(e=>e.kind===kind).length,original.events.filter(e=>e.kind===kind).length,`${kind} changed during read-only UI check`);assert.equal(current.record?.reservation_evidence?.tx_hash,original.record?.reservation_evidence?.tx_hash);assert.equal(current.record?.finalization_evidence?.tx_hash,original.record?.finalization_evidence?.tx_hash);}
 assert.ok(report.business_writes.every(r=>['/ops/v1/login','/ops/v1/logout'].includes(r.path)));
 assert.equal(report.javascript_errors.length,0);report.status='PASS';report.existing_task_count=before.length;report.created_tasks=0;report.new_model_calls=0;report.new_tool_dispatches=0;save();console.log('PASS: actual UI, roles, original MIME and four-node audit; zero new tasks or mail');
}catch(e){report.status='FAIL';report.failure=e.message;save();throw e;}finally{await browser.close();}
