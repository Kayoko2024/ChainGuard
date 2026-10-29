// Real served pages and existing data only. Never creates tasks, signs or dispatches tools.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {chooseTask} from './navigation.mjs';

const [configFile,out]=process.argv.slice(2);
assert.ok(configFile&&out,'Usage: node console/tests/paper-craft-browser.mjs <runtime.json> <new-out>');
assert.ok(!fs.existsSync(out),'Use a new result directory');
fs.mkdirSync(out,{recursive:true});
const c=JSON.parse(fs.readFileSync(configFile,'utf8'));
const base=`http://127.0.0.1:${c.port}`;
const auditConfig=JSON.parse(fs.readFileSync(c.audit_config,'utf8'));
const audit=`http://127.0.0.1:${auditConfig.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const privateShots=path.join(c.repo,'.local','ui-paper-craft',path.basename(path.dirname(out)),path.basename(out));
fs.mkdirSync(privateShots,{recursive:true});
const report={status:'RUNNING',real_http:true,fixtures:false,writes:[],javascript_errors:[],layouts:[],checks:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:960}});
function observe(p){
 p.on('pageerror',e=>report.javascript_errors.push(e.message));
 p.on('request',r=>{if((r.url().startsWith(base)||r.url().startsWith(audit))&&r.method()!=='GET')report.writes.push({path:new URL(r.url()).pathname,method:r.method()});});
}
observe(page);
const fingerprint=tasks=>tasks.map(t=>[t.id,t.events?.filter(e=>['MODEL_EXCHANGE','AGENT_ATTEMPT','RESERVE_REQUEST','HUMAN_APPROVAL'].includes(e.kind)),t.record?.reservation_evidence,t.record?.finalization_evidence]);
async function layout(p,name,width,height){
 await p.setViewportSize({width,height});
 const v=await p.evaluate(()=>{const chat=document.querySelector('.conversation-scroll');return{width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth+1,background:getComputedStyle(document.body).backgroundColor,chatHeight:chat?.getBoundingClientRect().height,chatOverflow:chat&&chat.clientWidth>0?chat.scrollWidth>chat.clientWidth+1:false};});
 report.layouts.push({page:name,...v});
 assert.equal(v.overflow,false,`${name} overflows at ${width}`);
 assert.equal(v.background,'rgb(253, 246, 238)');
 if(name==='chat'){assert.ok(v.chatHeight>height*.38,`Chat lost primary space: ${v.chatHeight}/${height}`);assert.equal(v.chatOverflow,false,`Chat has horizontal overflow at ${width}`);}
}
async function accessibleColors(p,selectors){
 const colors=await p.evaluate(selectors=>{
  const rgb=s=>s.match(/[\d.]+/g).slice(0,3).map(Number);
  const luminance=c=>c.map(n=>{n/=255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
  return selectors.map(selector=>{
   const e=document.querySelector(selector);if(!e)return{selector,missing:true};
   const s=getComputedStyle(e);let bg=s.backgroundColor,a=e;
   while((bg==='rgba(0, 0, 0, 0)'||bg==='transparent')&&a.parentElement){a=a.parentElement;bg=getComputedStyle(a).backgroundColor;}
   const l=[luminance(rgb(s.color)),luminance(rgb(bg))].sort((a,b)=>a-b);
   return{selector,color:s.color,background:bg,ratio:(l[1]+.05)/(l[0]+.05)};
  });
 },selectors);
 for(const r of colors){assert.equal(r.missing,undefined,`Missing ${r.selector}`);assert.ok(r.ratio>=4.5,`Text contrast ${r.selector}: ${r.ratio}`);}
 return colors;
}
try{
 await page.goto(base);await page.getByRole('heading',{name:'进入工作空间',exact:true}).waitFor();
 await layout(page,'login',1440,960);await page.screenshot({path:path.join(out,'login-desktop.png')});
 await layout(page,'login',390,844);await page.screenshot({path:path.join(out,'login-mobile.png')});
 await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const before=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 await page.setViewportSize({width:1440,height:960});
 await page.getByRole('button',{name:'新建会话',exact:true}).click();await page.locator('.conversation-welcome').waitFor();
 for(const [w,h] of [[1440,960],[1280,720],[768,1024],[390,844],[320,740]])await layout(page,'chat',w,h);
 await page.setViewportSize({width:1440,height:960});
 await page.getByLabel('任务内容').fill('整理授权资料，并列出下一步工作');
 report.contrast=await accessibleColors(page,['.conversation-welcome h1','.conversation-welcome h1 em','.welcome-copy>p','.welcome-label','.conversation-suggestions strong','.conversation-suggestions button>span:not(.suggestion-number)','.welcome-sandbox','.composer-actions .primary']);
 assert.ok(await page.locator('.welcome-hero>.craft-collage').isVisible(),'Desktop must render the original paper collage');
 assert.equal(await page.locator('.welcome-hero .craft-sheet').count(),3);
 const card=page.locator('.conversation-suggestions button').first();
 const sheets=()=>card.locator('.paper-layer').evaluateAll(es=>es.map(e=>getComputedStyle(e).transform));
 await page.mouse.move(1000,50);const rest=await sheets();await card.hover();await page.waitForTimeout(300);const lifted=await sheets();
 assert.notDeepEqual(lifted,rest);const offsets=await card.locator('.paper-layer').evaluateAll(es=>es.map(e=>new DOMMatrix(getComputedStyle(e).transform).m41));assert.ok(offsets[0]>0&&offsets[1]<0,'Paper sheets must separate in opposite directions');
 await page.mouse.move(1000,50);await page.waitForTimeout(300);await page.screenshot({path:path.join(out,'chat-desktop.png')});
 const h0=await page.locator('.conversation-scroll').evaluate(e=>e.clientHeight);
 await page.getByText('文件说明',{exact:true}).click();const h1=await page.locator('.conversation-scroll').evaluate(e=>e.clientHeight);assert.equal(h0,h1);await page.getByText('文件说明',{exact:true}).click();
 assert.equal(await page.getByLabel('添加文档附件').getAttribute('accept'),'.doc,.docx,.pdf,.txt,.md');
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await card.locator('.paper-layer').first().evaluate(e=>getComputedStyle(e).transitionDuration),'0s');await page.emulateMedia({reducedMotion:'no-preference'});
 await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('.welcome-hero>.craft-collage').isVisible(),false,'Mobile keeps the conversation space');await page.screenshot({path:path.join(out,'chat-mobile.png')});
 await page.setViewportSize({width:1440,height:960});
 const history=page.getByRole('region',{name:'历史任务列表'});const scroll=await history.evaluate(e=>{e.scrollTop=e.scrollHeight;const r={height:e.clientHeight,content:e.scrollHeight,scroll:e.scrollTop};e.scrollTop=0;return r;});if(scroll.content>scroll.height)assert.ok(scroll.scroll>0);
 report.checks.push('white paper, two-tone display type and original three-sheet collage','warm paper palette and AA key text contrast','opposite paper layer hover and reduced motion','history scroll and compact attachment controls','chat remains primary at five viewport sizes');
 await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();
 await page.getByRole('tab',{name:'任务授权',exact:true}).focus();await page.keyboard.press('ArrowRight');assert.equal(await page.getByRole('tab',{name:'接入与管理',exact:true}).getAttribute('aria-selected'),'true');await page.keyboard.press('ArrowLeft');assert.equal(await page.getByRole('tab',{name:'任务授权',exact:true}).getAttribute('aria-selected'),'true');
 await page.getByLabel('搜索可用工具').fill('mail.send');assert.equal(await page.locator('.tool-card:visible').count(),1);await page.getByLabel('搜索可用工具').fill('');
 for(const [w,h] of [[1440,960],[768,1024],[390,844],[320,740]])await layout(page,'tools',w,h);
 await page.setViewportSize({width:1440,height:960});await page.screenshot({path:path.join(privateShots,'tools-scope.png')});
 await page.getByRole('tab',{name:'接入与管理',exact:true}).click();await page.getByLabel('搜索已接入工具').waitFor();
 await page.screenshot({path:path.join(privateShots,'tools-management.png')});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(privateShots,'tools-mobile.png')});
 await page.getByRole('link',{name:'返回对话',exact:true}).click();assert.equal(await page.getByLabel('任务内容').inputValue(),'整理授权资料，并列出下一步工作');
 report.checks.push('catalog search, management view, draft preserved across settings');
 const completed=before.find(t=>t.display_state==='FINALIZED_OK');assert.ok(completed,'Existing completed task required');
 await page.setViewportSize({width:1440,height:960});await chooseTask(page,completed.id,{details:true});
 await page.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await page.locator('.review').waitFor();
 await page.getByRole('button',{name:'查看真实沙箱邮件',exact:true}).click();await page.locator('.mail article').first().waitFor();
 const mailbox=await(await page.request.get(base+`/ops/v1/tasks/${completed.id}/mailbox`)).json();assert.equal(mailbox.status,'VERIFIED');assert.equal(mailbox.mail_count,1);
 for(const [w,h] of [[1440,960],[390,844],[320,740]])await layout(page,'history-detail',w,h);
 await page.setViewportSize({width:1440,height:960});await page.screenshot({path:path.join(privateShots,'history-evidence.png')});
 report.checks.push('persisted conversation, original intent review and verified existing local MIME remain readable');
 const observer=await browser.newPage({viewport:{width:1440,height:960}});observe(observer);await observer.goto(audit);await observer.getByRole('heading',{name:'动作审计',exact:true}).waitFor();
 const actions=(await(await observer.request.get(audit+'/audit-api/v1/actions')).json()).actions;
 assert.ok(actions.length,'Real existing audit rows required');
 for(const [w,h] of [[1440,960],[1024,900],[768,1024],[390,844],[320,740]])await layout(observer,'audit',w,h);
 await observer.setViewportSize({width:1440,height:960});
 report.audit_contrast=await accessibleColors(observer,['.stats article>strong','.stats article>p','.verify-box button']);
 const finalized=actions.find(a=>a.group==='C'&&a.state==='FINALIZED_OK');assert.ok(finalized,'Existing C finalized action required');
 await observer.getByLabel('搜索动作').fill(finalized.action_id);await observer.locator('.row-link').first().click();
 await observer.getByRole('button',{name:'实时核验',exact:true}).click();
 await observer.getByTestId('verification-status').filter({hasText:'实时证据一致'}).waitFor({timeout:90000});
 const verified=await(await observer.request.get(audit+`/audit-api/v1/actions/${finalized.entry_id}/verify`)).json();
 assert.equal(verified.status,'VERIFIED');assert.ok(verified.transactions.every(t=>t.node_receipts===4));assert.equal(new Set(verified.approvals.map(a=>a.organization)).size,2);
 report.real_verification={entry_id:finalized.entry_id,action_id:finalized.action_id,status:verified.status,transactions:verified.transactions,tool_signer:verified.tool_signer,organizations:verified.approvals.map(a=>a.organization_label)};
 await observer.screenshot({path:path.join(privateShots,'audit-verified.png'),fullPage:true});
 await observer.getByLabel('搜索动作').fill('no-paper-craft-row');await observer.getByText('没有匹配记录',{exact:true}).waitFor();await observer.getByLabel('搜索动作').fill('');
 await observer.getByRole('button',{name:'C · 联盟链',exact:true}).click();assert.ok((await observer.locator('tbody .group').allTextContents()).every(x=>x==='C'));
 for(const role of ['biz','security']){const ctx=await browser.newContext();const p=await ctx.newPage();observe(p);await p.goto(base);await p.getByLabel('登录身份').selectOption(role);await p.getByLabel('登录密码').fill(passwords[role]);await p.getByRole('button',{name:'登录',exact:true}).click();await p.locator('.identity').waitFor();assert.equal(await p.getByLabel('任务内容').count(),0);assert.equal(await p.getByTestId('reserve-execute').count(),0);await ctx.close();}
 const after=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;assert.deepEqual(fingerprint(after),fingerprint(before));assert.ok(report.writes.every(r=>r.path==='/ops/v1/login'));assert.equal(report.javascript_errors.length,0);
 report.checks.push('real existing C action, four-node receipts, two organizations and tool signature','read-only audit filtering and separate approver identities','unchanged model/tool/approval/transaction records; zero task creation');
 report.created_tasks=0;report.model_calls=0;report.tool_dispatches=0;report.new_transactions=0;report.existing_tasks=before.length;report.audit_rows=actions.length;report.status='PASS';save();console.log('PASS: Paper Craft responsive UI and real four-node evidence; zero business writes.');
}catch(e){report.status='FAIL';report.failure=e.message;save();throw e;}finally{await browser.close();}
