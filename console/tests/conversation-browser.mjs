// Real HTTP UI regression. No task creation, approval, tool dispatch or model request.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,out]=process.argv.slice(2),config=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.ok(!fs.existsSync(out),'Use a new output directory');fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${config.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configPath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',real_http:true,mocked_routes:false,checks:[],writes:[],javascript_errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
function observe(page){page.on('pageerror',e=>report.javascript_errors.push(e.message));page.on('request',r=>{if(r.url().startsWith(base)&&r.method()!=='GET')report.writes.push({path:new URL(r.url()).pathname,method:r.method()});});}
async function login(page,role){await page.goto(base);await page.getByLabel('登录身份').selectOption(role);await page.getByLabel('登录密码').fill(passwords[role]);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();await page.locator('.task').first().waitFor();}
async function settings(page,tab){await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();await page.getByRole('tab',{name:tab,exact:true}).click();}
async function noOverflow(page,width,height){await page.setViewportSize({width,height});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`page overflows at ${width}`);}
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}});observe(page);await login(page,'requester');
 let before=[];
 for(let i=0;i<25;i++){before=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;if(before.some(t=>t.display_state==='FINALIZED_OK'))break;await page.waitForTimeout(1000);}
 assert.ok(await page.getByRole('heading',{name:'今天，让 Agent 帮你做什么？',exact:true}).isVisible());
 assert.equal(await page.getByLabel('自定义工具管理').isVisible(),false);
 assert.equal(await page.getByLabel('默认工具库').isVisible(),false);
 assert.equal(await page.getByLabel('审批与执行详情').count(),0);
 assert.ok(await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).isDisabled());
 const dimensions=await page.evaluate(()=>{const center=document.querySelector('.conversation-center').getBoundingClientRect();const sidebar=document.querySelector('.conversation-sidebar').getBoundingClientRect();const input=document.querySelector('#task-text').getBoundingClientRect();return {chat_width:center.width,sidebar_width:sidebar.width,viewport_width:innerWidth,input_visible:input.top>=0&&input.bottom<=innerHeight};});
 assert.ok(dimensions.chat_width/dimensions.viewport_width>.75);assert.ok(dimensions.input_visible);report.desktop_dimensions=dimensions;
 await page.screenshot({path:path.join(out,'conversation-desktop.png')});
 const draft='界面回归草稿：查阅授权文档；此测试不发送任务。';await page.getByLabel('任务内容').fill(draft);
 await settings(page,'任务授权');assert.ok(await page.getByLabel('默认工具库').isVisible());
 assert.ok(await page.getByRole('checkbox',{name:'doc.delete',exact:true}).isDisabled());
 await page.getByRole('checkbox',{name:'mail.send',exact:true}).uncheck();await page.getByText('当前为只读任务',{exact:true}).waitFor();
 await page.getByRole('checkbox',{name:'meeting-notes',exact:true}).uncheck();await page.getByRole('checkbox',{name:'project-brief',exact:true}).uncheck();
 await page.getByRole('link',{name:'保存选择，返回对话',exact:true}).click();
 assert.equal(await page.getByLabel('任务内容').inputValue(),draft);assert.ok(await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).isDisabled());
 await settings(page,'接入与管理');await page.getByLabel('自定义工具管理').waitFor();assert.equal(await page.getByLabel('工具接入方式').inputValue(),'http');
 await page.getByLabel('工具接入方式').selectOption('dataset');await page.getByText('注册新的查询工具',{exact:true}).click();await page.getByLabel('导入资料文件').waitFor();
 await page.getByLabel('工具接入方式').selectOption('github');await page.getByText('接入真实 GitHub 只读工具',{exact:true}).waitFor();await page.getByText('仓库策略与验证',{exact:true}).click();
 await page.getByLabel('GitHub 链上策略验收').waitFor();await page.screenshot({path:path.join(out,'tools-desktop.png')});
 await page.getByRole('tab',{name:'接入与管理',exact:true}).press('ArrowRight');assert.equal(await page.getByRole('tab',{name:'任务授权',exact:true}).getAttribute('aria-selected'),'true');
 await page.getByRole('link',{name:'返回对话',exact:true}).click();assert.equal(await page.getByLabel('任务内容').inputValue(),draft);
 report.checks.push('conversation dominates; management hidden by default; no disabled-tool escalation; draft and scope survive navigation; keyboard tabs');
 const finalized=before.find(t=>t.display_state==='FINALIZED_OK');assert.ok(finalized,'Existing real finalized task required');
 await page.locator('.task').filter({has:page.locator(`code[title="${finalized.id}"]`)}).click();
 const thread=page.getByLabel('任务对话');assert.equal(await thread.locator('.user-message .message-text').textContent(),finalized.task_text);
 assert.equal(await thread.locator('.tool-message').count(),finalized.events.filter(e=>e.kind==='AGENT_ATTEMPT').length);
 assert.equal(await page.getByLabel('审批与执行详情').count(),0);
 await page.getByRole('button',{name:'审批与证据',exact:true}).click();await page.getByTestId('workflow-step').filter({hasText:'已有链上终态'}).waitFor();
 await page.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await page.locator('.review').waitFor();
 await page.getByRole('button',{name:'查看真实沙箱邮件',exact:true}).click();await page.locator('.mail article').first().waitFor();
 const mailbox=await(await page.request.get(base+`/ops/v1/tasks/${finalized.id}/mailbox`)).json();assert.equal(mailbox.status,'VERIFIED');assert.equal(mailbox.mail_count,1);
 report.existing_evidence={task_id:finalized.id,action_id:finalized.record.action_id,mailbox_status:mailbox.status,mail_count:mailbox.mail_count,reserve_tx:finalized.record.reservation_evidence.tx_hash,finalize_tx:finalized.record.finalization_evidence.tx_hash};
 await page.screenshot({path:path.join(out,'execution-desktop.png')});await page.getByRole('button',{name:'关闭执行详情',exact:true}).click();
 await page.getByRole('button',{name:'新建会话',exact:true}).click();assert.equal(await page.getByLabel('任务内容').inputValue(),'');
 await page.getByRole('button',{name:/整理一份文档摘要/}).click();assert.ok((await page.getByLabel('任务内容').inputValue()).includes('不发送邮件'));
 assert.ok(await page.getByLabel('任务内容').evaluate(e=>document.activeElement===e));
 for(const [width,height] of [[1024,768],[750,900],[390,844],[320,740]]){
  await noOverflow(page,width,height);await page.getByLabel('任务内容').scrollIntoViewIfNeeded();
  const bounds=await page.getByLabel('任务内容').boundingBox();assert.ok(bounds.y>=0&&bounds.y+bounds.height<=height);
  if(width===390)await page.screenshot({path:path.join(out,'conversation-mobile.png')});
 }
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'历史任务',exact:true}).click();await page.getByLabel('搜索任务').fill(finalized.id);await page.locator('.task').first().click();
 assert.equal(await page.getByRole('button',{name:'历史任务',exact:true}).getAttribute('aria-expanded'),'false');
 await page.getByRole('button',{name:'审批与证据',exact:true}).click();await noOverflow(page,390,844);await page.getByRole('button',{name:'关闭执行详情',exact:true}).click();
 await settings(page,'接入与管理');await noOverflow(page,390,844);await page.screenshot({path:path.join(out,'tools-mobile.png')});
 const after=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;assert.deepEqual(after.map(t=>t.id).sort(),before.map(t=>t.id).sort());
 for(const original of before){const current=after.find(t=>t.id===original.id);for(const kind of ['MODEL_EXCHANGE','AGENT_ATTEMPT','HUMAN_APPROVAL','RESERVE_REQUEST'])assert.equal(current.events.filter(e=>e.kind===kind).length,original.events.filter(e=>e.kind===kind).length);assert.equal(current.record?.reservation_evidence?.tx_hash,original.record?.reservation_evidence?.tx_hash);assert.equal(current.record?.finalization_evidence?.tx_hash,original.record?.finalization_evidence?.tx_hash);}
 for(const role of ['biz','security']){
  const ctx=await browser.newContext(),p=await ctx.newPage();observe(p);await login(p,role);assert.equal(await p.getByLabel('任务内容').count(),0);
  await p.locator('.task').filter({has:p.locator(`code[title="${finalized.id}"]`)}).click();await p.getByLabel('审批与执行详情').waitFor();
  assert.equal(await p.getByTestId('reserve-execute').count(),0);await p.getByRole('button',{name:'审阅原意图与邮件参数',exact:true}).click();await p.locator('.review').waitFor();
  assert.ok(await p.getByRole('button',{name:/批准此意图/}).isDisabled());
  await settings(p,'接入与管理');await p.getByLabel('自定义工具管理').waitFor();assert.equal(await p.getByText('注册新的查询工具',{exact:true}).count(),0);
  await p.getByRole('button',{name:'退出',exact:true}).click();await p.getByRole('heading',{name:'进入工作空间',exact:true}).waitFor();await ctx.close();
 }
 report.checks.push('persisted conversation matches actual task/events; original signed MIME verified; 320/390/750/1024 responsive; mobile history; independent approvers cannot create or execute; terminal approvals disabled');
 assert.ok(report.writes.every(r=>['/ops/v1/login','/ops/v1/logout'].includes(r.path)));assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';report.existing_tasks=before.length;report.new_tasks=0;report.new_model_calls=0;report.new_tool_dispatches=0;save();console.log('PASS: conversation, settings, roles, persisted task/MIME, responsive layouts; no business writes');
}catch(error){report.status='FAIL';report.failure=error.message;save();throw error;}finally{await browser.close();}
