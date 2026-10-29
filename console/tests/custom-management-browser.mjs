import {labelLowRiskForTest} from './navigation.mjs';
import {openSettings,openChat,openDetails,chooseTask} from './navigation.mjs';
// Real BFF, tool container and DeepSeek. Synthetic local records; no mock routes.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,passwordConfig,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
const examples=JSON.parse(fs.readFileSync(new URL('../src/custom-tool-examples.json',import.meta.url),'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(passwordConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',mode:'contact_inventory_management',real_llm:true,asr_measured:false,cases:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}}),base=`http://127.0.0.1:${c.port}`;
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 async function login(role){
  if(await page.getByRole('button',{name:'退出',exact:true}).count()){await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByLabel('登录身份').waitFor();}
  await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();
 }
 async function write(url,body,extra={}){const s=await(await page.request.get(base+'/ops/v1/session')).json();return page.request.post(base+url,{headers:{Origin:base,'X-CSRF-Token':s.csrf,...extra},data:body});}
 const catalog=async()=> (await(await page.request.get(base+'/ops/v1/custom-tools')).json()).tools;
 async function openVersion(revision){await openSettings(page);const t=(await catalog()).find(t=>t.revision===revision);await page.locator('.custom-versions button').filter({hasText:t.name}).filter({hasText:`v${t.version}`}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:`v${t.version}`}).waitFor();}
 await page.goto(base);await login('requester');
 for(const example of examples){
  await openSettings(page);
  const input=example.registration,name=input.name+'_'+Math.random().toString(16).slice(2,8),item={example_id:example.id,name};report.cases.push(item);report.step='IMPORT_'+example.id;save();
  await page.getByLabel('工具接入方式').selectOption('dataset');if(!await page.locator('.connection-intake > div:not([hidden]) .custom-form').isVisible())await page.getByText('注册新的查询工具',{exact:true}).click();
  await page.getByRole('button',{name:`填入${example.title}示例`,exact:true}).click();await page.getByLabel('自定义工具名称',{exact:true}).fill(name);
  const initial=await catalog();const beforeTasks=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks.length;
  const csv=example.id==='inventory',columns=Object.keys(input.records[0]);
  const content=csv?'\ufeff'+[columns.join(','),...input.records.map(r=>columns.map(k=>JSON.stringify(r[k])).join(','))].join('\r\n'):JSON.stringify(input.records);
  await page.getByLabel('导入资料文件').setInputFiles({name:csv?'stock.csv':'contacts.json',mimeType:csv?'text/csv':'application/json',buffer:Buffer.from(content)});
  await page.waitForFunction(expected=>document.querySelector('[aria-label="导入格式"]').value===expected,csv?'csv':'json');
  if(csv)await page.getByLabel('CSV 列类型').fill('{"quantity":"integer","reorder_level":"integer"}');
  const previewed=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/import-preview'));await page.getByRole('button',{name:'校验并预览导入',exact:true}).click();
  const pr=await previewed;assert.equal(pr.status(),200);assert.equal((await pr.json()).persisted,false);assert.equal((await catalog()).length,initial.length);
  await page.getByLabel('导入预览').waitFor();await page.getByRole('button',{name:'将预览数据填入待审版本',exact:true}).click();
  assert.deepEqual(JSON.parse(await page.getByLabel('自定义工具资料').inputValue()),input.records);
  const created=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/custom-tools');await page.getByRole('button',{name:'提交待审版本',exact:true}).click();
  const response=await created;assert.equal(response.status(),201);item.old_revision=(await response.json()).revision;save();
  await page.getByRole('button',{name:'以此版本修改资料',exact:true}).click();await page.getByLabel('新版本来源').waitFor();
  assert.ok(await page.getByLabel('自定义工具名称',{exact:true}).getAttribute('readonly')!==null);
  const changed=structuredClone(input.records);if(csv)changed[1].quantity=3;else changed[0].department='真实文件导入验收';
  await page.getByLabel('自定义工具资料').fill(JSON.stringify(changed));
  const versioned=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/versions'));await page.getByRole('button',{name:'提交修改后的新版本',exact:true}).click();
  const vr=await versioned;assert.equal(vr.status(),201);item.revision=(await vr.json()).revision;
  const detail=await(await page.request.get(base+'/ops/v1/custom-tools/'+item.revision)).json();
  assert.equal(detail.state,'DRAFT');assert.equal(detail.parent_revision,item.old_revision);assert.equal(detail.manifest.version,2);
  assert.equal(detail.changes.changed_keys.length,1);assert.ok(detail.history[0].recorded_at_utc);
  assert.deepEqual((await(await page.request.get(base+'/ops/v1/custom-tools/'+item.old_revision)).json()).records,input.records);
  const duplicate=await write('/ops/v1/custom-tools/'+item.old_revision+'/versions',vr.request().postDataJSON(),{'Idempotency-Key':await vr.request().headerValue('idempotency-key')});assert.equal((await duplicate.json()).revision,item.revision);
  item.preview_did_not_persist=true;item.old_version_unchanged=true;item.version_registration_idempotent=true;
  const denied=await write('/ops/v1/custom-tools/'+item.revision+'/activation',{revision:item.revision,enabled:true});assert.equal(denied.status(),403);
  const selected=csv?changed[1]:changed[0];item.query=selected[input.key_field];item.forbidden_key=changed.find(r=>r[input.key_field]!==item.query)[input.key_field];
  const early=await write('/ops/v1/tasks',{task_text:'Draft must not run',allowed_tools:[name],allowed_recipients:[],allowed_document_ids:[],read_mailboxes:[],custom_tools:[{name,revision:item.revision,allowed_keys:[item.query]}]},{'Idempotency-Key':'0x'+'bb'.repeat(32)});
  assert.equal(early.status(),422);assert.equal((await early.json()).error.code,'POLICY_REVOKED');
  await login('security');await openVersion(item.revision);await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
  await login('requester');await openVersion(item.revision);
  const prepare=page.getByRole('button',{name:'用本版本准备 Agent 任务',exact:true});assert.ok(await prepare.isDisabled());await page.getByRole('checkbox',{name:`准备查询 ${item.query}`,exact:true}).check();await prepare.click();
  await page.waitForFunction(expected=>document.querySelector('[aria-label="任务内容"]').value.includes(expected),name);
  assert.equal((await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks.length,beforeTasks);
  await openSettings(page,'任务授权');
  assert.ok(await page.getByRole('checkbox',{name:'mail.send',exact:true}).isChecked()===false);
  assert.ok(await page.getByRole('checkbox',{name:`${name} 记录 ${item.query}`,exact:true}).isChecked());
  await openChat(page);
  const submitted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();
  const cr=await submitted;assert.equal(cr.status(),202);item.job_id=(await cr.json()).id;report.step='REAL_MODEL_'+example.id;save();
  const end=Date.now()+150000;let job;
  while(Date.now()<end){job=await(await page.request.get(base+'/ops/v1/tasks/'+item.job_id)).json();if(job.display_state==='READ_COMPLETED')break;if(!['QUEUED','AGENT_RUNNING'].includes(job.display_state))throw Error('Unexpected task state '+job.display_state);await page.waitForTimeout(1000);}
  assert.equal(job.display_state,'READ_COMPLETED');assert.equal(job.record,null);assert.deepEqual(job.allowed_recipients,[]);
  const reads=job.events.filter(e=>e.kind==='AGENT_ATTEMPT');assert.ok(reads.length>0);assert.ok(reads.every(e=>e.tool_name===name&&e.tool_executed===true&&e.result.trust==='untrusted'));
  assert.deepEqual(reads[0].result.data.record,selected);item.read_execution_id=reads[0].result.read_execution_id;item.result_sha256=reads[0].result.sha256;item.state=job.display_state;
  assert.ok(job.agent_output);await page.screenshot({path:path.join(out,example.id+'.png'),fullPage:true});save();
 }
 report.step='VERIFY_TOOL_SCOPE';save();const deadline=Date.now()+60000;while(!fs.existsSync(path.join(out,'scope-check.done'))){if(Date.now()>deadline)throw Error('Scope checker timed out');await page.waitForTimeout(500);}
 await login('security');for(const item of report.cases){await openVersion(item.revision);await page.getByRole('button',{name:'停用本版本',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'DISABLED'}).waitFor();}
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';report.step='COMPLETE';report.new_sandbox_mails=0;report.read_transactions=0;report.chain_transactions=c.tool_sessions?null:0;
}catch(error){report.status='FAIL';report.error_type=error.name;report.error=error.message;throw error;}finally{save();await browser.close();}
