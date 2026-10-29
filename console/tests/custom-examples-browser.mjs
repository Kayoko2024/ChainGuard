import {labelLowRiskForTest} from './navigation.mjs';
import {openSettings,openChat,openDetails,chooseTask} from './navigation.mjs';
// Uses real registration, admission, DeepSeek and sandbox query services.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,passwordConfig,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
const examples=JSON.parse(fs.readFileSync(new URL('../src/custom-tool-examples.json',import.meta.url),'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(passwordConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',mode:'contact_inventory_examples',real_llm:true,asr_measured:false,cases:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}}),base=`http://127.0.0.1:${c.port}`;
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 async function login(role){
  if(await page.getByRole('button',{name:'退出',exact:true}).count()){await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByLabel('登录身份').waitFor();}
  await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();
 }
 async function write(url,body,extra={}){const s=await(await page.request.get(base+'/ops/v1/session')).json();return page.request.post(base+url,{headers:{Origin:base,'X-CSRF-Token':s.csrf,...extra},data:body});}
 await page.goto(base);await login('requester');
 for(const example of examples){
  await openSettings(page);
  const input=example.registration,name=input.name+'_'+Math.random().toString(16).slice(2,8),item={example_id:example.id,name};report.cases.push(item);report.step='REGISTER_'+example.id;save();
  await page.getByLabel('工具接入方式').selectOption('dataset');const form=page.locator('.connection-intake > div:not([hidden]) .custom-form');if(!await form.isVisible())await page.getByText('注册新的查询工具',{exact:true}).click();
  const before=(await(await page.request.get(base+'/ops/v1/custom-tools')).json()).tools.length;
  await page.getByRole('button',{name:`填入${example.title}示例`,exact:true}).click();
  assert.equal(await page.getByLabel('自定义工具名称',{exact:true}).inputValue(),input.name);
  assert.equal(await page.getByLabel('记录键字段').inputValue(),input.key_field);
  assert.equal(await page.getByLabel('返回字段').inputValue(),input.output_fields.join(', '));
  assert.deepEqual(JSON.parse(await page.getByLabel('自定义工具资料').inputValue()),input.records);
  assert.equal((await(await page.request.get(base+'/ops/v1/custom-tools')).json()).tools.length,before);
  await page.getByLabel('示例任务说明').waitFor();await page.getByLabel('自定义工具名称',{exact:true}).fill(name);
  const registered=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/custom-tools');await page.getByRole('button',{name:'提交待审版本',exact:true}).click();
  const response=await registered;assert.equal(response.status(),201);item.revision=(await response.json()).revision;save();
  const forbidden=await write(`/ops/v1/custom-tools/${item.revision}/activation`,{revision:item.revision,enabled:true});assert.equal(forbidden.status(),403);
  await login('security');await page.locator('.custom-versions button').filter({hasText:name}).click();await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
  await login('requester');
  await openSettings(page,'任务授权');
  for(const input of await page.locator('.tool-cards input[type=checkbox]:enabled').all())await input.uncheck();
  await page.getByRole('checkbox',{name,exact:true}).check();
  await openChat(page);const run=page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true});assert.ok(await run.isDisabled());await openSettings(page,'任务授权');
  const selected=example.id==='inventory'?input.records[1]:input.records[0];item.query=selected[input.key_field];item.forbidden_key=input.records.find(r=>r[input.key_field]!==item.query)[input.key_field];
  await page.getByRole('checkbox',{name:`${name} 记录 ${item.query}`,exact:true}).check();
  await openChat(page);
 await page.getByLabel('任务内容').fill(example.task_example.replace(input.records[0][input.key_field],item.query)+` 必须先调用 ${name}，query 为 ${item.query}，根据实际返回值回答。`);
  const submitted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await run.click();const created=await submitted;assert.equal(created.status(),202);item.job_id=(await created.json()).id;report.step='REAL_MODEL_'+example.id;save();
  const end=Date.now()+150000;let job;
  while(Date.now()<end){job=await(await page.request.get(base+`/ops/v1/tasks/${item.job_id}`)).json();if(job.display_state==='READ_COMPLETED')break;if(!['QUEUED','AGENT_RUNNING'].includes(job.display_state))throw Error('Unexpected task state '+job.display_state+' '+(job.error||''));await page.waitForTimeout(1200);}
  assert.equal(job.display_state,'READ_COMPLETED');assert.equal(job.record,null);assert.deepEqual(job.allowed_recipients,[]);
  const reads=job.events.filter(e=>e.kind==='AGENT_ATTEMPT');assert.ok(reads.length>0);
  assert.ok(reads.every(e=>e.tool_name===name&&e.tool_executed===true&&e.result.trust==='untrusted'));
  assert.deepEqual(reads[0].result.data.record,selected);item.read_execution_id=reads[0].result.read_execution_id;item.result_sha256=reads[0].result.sha256;item.state=job.display_state;
  assert.ok(job.agent_output.includes(example.id==='contacts'?'Alice':'2'));if(example.id==='inventory')assert.ok(job.agent_output.includes('10'));
  const audit=JSON.parse(fs.readFileSync(c.audit_config,'utf8'));let verified;const deadline=Date.now()+30000;
  while(Date.now()<deadline){const r=await page.request.get(`http://127.0.0.1:${audit.port}/audit-api/v1/actions/interactive-${item.job_id.slice(2)}/verify`);if(r.ok()){verified=await r.json();break;}await page.waitForTimeout(500);}
  assert.equal(verified?.status,'READ_ONLY_OBSERVATION');assert.deepEqual(verified.transactions,[]);item.audit_status=verified.status;
  await page.screenshot({path:path.join(out,example.id+'.png'),fullPage:true});save();
 }
 report.step='VERIFY_TOOL_SCOPE';save();const deadline=Date.now()+60000;
 while(!fs.existsSync(path.join(out,'scope-check.done'))){if(Date.now()>deadline)throw Error('Tool scope checker timed out');await page.waitForTimeout(500);}
 await login('security');
 for(const item of report.cases){await page.locator('.custom-versions button').filter({hasText:item.name}).click();await page.getByRole('button',{name:'停用本版本',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'DISABLED'}).waitFor();}
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:path.join(out,'examples-mobile.png'),fullPage:true});assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';report.step='COMPLETE';report.new_sandbox_mails=0;report.read_transactions=0;report.chain_transactions=c.tool_sessions?null:0;
}catch(error){report.status='FAIL';report.error_type=error.name;report.error=error.message;throw error;}finally{save();await browser.close();}
