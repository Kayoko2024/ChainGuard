import {openSettings,openChat,openDetails,chooseTask,chooseConnection} from './navigation.mjs';
// Only GET/login/logout; opens original live-test records without re-running model/tool.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,passwordConfig,source,out]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configPath,'utf8')),b=JSON.parse(fs.readFileSync(source,'utf8'));
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(passwordConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',model_or_tool_reexecuted:false,javascript_errors:[]};
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}});page.on('pageerror',e=>report.javascript_errors.push(e.message));await page.goto(`http://127.0.0.1:${c.port}`);
 await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await openSettings(page);await page.getByLabel('自定义工具管理').waitFor();
 await chooseConnection(page,'github');await page.getByText('接入真实 GitHub 只读工具',{exact:true}).click();assert.equal(await page.getByLabel('GitHub 授权资源').inputValue(),'microsoft/vscode\nmicrosoft/vscode#1');
 for(const item of b.cases){
  await chooseTask(page,item.job_id);await page.locator('.read-observations summary').first().click();
  if(item.source){const proof=page.getByLabel('GitHub 实时来源');await proof.waitFor();assert.ok((await proof.textContent()).includes(item.source.response_sha256));assert.ok((await proof.textContent()).includes(item.source.github_request_id));}
  if(item.tool?.repository_policy){const proof=page.getByLabel('GitHub 链上仓库判定');await proof.waitFor();assert.ok((await proof.textContent()).includes(item.tool.repository_policy.allowed?'链上仓库准入通过':'链上仓库策略拒绝'));assert.ok((await proof.textContent()).includes(item.tool.repository_policy.contract));}
 }
 await page.screenshot({path:path.join(out,'source-evidence.png'),fullPage:true});await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'source-mobile.png'),fullPage:true});assert.deepEqual(report.javascript_errors,[]);report.status='PASS';
}catch(error){report.status='FAIL';report.error_type=error.name;report.error=error.message;throw error;}finally{fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));await browser.close();}
