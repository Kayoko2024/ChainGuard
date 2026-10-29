// Real served UI; only GET and login. Never submits a task or calls the model.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const [configFile,out,mode='after']=process.argv.slice(2);
assert.ok(configFile&&out&&!fs.existsSync(out),'Use config and a new output directory');
fs.mkdirSync(out,{recursive:true});
const c=JSON.parse(fs.readFileSync(configFile,'utf8')),base=`http://127.0.0.1:${c.port}`;
const credentials=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const report={status:'RUNNING',mode,writes:[],checks:[],errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:960}});
page.on('pageerror',e=>report.errors.push(e.message));
page.on('request',r=>{if(r.url().startsWith(base)&&r.method()!=='GET')report.writes.push(new URL(r.url()).pathname);});
const tasks=async()=>(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
const fingerprint=jobs=>jobs.map(j=>[j.id,j.events?.length,j.record?.action_id,j.record?.reservation_evidence?.tx_hash,j.record?.finalization_evidence?.tx_hash]);
const send=page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true});
async function settings(){await page.locator('.composer-scope').click();await page.getByRole('tab',{name:'任务授权',exact:true}).click();}
async function back(){await page.getByRole('link',{name:'保存选择，返回对话',exact:true}).click();}
try{
 await page.goto(base);await page.getByLabel('登录密码').fill(credentials.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const before=await tasks();const catalog=await(await page.request.get(base+'/ops/v1/tools')).json();
 const tool=catalog.tools.find(t=>t.custom&&t.enabled&&t.resources?.length);
 assert.ok(tool,'A real admitted custom tool with resource keys is required');
 await page.getByRole('button',{name:'新建会话',exact:true}).click();
 await settings();
 for(const t of catalog.tools.filter(t=>!t.custom&&t.enabled))await page.getByRole('checkbox',{name:t.name,exact:true}).check();
 await page.getByRole('checkbox',{name:tool.name,exact:true}).check();
 await back();await page.getByLabel('任务内容').fill('检查可用工具列表');
 assert.ok(await send.isDisabled());
 report.checks.push('same seven-tool pattern: missing custom resource blocks send');
 if(mode==='before'){
  assert.equal(await page.locator('.composer-scope-notice').count(),0);
  report.checks.push('reproduced old defect: disabled send without actionable resource explanation');
 }else{
  const notice=page.locator('.composer-scope-notice');await notice.waitFor();
  assert.ok((await notice.innerText()).includes(tool.name));
  const screenshots=path.join(c.repo,'.local','ui-tool-scope',path.basename(path.dirname(out)),path.basename(out));fs.mkdirSync(screenshots,{recursive:true});
  await page.screenshot({path:path.join(screenshots,'missing-custom-resource.png')});
  await page.getByLabel('任务内容').press('Control+Enter');
  assert.deepEqual(report.writes,['/ops/v1/login']);
  await notice.getByRole('button',{name:'补全授权',exact:true}).click();
  assert.ok(await page.locator('.settings-scope-notice').isVisible());
 }
 if(mode==='before')await settings();
 await page.getByRole('checkbox',{name:`${tool.name} 记录 ${tool.resources[0]}`,exact:true}).check();
 if(mode!=='before')assert.equal(await page.locator('.settings-scope-notice').count(),0);
 await back();assert.ok(await send.isEnabled());
 assert.equal(await page.getByLabel('任务内容').inputValue(),'检查可用工具列表');
 report.checks.push('explicit resource selection enables send and preserves the draft');
 if(mode!=='before'){
  await settings();
  for(const mailbox of catalog.mailboxes)await page.getByRole('checkbox',{name:'读取 '+mailbox,exact:true}).uncheck();
  await back();assert.ok(await send.isDisabled());assert.match(await page.locator('.composer-scope-notice').innerText(),/邮箱/);
  await page.locator('.composer-scope-notice').getByRole('button',{name:'补全授权',exact:true}).click();
  await page.getByRole('checkbox',{name:'读取 '+catalog.mailboxes[0],exact:true}).check();
  await back();assert.ok(await send.isEnabled());
  report.checks.push('mail read needs its own mailbox scope; fixing it restores send');
  await settings();await page.getByRole('checkbox',{name:tool.name,exact:true}).uncheck();
  await back();assert.ok(await send.isEnabled());
  await settings();await page.getByRole('checkbox',{name:tool.name,exact:true}).check();
  await back();assert.ok(await send.isEnabled());
  report.checks.push('unchecking/rechecking retains only explicitly selected custom resources');
  await settings();await page.getByRole('checkbox',{name:`${tool.name} 记录 ${tool.resources[0]}`,exact:true}).uncheck();await back();
  for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:960});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   const box=await page.locator('.composer-scope-notice').boundingBox();assert.ok(box&&box.x>=0&&box.x+box.width<=width);
   assert.ok(await page.locator('.composer-scope-notice button').isVisible());
  }
  report.checks.push('desktop/mobile resource guidance fits the composer');
 }
 assert.deepEqual(fingerprint(await tasks()),fingerprint(before));assert.deepEqual(report.writes,['/ops/v1/login']);assert.deepEqual(report.errors,[]);
 report.status='PASS';save();
}catch(e){report.status='FAIL';report.error=String(e);save();throw e;}
finally{await browser.close();}
console.log(JSON.stringify(report));
