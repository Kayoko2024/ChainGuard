import {labelLowRiskForTest} from './navigation.mjs';
import {openSettings,openChat,openDetails,chooseTask} from './navigation.mjs';
// Real UI + DeepSeek + existing C services. Only synthetic local test records/mail.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,passwordConfig,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(passwordConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',real_llm:true,asr_measured:false,javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}});page.on('pageerror',e=>report.javascript_errors.push(e.message));
 const base=`http://127.0.0.1:${c.port}`,name='custom.project_'+Math.random().toString(16).slice(2,10);
 async function login(role){
  if(await page.getByRole('button',{name:'退出',exact:true}).count()){await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByLabel('登录身份').waitFor();}
  await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();
 }
 async function write(url,body,extra={}){
  const session=await(await page.request.get(base+'/ops/v1/session')).json();
  return page.request.post(base+url,{headers:{Origin:base,'X-CSRF-Token':session.csrf,...extra},data:body});
 }
 async function job(){return (await page.request.get(base+`/ops/v1/tasks/${report.job_id}`)).json();}
 async function waitState(state){
  const end=Date.now()+150000;
  while(Date.now()<end){const v=await job();if(v.display_state===state&&(state!=='AWAITING_APPROVAL'||v.record))return v;if(['MODEL_ERROR','INTERRUPTED','DENIED','NO_ACTION','READ_COMPLETED','FINALIZED_ERROR','EXPIRED'].includes(v.display_state))throw Error('Unexpected task state '+v.display_state+' '+(v.error||''));await page.waitForTimeout(1200);}
  throw Error('Task timed out waiting for '+state);
 }
 await page.goto(base);await login('requester');
 await page.getByLabel('工具接入方式').selectOption('dataset');await page.getByText('注册新的查询工具',{exact:true}).click();
 await page.getByLabel('自定义工具名称',{exact:true}).fill(name);await page.getByLabel('自定义工具显示名称').fill('合成项目查询验收');
 await page.getByLabel('自定义工具描述').fill('按项目编号查询已授权的合成项目负责人和状态。query 必须为项目编号。');
 await page.getByLabel('记录键字段').fill('project_id');await page.getByLabel('返回字段').fill('project_id, owner, status');
 await page.getByRole('button',{name:'填入合成示例资料'}).click();
 await page.getByRole('button',{name:'提交待审版本'}).click();await page.getByLabel('自定义工具版本审阅').waitFor();
 const versions=await(await page.request.get(base+'/ops/v1/custom-tools')).json();const t=versions.tools.find(t=>t.name===name);assert.equal(t.state,'DRAFT');report.name=name;report.revision=t.revision;save();
 const forbidden=await write(`/ops/v1/custom-tools/${t.revision}/activation`,{revision:t.revision,enabled:true});assert.equal(forbidden.status(),403);
 await login('security');await page.locator('.custom-versions button').filter({hasText:name}).click();await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用'}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
 await login('requester');
 await openSettings(page,'任务授权');
 for(const builtin of ['doc.list','doc.search','doc.read'])await page.getByRole('checkbox',{name:builtin,exact:true}).uncheck();
 await page.getByRole('checkbox',{name,exact:true}).check();
 await openChat(page);const run=page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true});assert.ok(await run.isDisabled());await openSettings(page,'任务授权');
 await page.getByRole('checkbox',{name:`${name} 记录 DEMO-1`,exact:true}).check();
 await openChat(page);
 await page.getByLabel('任务内容').fill(`真实合成验收：必须先调用 ${name}，query 为 DEMO-1，读取项目负责人和状态。再把查询到的负责人和状态发送给 alice@inbox.chainguard.invalid，主题为自定义工具真实链路验收。只查询 DEMO-1，不查询其他编号。`);
 const taskResponse=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await run.click();
 const created=await taskResponse;assert.equal(created.status(),202);report.job_id=(await created.json()).id;report.step='REAL_MODEL_RUNNING';save();
 let current=await waitState('AWAITING_APPROVAL');report.action_id=current.record.action_id;
 assert.deepEqual(current.events.filter(e=>e.kind==='AGENT_ATTEMPT').map(e=>e.tool_name),[name,'mail.send']);
 const read=current.events.find(e=>e.kind==='AGENT_ATTEMPT'&&e.tool_name===name);assert.equal(read.result.revision,t.revision);assert.equal(read.result.data.record.owner,'Alice');assert.equal(read.tool_executed,true);
 const reviewed=await(await page.request.get(base+`/ops/v1/tasks/${report.job_id}/review`)).json();
 const missing=await write(`/ops/v1/tasks/${report.job_id}/execute`,{intent_digest:reviewed.intent_digest});assert.ok(!missing.ok());report.missing_approval=(await missing.json()).error.code;
 const negative=await write(`/ops/v1/tasks/${report.job_id}/negative-control`,{});assert.ok(negative.ok());const n=await negative.json();assert.equal(n.error_code,'UNAUTHORIZED_SCOPE');assert.equal(n.mail_before,n.mail_after);report.negative_control=n;
 async function selectTask(){await chooseTask(page,report.job_id,{details:true});await page.getByRole('button',{name:'审阅原意图与邮件参数'}).click();await page.locator('.detail .review').waitFor();}
 for(const role of ['biz','security']){await login(role);await selectTask();const approved=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/approve'));await page.getByRole('button',{name:/批准此意图/}).click();assert.ok((await approved).ok());await page.getByRole('button',{name:/批准此意图/}).isEnabled();}
 await login('requester');await selectTask();await page.getByTestId('reserve-execute').click();current=await waitState('FINALIZED_OK');
 const mailbox=await(await page.request.get(base+`/ops/v1/tasks/${report.job_id}/mailbox`)).json();assert.equal(mailbox.status,'VERIFIED');assert.equal(mailbox.mail_count,1);report.mime_sha256=mailbox.messages[0].mime_sha256;
 const duplicate=await write(`/ops/v1/tasks/${report.job_id}/execute`,{intent_digest:reviewed.intent_digest});assert.ok(duplicate.ok());
 assert.equal((await(await page.request.get(base+`/ops/v1/tasks/${report.job_id}/mailbox`)).json()).mail_count,1);
 await page.screenshot({path:path.join(out,'business.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'business-mobile.png'),fullPage:true});
 const auditConfig=JSON.parse(fs.readFileSync(c.audit_config,'utf8')),auditBase=`http://127.0.0.1:${auditConfig.port}`;
 const entry='interactive-'+report.job_id.slice(2);const end=Date.now()+45000;let verified;
 while(Date.now()<end){const r=await page.request.get(`${auditBase}/audit-api/v1/actions/${entry}/verify`);if(r.ok()){verified=await r.json();if(verified.status==='VERIFIED')break;}await page.waitForTimeout(1000);}
 assert.equal(verified?.status,'VERIFIED');assert.ok(verified.transactions.every(v=>v.node_receipts===4));report.verification=verified;
 report.step='VERIFY_TOOL_SCOPE';save();const probeDeadline=Date.now()+60000;
 while(!fs.existsSync(path.join(out,'scope-check.done'))){if(Date.now()>probeDeadline)throw Error('Tool scope checker did not complete');await page.waitForTimeout(500);}
 await login('security');await page.locator('.custom-versions button').filter({hasText:name}).click();await page.getByRole('button',{name:'停用本版本',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'DISABLED'}).waitFor();
 await login('requester');const blocked=await write('/ops/v1/tasks',{task_text:'Revoked read must be rejected',allowed_tools:[name],allowed_document_ids:[],read_mailboxes:[],allowed_recipients:[],custom_tools:[{name,revision:t.revision,allowed_keys:['DEMO-1']}]},{'Idempotency-Key':'0x'+'ab'.repeat(32)});
 assert.equal(blocked.status(),422);assert.equal((await blocked.json()).error.code,'POLICY_REVOKED');
 assert.deepEqual(report.javascript_errors,[]);report.status='PASS';report.new_sandbox_mails=1;report.step='COMPLETE';
}catch(e){report.status='FAIL';report.error_type=e.name;report.error=e.message;throw e;}finally{save();await browser.close();}
