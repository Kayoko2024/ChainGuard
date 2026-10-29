// Real Edge, real HTTP and real model/chain/tool. No route interception or clock changes.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configFile,credentialsFile,out,legacy,resumeFile]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configFile,'utf8'));
assert.ok(c.acceptance_only&&c.port===8092&&!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(credentialsFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const base='http://127.0.0.1:8092',audit='http://127.0.0.1:8093';
const report={status:'RUNNING',mocked_routes:false,clock_manipulation:false,checks:[],javascript_errors:[]},save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext(),page=await context.newPage({viewport:{width:1460,height:1000}});
page.on('pageerror',e=>report.javascript_errors.push(e.message));
const id=()=> '0x'+crypto.randomUUID().replaceAll('-','')+crypto.randomUUID().replaceAll('-','');
async function login(p,role){await p.goto(base);await p.getByLabel('登录身份').selectOption(role);await p.getByLabel('登录密码').fill(passwords[role]);await p.getByRole('button',{name:'登录',exact:true}).click();await p.locator('.identity').waitFor();}
async function detail(sid){const r=await page.request.get(base+'/ops/v1/conversations/'+sid);assert.equal(r.status(),200);return r.json();}
async function waitFor(fn,check,seconds=120){const deadline=Date.now()+seconds*1000;while(Date.now()<deadline){const value=await fn();if(check(value))return value;await page.waitForTimeout(800);}throw Error('Acceptance wait timed out; preserve original tasks and inspect evidence');}
async function submit(text,status=202){await page.getByLabel('任务内容').fill(text);const waiting=page.waitForResponse(r=>r.request().method()==='POST'&&/\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname),{timeout:45000});await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();const r=await waiting;assert.equal(r.status(),status);return {data:await r.json(),request:r.request().postDataJSON()};}
async function complete(sid,n){return waitFor(()=>detail(sid),v=>v.runs.length===n&&Boolean(v.runs[n-1].agent_output));}
try{
 await login(page,'requester');
 if(!resumeFile){await page.locator(`.task code[title="${legacy}"]`).waitFor();await page.locator('.task').filter({has:page.locator(`code[title="${legacy}"]`)}).click();await page.getByLabel('任务对话').waitFor();}
 const original=(await(await page.request.get(base+'/ops/v1/tasks/'+legacy)).json());
 let all=(await(await page.request.get(base+'/ops/v1/conversations')).json()).conversations;
 let conversation=all.find(v=>v.legacy_job_id===legacy);
 let checkpoint1,csrf;
 if(resumeFile){
  const previous=JSON.parse(fs.readFileSync(resumeFile,'utf8'));assert.equal(conversation.id,previous.session_id);
  report.resumed_from=resumeFile;report.previous_checks=[...(previous.previous_checks||[]),...previous.checks];
  assert.ok(conversation.runs.length>=3&&conversation.runs[1].conversation_grant_digest!==conversation.runs[2].conversation_grant_digest);
  await page.evaluate(sid=>localStorage.setItem('chainguard.activeConversation.v1',sid),conversation.id);await page.reload();await page.getByLabel('任务对话').first().waitFor();
  checkpoint1=previous.LOW_checkpoints?.[0]||conversation.low_status.observations.find(o=>o.batch?.count===1&&!o.batch.closed)?.batch;
  assert.ok(checkpoint1);report.session_id=conversation.id;save();
 }else{
 if(!conversation){const sent=await submit('沿用刚才的总结，先说明负责人，再调用 doc_read 重新读取 meeting-notes 核对下一步；此轮不发邮件。');conversation=sent.data;}
 const sid=conversation.id;report.session_id=sid;save();
 conversation=await complete(sid,2);
 assert.match(conversation.runs[1].agent_output,/Alice/i);assert.equal(conversation.legacy_job_id,legacy);
 assert.ok(conversation.runs[1].events.some(e=>e.kind==='AGENT_ATTEMPT'&&e.tool_name==='doc.read'&&e.tool_executed));
 assert.equal(conversation.low_grant.message.expiresAt-conversation.low_grant.message.issuedAt,60);
 const oldDigest=conversation.low_grant.digest,expires=conversation.low_grant.message.expiresAt;
 await page.reload();await page.getByLabel('任务对话').first().waitFor();assert.equal(await page.getByLabel('任务对话').count(),2);assert.equal(await page.evaluate(()=>localStorage.getItem('chainguard.activeConversation.v1')),sid);
 report.checks.push('legacy task continues in same window, actual context and tool read, reload restores messages');save();
 await waitFor(async()=>Date.now()/1000,t=>t>expires+1,75);
 const before=await detail(sid),beforeEvents=before.runs.reduce((n,r)=>n+r.events.length,0);
 const blocked=await submit('请再调用 doc_read 读取 meeting-notes，简短核对负责人和下一步；不发送邮件。',409);
 assert.equal(blocked.data.error.code,'AUTH_EXPIRED');assert.equal(blocked.data.error.accepted,false);
 conversation=await detail(sid);assert.equal(conversation.runs.length,2);assert.equal(conversation.runs.reduce((n,r)=>n+r.events.length,0),beforeEvents);
 await page.locator('.conversation-auth-notice').waitFor();
 const originalMessageId=blocked.request.message_id;
 const retry=page.waitForResponse(r=>r.request().method()==='POST'&&/\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname),{timeout:60000});
 await page.getByRole('button',{name:'重新授权并继续',exact:true}).click();
 const retried=await retry;assert.equal(retried.status(),202);assert.equal(retried.request().postDataJSON().message_id,originalMessageId);
 conversation=await complete(sid,3);assert.equal(conversation.id,sid);assert.notEqual(conversation.low_grant.digest,oldDigest);assert.equal(conversation.low_grant.message.expiresAt-conversation.low_grant.message.issuedAt,86400);
 // Explicit duplicate HTTP delivery returns original accepted run, with no extra model execution.
 csrf=(await(await page.request.get(base+'/ops/v1/session')).json()).csrf;
 const duplicate=await page.request.post(base+`/ops/v1/conversations/${sid}/messages`,{headers:{Origin:base,'X-CSRF-Token':csrf},data:blocked.request});assert.equal(duplicate.status(),202);assert.equal((await duplicate.json()).runs.length,3);
 report.checks.push('real 60s expiration rejected without enqueue/model; explicit 24h renewal automatically resubmits original message ID exactly once');save();
 conversation=await waitFor(()=>detail(sid),v=>v.low_status?.observations?.some(o=>o.status==='ANCHORED'&&o.batch.count===1&&!o.batch.closed));
 checkpoint1=conversation.low_status.observations.find(o=>o.batch?.count===1).batch;
 }
 const sid=conversation.id;
 csrf=(await(await page.request.get(base+'/ops/v1/session')).json()).csrf;
 // HIGH flow remains independent: two different organization sessions, exact intent, requester reserve.
 if(conversation.runs.length===3){await page.reload();await page.getByLabel('任务对话').first().waitFor();await submit('把你上一轮的完整总结作为正文，调用 mail_send 发给 alice@inbox.chainguard.invalid，主题为“旧会话续期验收”。不要再读取文档。');}
 conversation=await waitFor(()=>detail(sid),v=>v.runs.length===4&&v.runs[3].record&&(v.runs[3].scheduler_state==='AWAITING_APPROVAL'||v.runs[3].record.state==='FINALIZED_OK'&&v.runs[3].agent_output));
 const high=conversation.runs[3];report.action_id=high.record.action_id;save();
 if(high.record.state!=='FINALIZED_OK'){
 await page.locator('.conversation-blocker').waitFor();assert.ok(await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).isDisabled());
 const busy=await page.request.post(base+`/ops/v1/conversations/${sid}/messages`,{headers:{Origin:base,'X-CSRF-Token':csrf},data:{message_id:id(),text:'不能越过审批的新消息',expected_version:conversation.version}});assert.equal(busy.status(),409);assert.equal((await busy.json()).error.code,'CONVERSATION_BUSY');
 const renewBusy=await page.request.post(base+`/ops/v1/conversations/${sid}/grant`,{headers:{Origin:base,'X-CSRF-Token':csrf},data:{duration_seconds:86400,max_calls:50,expected_grant_digest:conversation.low_grant.digest}});assert.equal(renewBusy.status(),409);
 let box=await(await page.request.get(base+`/ops/v1/tasks/${high.id}/mailbox`)).json();assert.equal(box.mail_count,0);
 const digests=[];
 for(const role of ['biz','security']){
  const orgContext=await browser.newContext(),p=await orgContext.newPage();await login(p,role);
  await p.locator(`.task code[title="${high.id}"]`).waitFor();await p.locator('.task').filter({has:p.locator(`code[title="${high.id}"]`)}).click();
  const read=p.waitForResponse(r=>r.url().endsWith(`/tasks/${high.id}/review`));await p.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();digests.push((await(await read).json()).intent_digest);
  await p.locator('.review').waitFor();await p.getByRole('button',{name:/批准此意图/}).click();
  await waitFor(()=>detail(sid),v=>v.runs[3].record.approval_signatures.length===(role==='biz'?1:2));
  box=await(await page.request.get(base+`/ops/v1/tasks/${high.id}/mailbox`)).json();assert.equal(box.mail_count,0);await orgContext.close();
 }
 assert.equal(digests[0],digests[1]);
 await page.getByRole('button',{name:'查看挂起任务',exact:true}).click();await page.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await page.locator('.review').waitFor();
 await page.getByTestId('reserve-execute').click();
 conversation=await waitFor(()=>detail(sid),v=>v.runs[3].record?.state==='FINALIZED_OK'&&Boolean(v.runs[3].agent_output));
 box=await(await page.request.get(base+`/ops/v1/tasks/${high.id}/mailbox`)).json();assert.equal(box.status,'VERIFIED');assert.equal(box.mail_count,1);
 report.checks.push('pending HIGH blocks message and renewal; independent OrgA/OrgB approve same digest with zero mail until requester reserve; finalize resumes model');save();
 }
 if(conversation.state!=='CLOSED')await page.getByRole('button',{name:'结束会话并存证',exact:true}).click();
 conversation=await waitFor(()=>detail(sid),v=>v.state==='CLOSED'&&v.low_status.observations.every(o=>o.status==='ANCHORED'&&o.batch.closed));
 const final=conversation.low_status.observations[0].batch;assert.equal(final.previous_root,checkpoint1.root);assert.ok(final.count>checkpoint1.count);assert.equal(final.session_id,sid);
 report.LOW_checkpoints=[checkpoint1,final];report.runs=conversation.runs.slice(1).map(r=>({id:r.id,state:r.scheduler_state}));
 const auditRows=(await(await page.request.get(audit+'/audit-api/v1/actions')).json()).actions;
 for(const row of auditRows.filter(r=>r.session_id===sid&&r.conversation_observation||r.action_id===high.record.action_id)){
  const verified=await(await page.request.get(audit+`/audit-api/v1/actions/${row.entry_id}/verify`)).json();assert.ok(['VERIFIED','BATCH_VERIFIED'].includes(verified.status));
 }
 await page.reload();await page.getByLabel('任务对话').first().waitFor();assert.equal(await page.getByLabel('任务对话').count(),4);
 for(const width of [1460,390,320]){await page.setViewportSize({width,height:1000});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);}
 assert.equal(original.id,legacy);assert.deepEqual(report.javascript_errors,[]);report.checks.push('renewal and close produce continuous cumulative roots; read-only audit verifies real LOW and HIGH; refresh and mobile preserve history');
 report.status='PASS';save();console.log('PASS: real legacy memory / expiration / renewal / double approval / MIME / four-node audit');
}catch(error){report.status='FAIL';report.failure=error.message;save();throw error;}finally{await browser.close();}
