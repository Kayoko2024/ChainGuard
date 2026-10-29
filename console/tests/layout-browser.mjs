// Live layout acceptance: GET and login only. No task/approval/tool mutations.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
const [configFile,out,mode='after']=process.argv.slice(2);
assert.ok(!fs.existsSync(out),'New output directory required');fs.mkdirSync(out,{recursive:true});
const c=JSON.parse(fs.readFileSync(configFile,'utf8')),base=`http://127.0.0.1:${c.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(x=>x.includes(' : ')).map(x=>x.split(' : ')));
const report={status:'RUNNING',mode,writes:[],checks:[],layout:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:900}});
page.on('pageerror',e=>report.javascript_errors.push(e.message));
page.on('request',r=>{if(r.url().startsWith(base)&&r.method()!=='GET')report.writes.push(new URL(r.url()).pathname);});
const fingerprint=tasks=>tasks.map(j=>[j.id,j.events.map(e=>e.kind),j.record?.action_id,j.record?.reservation_evidence?.tx_hash,j.record?.finalization_evidence?.tx_hash]);
async function jobs(){return(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;}
async function dimensions(){return page.evaluate(()=>{
 const box=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};};
 return{viewport:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth+1,chat:box('.conversation-scroll'),composer:box('.composer-dock'),attachments:box('.document-composer')};
});}
try{
 await page.goto(base);await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const before=await jobs();await page.getByRole('button',{name:'新建会话',exact:true}).click();
 for(const [width,height] of [[1440,900],[1280,720],[390,844],[320,740]]){
  await page.setViewportSize({width,height});const d=await dimensions();report.layout.push(d);assert.equal(d.overflow,false);
  if(mode==='after')assert.ok(d.chat.height>height*.38,`Chat space too small at ${width}: ${d.chat.height}`);
  if(mode==='after'){
   await page.getByText('文件说明',{exact:true}).click();
   const help=await page.locator('.document-info .document-help').boundingBox();
   assert.ok(help.x>=0&&help.x+help.width<=width,`File help outside viewport at ${width}: ${JSON.stringify(help)}`);
   assert.equal((await dimensions()).chat.height,d.chat.height);
   await page.getByText('文件说明',{exact:true}).click();
  }
 }
 if(mode==='before'){report.status='PASS';save();}
 else{
  await page.setViewportSize({width:1440,height:900});
  const privateShots=path.join(c.repo,'.local','ui-layout',path.basename(out));fs.mkdirSync(privateShots,{recursive:true});
  await page.screenshot({path:path.join(privateShots,'chat.png')});
  const collapsed=await dimensions();await page.getByText('文件说明',{exact:true}).click();
  await page.getByText(/最多 4 个，每个 5 MB/).waitFor();assert.equal((await dimensions()).chat.height,collapsed.chat.height);
  await page.getByText('文件说明',{exact:true}).click();
  const permission=page.getByRole('checkbox',{name:'允许生成 / 修改 Word、PDF 副本'});await permission.check();assert.ok(await permission.isChecked());await permission.uncheck();
  assert.equal(await page.getByLabel('添加文档附件').getAttribute('accept'),'.doc,.docx,.pdf,.txt,.md');
  report.checks.push('compact attachment controls, unchanged file types and explicit output permission; help does not resize chat');
  await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();
  await page.getByLabel('搜索可用工具').fill('mail.send');assert.equal(await page.locator('.tool-card:visible').count(),1);
  await page.getByLabel('搜索可用工具').fill('');
  await page.getByRole('button',{name:/个人数据 ·/}).click();assert.equal(await page.locator('.tool-card:visible').filter({has:page.locator('code').filter({hasText:/^doc\./})}).count(),0);
  await page.getByRole('button',{name:/全部工具 ·/}).click();
  await page.screenshot({path:path.join(privateShots,'tool-scope.png')});
  report.checks.push('task authorization list supports search and category without broadening selected scopes');
  await page.getByRole('tab',{name:'接入与管理',exact:true}).click();await page.getByLabel('搜索已接入工具').waitFor();
  const items=(await(await page.request.get(base+'/ops/v1/custom-tools')).json()).tools;
  const names=new Set(items.map(t=>t.name));await page.locator('.managed-tool-row').first().waitFor();assert.equal(await page.locator('.managed-tool-row').count(),names.size);
  for(const [status,states] of [['ACTIVE',['ACTIVE']],['pending',['DRAFT','ENABLING','DISABLING']],['DISABLED',['DISABLED']]]){
   await page.getByLabel('筛选工具状态').selectOption(status);
   assert.equal(await page.locator('.managed-tool-row').count(),new Set(items.filter(t=>states.includes(t.state)).map(t=>t.name)).size);
  }
  await page.getByLabel('筛选工具状态').selectOption('all');
  await page.screenshot({path:path.join(privateShots,'tool-management.png')});
  const selected=items.find(t=>t.adapter==='github.read')||items[0];assert.ok(selected);
  await page.getByLabel('搜索已接入工具').fill(selected.name);assert.equal(await page.locator('.managed-tool-row:visible').count(),1);
  await page.locator('.managed-tool-row:visible .tool-row-open').click();await page.getByLabel('自定义工具版本审阅').waitFor();
  assert.equal(await page.getByLabel('工具详情',{exact:true}).count(),1);
  for(const width of [1440,900,390,320]){
   await page.setViewportSize({width,height:900});
   const box=await page.getByLabel('工具详情',{exact:true}).boundingBox();
   assert.ok(box.x>=0&&box.x+box.width<=width);
   assert.ok(await page.getByRole('button',{name:'关闭工具详情',exact:true}).isVisible());
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  }
  await page.setViewportSize({width:1440,height:900});await page.getByRole('button',{name:'关闭工具详情',exact:true}).click();
  const versions=items.filter(t=>t.name===selected.name).sort((a,b)=>b.version-a.version);
  const history=page.locator('.managed-tool-row:visible .tool-version-history');await history.locator('summary').click();
  assert.equal(await history.locator('button').count(),versions.length);
  await history.getByRole('button').last().click();await page.getByLabel('自定义工具版本审阅').waitFor();
  assert.ok((await page.getByLabel('自定义工具版本审阅').innerText()).includes(versions.at(-1).revision));
  await page.keyboard.press('Escape');assert.equal(await page.getByLabel('工具详情',{exact:true}).count(),0);
  await page.getByLabel('搜索已接入工具').fill('');
  await page.getByRole('button',{name:'接入新工具',exact:true}).click();await page.getByLabel('工具接入方式').selectOption('http');
  await page.getByText('接入通用 API 工具',{exact:true}).click();await page.getByLabel('API 地址',{exact:true}).fill('https://example.com/query');
  await page.getByRole('button',{name:'收起接入表单',exact:true}).click();await page.getByRole('button',{name:'接入新工具',exact:true}).click();assert.equal(await page.getByLabel('API 地址',{exact:true}).inputValue(),'https://example.com/query');
  await page.getByRole('button',{name:'收起接入表单',exact:true}).click();report.checks.push('tools grouped by name; searchable list and on-demand details; API draft survives collapse');
  await page.getByLabel('搜索已接入工具').fill(selected.name);await page.locator('.managed-tool-row:visible .tool-row-open').click();
  await page.getByRole('button',{name:'以此版本修改资料',exact:true}).click();
  if(selected.adapter==='github.read'){
   assert.equal(await page.getByLabel('工具接入方式').inputValue(),'github');
   assert.equal(await page.getByLabel('GitHub 工具名称').inputValue(),selected.name);assert.ok(await page.getByLabel('GitHub 工具名称').evaluate(e=>e.readOnly));
  }
  await page.getByRole('button',{name:'收起接入表单',exact:true}).click();await page.getByLabel('搜索已接入工具').fill('');
  for(const width of [1440,900,390,320]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  assert.deepEqual(fingerprint(await jobs()),fingerprint(before));assert.deepEqual(report.writes,['/ops/v1/login']);assert.deepEqual(report.javascript_errors,[]);
  const context=await browser.newContext({viewport:{width:1280,height:800}}),security=await context.newPage();
  security.on('request',r=>{if(r.url().startsWith(base)&&r.method()!=='GET')report.writes.push(new URL(r.url()).pathname);});
  await security.goto(base);await security.getByLabel('登录身份').selectOption('security');await security.getByLabel('登录密码').fill(passwords.security);await security.getByRole('button',{name:'登录',exact:true}).click();await security.locator('.identity').waitFor();
  await security.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();await security.getByRole('tab',{name:'接入与管理',exact:true}).click();
  assert.equal(await security.getByRole('button',{name:'接入新工具',exact:true}).count(),0);
  await security.getByLabel('搜索已接入工具').fill(selected.name);await security.locator('.managed-tool-row:visible .tool-row-open').click();await security.getByLabel('工具审核风险等级').waitFor();
  assert.ok(await security.getByRole('button',{name:'核对本版本并启用',exact:true}).isVisible());
  assert.equal(await security.getByLabel('任务内容').count(),0);await context.close();
  assert.ok(report.writes.every(p=>p==='/ops/v1/login'));report.checks.push('independent OrgB retains risk/activation review and has no import or task composer');
  report.checks.push('desktop/mobile no horizontal overflow; no business mutations or model calls');report.status='PASS';save();
 }
}catch(e){report.status='FAIL';report.error=String(e);save();throw e;}
finally{await browser.close();}
console.log(JSON.stringify({status:report.status,checks:report.checks.length,layout:report.layout}));
