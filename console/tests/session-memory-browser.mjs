// Fresh real browser task, no mocked routes. Synthetic data only; never logs passwords or model text.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configFile,credentialsFile,out,existing]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configFile,'utf8'));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${c.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(credentialsFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(x=>x.includes(' : ')).map(x=>x.split(' : ')));
const report={status:'RUNNING',mocked_routes:false,real_llm:false,checks:[],javascript_errors:[]},save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1450,height:1000}});page.on('pageerror',e=>report.javascript_errors.push(e.message));
async function conversations(){return (await(await page.request.get(base+'/ops/v1/conversations')).json()).conversations;}
async function waitRun(sid,n){for(let i=0;i<120;i++){const conversation=(await conversations()).find(v=>v.id===sid);if(conversation?.runs.length===n&&conversation.runs[n-1].agent_output)return conversation;await page.waitForTimeout(1000);}throw Error('Real model conversation did not complete');}
async function submit(text){await page.getByLabel('任务内容').fill(text);const response=page.waitForResponse(r=>r.request().method()==='POST'&&/\/conversations\/[^/]+\/messages$/.test(new URL(r.url()).pathname));await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();const r=await response;assert.equal(r.status(),202);return r.json();}
try{
 await page.goto(base);await page.getByLabel('登录身份').selectOption('requester');await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 if(existing){
  await page.evaluate(id=>localStorage.setItem('chainguard.activeConversation.v1',id),existing);await page.reload();await page.getByLabel('任务对话').first().waitFor();
  assert.equal(await page.getByLabel('任务对话').count(),2);assert.match(await page.locator('.conversation-toolbar').innerText(),/2 轮/);report.checks.push('persisted two-turn HIGH conversation restored after reload');
 }else assert.ok(c.acceptance_only&&c.port===8092,'Fresh-only checks must use an isolated acceptance runtime');
 await page.getByRole('button',{name:'新建会话',exact:true}).click();await page.getByRole('button',{name:/整理一份文档摘要/}).click();
 let result=await submit('读取 meeting-notes，简短总结负责人和下一步；不发邮件。');const sid=result.id;report.session_id=sid;save();
 let conversation=await waitRun(sid,1);assert.equal(conversation.runs[0].scheduler_state,'READ_COMPLETED');report.real_llm=true;
 await page.reload();await page.getByLabel('任务对话').waitFor();assert.equal(await page.evaluate(()=>localStorage.getItem('chainguard.activeConversation.v1')),sid);
 await submit('你上一轮说的负责人是谁？根据上文回答，不再调用工具，不发送邮件。');conversation=await waitRun(sid,2);
 assert.equal(conversation.id,sid);assert.equal(conversation.runs.length,2);assert.match(conversation.runs[1].agent_output,/Alice/i);
 await page.reload();await page.getByLabel('任务对话').first().waitFor();assert.equal(await page.getByLabel('任务对话').count(),2);
 assert.equal(new Set(conversation.runs.map(r=>r.conversation_id)).size,1);
 assert.equal(conversation.runs[1].events.filter(e=>e.kind==='AGENT_ATTEMPT').length,0);
 assert.equal(conversation.low_status.grants.length,1);report.checks.push('page creates real task; same session followup remembers Alice without reading again; refresh retains both turns');
 await page.getByRole('button',{name:'结束会话并存证',exact:true}).click();
 for(let i=0;i<45;i++){conversation=(await conversations()).find(v=>v.id===sid);if(conversation.state==='CLOSED'&&conversation.low_status.observations.every(o=>o.status==='ANCHORED'&&o.batch.closed))break;await page.waitForTimeout(1000);}
 assert.equal(conversation.state,'CLOSED');assert.ok(conversation.low_status.observations.length>0&&conversation.low_status.observations.every(o=>o.status==='ANCHORED'&&o.batch.closed));
 assert.ok(await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).isDisabled());
 report.anchor=conversation.low_status.observations[0].batch.evidence;report.runs=conversation.runs.map(r=>({id:r.id,state:r.scheduler_state,model_exchanges:r.events.filter(e=>e.kind==='MODEL_EXCHANGE').length}));
 assert.deepEqual(report.javascript_errors,[]);report.status='PASS';report.checks.push('close automatically anchors LOW session and disables new input');save();
}catch(error){report.status='FAIL';report.failure=error.message;save();throw error;}finally{await browser.close();}
