import {chooseConnection,labelLowRiskForTest} from './navigation.mjs';
import {openSettings,openChat,openDetails,chooseTask} from './navigation.mjs';
// Live browser -> real DeepSeek -> gateway -> independent tool -> GitHub HTTPS.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,passwordConfig,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(passwordConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',mode:'github_live',real_llm:true,asr_measured:false,cases:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}}),base=`http://127.0.0.1:${c.port}`,name='custom.github_'+Math.random().toString(16).slice(2,8);
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 async function login(role){if(await page.getByRole('button',{name:'退出',exact:true}).count()){await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByLabel('登录身份').waitFor();}await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();}
 async function write(url,body,extra={}){const s=await(await page.request.get(base+'/ops/v1/session')).json();return page.request.post(base+url,{headers:{Origin:base,'X-CSRF-Token':s.csrf,...extra},data:body});}
 async function open(){await openSettings(page);await page.locator('.custom-versions button').filter({hasText:name}).click();await page.getByLabel('自定义工具版本审阅').waitFor();}
 await page.goto(base);await login('requester');await chooseConnection(page,'github');await page.getByText('接入真实 GitHub 只读工具',{exact:true}).click();
 await page.getByLabel('GitHub 工具名称').fill(name);await page.getByLabel('GitHub 授权资源').fill('microsoft/vscode\nmicrosoft/vscode#1');
 const registered=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/custom-tools');await page.getByRole('button',{name:'提交 GitHub 工具待审版本',exact:true}).click();
 const response=await registered;assert.equal(response.status(),201);report.revision=(await response.json()).revision;report.name=name;save();
 const unauth=await write('/ops/v1/custom-tools/'+report.revision+'/activation',{revision:report.revision,enabled:true});assert.equal(unauth.status(),403);
 await login('security');await open();await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
 await login('requester');
 for(const key of ['microsoft/vscode','microsoft/vscode#1']){
  await open();await page.getByRole('checkbox',{name:'准备查询 '+key,exact:true}).check();await page.getByRole('button',{name:'用本版本准备 Agent 任务',exact:true}).click();
  await page.waitForFunction(q=>document.querySelector('[aria-label="任务内容"]').value.includes(q),key);
  await page.getByLabel('任务内容').fill(`必须调用 ${name}，query 精确为 ${key}。根据真实 GitHub 返回值总结${key.includes('#')?'Issue 标题、状态及主要内容':'仓库名称、用途、Stars 和未关闭 Issue 数'}，列出来源 URL 和查询时间。不要查询其他资源，不发送邮件。`);
  const submitted=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();const created=await submitted;assert.equal(created.status(),202);
  const item={name,revision:report.revision,query:key,forbidden_key:'octocat/hello-world',job_id:(await created.json()).id};report.cases.push(item);report.step='REAL_MODEL';save();
  const end=Date.now()+150000;let job;
  while(Date.now()<end){job=await(await page.request.get(base+'/ops/v1/tasks/'+item.job_id)).json();if(job.display_state==='READ_COMPLETED')break;if(!['QUEUED','AGENT_RUNNING'].includes(job.display_state))throw Error('Actual task state '+job.display_state+' '+JSON.stringify(job.attempt?.result));await page.waitForTimeout(1000);}
  assert.equal(job.display_state,'READ_COMPLETED');assert.equal(job.record,null);assert.deepEqual(job.allowed_recipients,[]);
  const reads=job.events.filter(e=>e.kind==='AGENT_ATTEMPT');assert.ok(reads.length>0);assert.ok(reads.every(e=>e.tool_name===name&&e.tool_executed===true));
  const r=reads[0].result;assert.equal(r.trust,'untrusted');assert.equal(r.data.record.resource,key);assert.equal(r.data.source.http_status,200);assert.ok(r.data.source.github_request_id);assert.match(r.data.source.url,/^https:\/\/api\.github\.com\/repos\/microsoft\/vscode/);
  Object.assign(item,{read_execution_id:r.read_execution_id,result_sha256:r.sha256,source:r.data.source,state:job.display_state});
  await page.screenshot({path:path.join(out,key.includes('#')?'issue.png':'repository.png'),fullPage:true});save();
 }
 report.step='VERIFY_TOOL_SCOPE';save();const deadline=Date.now()+60000;while(!fs.existsSync(path.join(out,'scope-check.done'))){if(Date.now()>deadline)throw Error('Scope checker timed out');await page.waitForTimeout(500);}
 await login('security');await open();await page.getByRole('button',{name:'停用本版本',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'DISABLED'}).waitFor();
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';report.step='COMPLETE';report.new_sandbox_mails=0;report.read_transactions=0;report.chain_transactions=c.tool_sessions?null:0;
}catch(error){report.status='FAIL';report.error_type=error.name;report.error=error.message;throw error;}finally{save();await browser.close();}
