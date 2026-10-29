import {chooseConnection,labelLowRiskForTest} from './navigation.mjs';
import {openSettings,openChat,openDetails,chooseTask} from './navigation.mjs';
// Fresh live tasks. Real DeepSeek responses, real gateway, actual Besu policy, actual HTTPS.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configPath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',real_llm:true,asr_measured:false,cases:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}}),base=`http://127.0.0.1:${c.port}`;
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 async function login(role){
  if(await page.getByRole('button',{name:'退出',exact:true}).count()){await page.getByRole('button',{name:'退出',exact:true}).click();await page.getByLabel('登录身份').waitFor();}
  await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();
 }
 const name='custom.github_vscode_'+Math.random().toString(16).slice(2,8);report.name=name;
 async function open(){await openSettings(page);await page.locator('.custom-versions button').filter({hasText:name}).click();await page.getByLabel('自定义工具版本审阅').waitFor();}
 await page.goto(base);await login('requester');await chooseConnection(page,'github');await page.getByText('接入真实 GitHub 只读工具',{exact:true}).click();
 await page.getByRole('button',{name:'填入 VS Code 验收用例',exact:true}).click();await page.getByLabel('GitHub 工具名称').fill(name);
 const registered=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/custom-tools');
 await page.getByRole('button',{name:'提交 GitHub 工具待审版本',exact:true}).click();let response=await registered;assert.equal(response.status(),201);report.revision=(await response.json()).revision;save();
 await login('security');await open();await labelLowRiskForTest(page);await page.getByRole('button',{name:'核对本版本并启用',exact:true}).click();await page.getByLabel('自定义工具版本审阅').getByRole('heading').filter({hasText:'ACTIVE'}).waitFor();
 await login('requester');await open();
 for(const key of ['microsoft/vscode','microsoft/vscode#1','facebook/react#1'])await page.getByRole('checkbox',{name:'准备查询 '+key,exact:true}).check();
 await page.getByRole('button',{name:'用本版本准备 Agent 任务',exact:true}).click();
 for(const [query,expected] of [['microsoft/vscode#1','READ_COMPLETED'],['facebook/react#1','DENIED']]){
  await page.getByLabel('任务内容').fill(`请实际调用 ${name}，query 精确为 ${query}，查询这个 Issue 的标题、状态与内容。必须依据工具的真实结果回答；若被拒绝则报告原因。不要查询其他资源，不发邮件。`);
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url()===base+'/ops/v1/tasks');await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();response=await pending;assert.equal(response.status(),202);
  const item={job_id:(await response.json()).id,query,expected};report.cases.push(item);save();
  let job;const deadline=Date.now()+180000;
  while(Date.now()<deadline){job=await(await page.request.get(base+'/ops/v1/tasks/'+item.job_id)).json();if(!['QUEUED','AGENT_RUNNING'].includes(job.display_state))break;await page.waitForTimeout(1000);}
  assert.equal(job.display_state,expected,JSON.stringify({state:job.display_state,error:job.error,attempt:job.attempt?.result}));
  const attempts=job.events.filter(e=>e.kind==='AGENT_ATTEMPT');assert.equal(attempts.length,1);const attempt=attempts[0];
  assert.equal(attempt.arguments.query,query);assert.equal(attempt.result.repository_policy.allowed,expected==='READ_COMPLETED');
  assert.equal(attempt.tool_executed,expected==='READ_COMPLETED');assert.equal(job.record,null);
  if(expected==='READ_COMPLETED')assert.equal(attempt.result.data.source.http_status,200);
  else assert.equal(attempt.result.error_code,'GITHUB_REPOSITORY_DENIED');
  item.result={status:expected,error_code:attempt.result.error_code,read_execution_id:attempt.result.read_execution_id,repository_policy:attempt.result.repository_policy};save();
 }
 // Exercise the visible manual controls too; these are explicitly not model samples.
 await openSettings(page,'GitHub 链策略');
 const panel=page.getByLabel('GitHub 链上策略验收');
 for(const [button,code] of [['测试其他仓库被链上拒绝','GITHUB_REPOSITORY_DENIED'],['测试未授权 Issue 被工具拒绝','UNAUTHORIZED_SCOPE']]){
  const pending=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/github-negative-control'));
  await panel.getByRole('button',{name:button,exact:true}).click();response=await pending;assert.equal(response.status(),200);const v=await response.json();
  assert.equal(v.error_code,code);assert.equal(v.no_new_github_fetch,true);assert.equal(v.chain_enforced,code==='GITHUB_REPOSITORY_DENIED');
  (report.manual_probes??=[]).push(v);save();
 }
 const policy=await(await page.request.get(base+'/ops/v1/github-policy?resource=facebook%2Freact%231')).json();assert.equal(policy.allowed,false);report.current_denied_policy=policy;
 await page.reload();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';save();
}catch(e){report.status='FAIL';report.error_type=e.name;report.error=e.message;save();throw e;}finally{await browser.close();}
