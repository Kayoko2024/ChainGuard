import {labelLowRiskForTest} from './navigation.mjs';
// Real browser -> real DeepSeek -> original gateway/tool -> public HTTPS echo API.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,credentialConfig,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${c.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(credentialConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1450,height:1000}});
const report={status:'RUNNING',real_llm:null,real_http:true,mocked_routes:false,cases:[],javascript_errors:[],asr_measured:false};
page.on('pageerror',e=>report.javascript_errors.push(e.message));
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
async function settings(){await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();await page.getByRole('tab',{name:'接入与管理',exact:true}).click();}
async function login(role){
 if(await page.getByRole('button',{name:'退出',exact:true}).count())await page.getByRole('button',{name:'退出',exact:true}).click();
 await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();await settings();
}
async function write(url,data){const s=await(await page.request.get(base+'/ops/v1/session')).json();return page.request.post(base+url,{headers:{Origin:base,'X-CSRF-Token':s.csrf,...(url==='/ops/v1/tasks'?{'Idempotency-Key':'0x'+crypto.randomUUID().replaceAll('-','').repeat(2)}:{})},data});}
try{
 await page.goto(base);await login('requester');
 const item={name:'custom.http_echo_'+Date.now().toString(16),profile:'demo',marker:'CG-'+Date.now().toString(16)};report.cases.push(item);
 await page.getByText('接入通用 API 工具',{exact:true}).click();
 await page.getByLabel('API 工具名称',{exact:true}).fill(item.name);await page.getByLabel('API 工具显示名称').fill('通用 API 实测');
 await page.getByLabel('API 工具描述').fill('Call the authorized JSON echo API using query=demo and report its actual returned message. This is a connectivity test, not image recognition.');
 await page.getByLabel('API 地址',{exact:true}).fill('https://httpbin.org/anything');await page.getByLabel('API Method').selectOption('POST');await page.getByLabel('API 请求配置名').fill(item.profile);
 await page.getByLabel('API URL 参数').fill('{"lang":"zh"}');await page.getByLabel('API 请求 Body').fill(JSON.stringify({message:item.marker}));
 const registered=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/custom-tools');await page.getByRole('button',{name:'提交 API 工具待审版本',exact:true}).click();
 const response=await registered;assert.equal(response.status(),201);item.revision=(await response.json()).revision;save();
 assert.equal((await write(`/ops/v1/custom-tools/${item.revision}/activation`,{revision:item.revision,enabled:true})).status(),403);
 const draft=await write('/ops/v1/tasks',{task_text:'Unreviewed request must not run',allowed_tools:[item.name],allowed_document_ids:[],read_mailboxes:[],allowed_recipients:[],custom_tools:[{name:item.name,revision:item.revision,allowed_keys:['demo']}]});assert.equal(draft.status(),422);item.unreviewed_task_rejected=true;
 await login('security');await page.locator('.custom-versions button').filter({hasText:item.name}).click();await page.getByLabel('API 版本绑定').waitFor();
 await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
 await login('requester');await page.locator('.custom-versions button').filter({hasText:item.name}).click();await page.getByRole('checkbox',{name:'准备查询 demo',exact:true}).check();
 await page.getByRole('button',{name:'用本版本准备 Agent 任务',exact:true}).click();await page.getByLabel('任务内容').fill(`请实际调用 ${item.name}，query 精确为 demo，依据真实 API 返回报告 message、lang 和 HTTP 状态。只查询这一份已审核配置，不发送邮件。`);
 const submitted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();const created=await submitted;assert.equal(created.status(),202);item.job_id=(await created.json()).id;save();
 let job;const end=Date.now()+150000;
 while(Date.now()<end){job=await(await page.request.get(base+`/ops/v1/tasks/${item.job_id}`)).json();if(!['QUEUED','AGENT_RUNNING'].includes(job.display_state))break;await page.waitForTimeout(1000);}
 assert.equal(job.display_state,'READ_COMPLETED');assert.equal(job.record,null);
 const calls=job.events.filter(e=>e.kind==='AGENT_ATTEMPT');assert.ok(calls.length);assert.ok(calls.every(e=>e.tool_name===item.name&&e.tool_executed===true));
 const call=calls[0],result=call.result;const actual=JSON.parse(result.data.record.response);
 assert.equal(actual.json.message,item.marker);assert.equal(actual.args.lang,'zh');assert.equal(actual.method,'POST');assert.equal(result.data.source.http_status,200);
 assert.ok(job.agent_output.includes(item.marker));assert.ok(job.events.some(e=>e.kind==='MODEL_EXCHANGE'));report.real_llm=true;
 Object.assign(item,{read_execution_id:result.read_execution_id,http_execution_id:result.http_execution_id,result_sha256:result.sha256,state:job.display_state,http_status:200});
 await page.getByLabel('任务对话').getByText(new RegExp(item.name+' · READ_ALLOWED')).first().click();await page.getByLabel('API 实时来源').waitFor();
 await page.screenshot({path:path.join(out,'http-evidence.png'),fullPage:true});
 const audit=JSON.parse(fs.readFileSync(c.audit_config,'utf8'));let verified;
 for(let i=0;i<40;i++){const r=await page.request.get(`http://127.0.0.1:${audit.port}/audit-api/v1/actions/interactive-${item.job_id.slice(2)}/verify`);if(r.ok()){verified=await r.json();if(verified.status==='EXTERNAL_TOOL_OBSERVATION')break;}await page.waitForTimeout(500);}
 assert.equal(verified?.status,'EXTERNAL_TOOL_OBSERVATION');assert.deepEqual(verified.transactions,[]);item.audit_status=verified.status;report.step='VERIFY_SCOPE';save();
 const scopeDeadline=Date.now()+60000;
 while(!fs.existsSync(path.join(out,'scope-check.done'))){if(Date.now()>scopeDeadline)throw Error('Direct scope verifier timed out');await page.waitForTimeout(300);}
 await settings();await page.locator('.custom-versions button').filter({hasText:item.name}).click();await page.getByRole('button',{name:'以此版本修改资料',exact:true}).click();
 assert.equal(await page.getByLabel('API 地址',{exact:true}).inputValue(),'https://httpbin.org/anything');assert.equal(await page.getByLabel('API Method').inputValue(),'POST');
 assert.equal(JSON.parse(await page.getByLabel('API 请求 Body').inputValue()).message,item.marker);
 await page.getByLabel('API Method').selectOption('GET');assert.equal(await page.getByLabel('API 请求 Body').count(),0);await page.getByLabel('API Method').selectOption('POST');
 await page.setViewportSize({width:1450,height:1000});await page.getByLabel('API 地址',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'http-form-desktop.png')});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.getByLabel('API 地址',{exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'http-form-mobile.png')});
 await login('security');await page.locator('.custom-versions button').filter({hasText:item.name}).click();await page.getByRole('button',{name:'停用本版本',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'DISABLED'}).waitFor();
 assert.deepEqual(report.javascript_errors,[]);report.status='PASS';report.read_transactions=0;report.chain_transactions=c.tool_sessions?null:0;report.local_mails=0;
}catch(e){report.status='FAIL';report.error=e.message;throw e;}finally{save();await browser.close();}
