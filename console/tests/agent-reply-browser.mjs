// Existing live task outputs are read only; synthetic Markdown is isolated in a
// separate page for layout/security checks and never submitted as model evidence.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AgentReply} from '../src/AgentReply.mjs';

const [configPath,out]=process.argv.slice(2);
const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.ok(!fs.existsSync(out),'Use a new output directory');fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${config.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configPath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',real_http:true,mocked_routes:false,checks:[],writes:[],javascript_errors:[],private_text_exported:false};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const render=text=>renderToStaticMarkup(React.createElement(AgentReply,{text}));
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 page.on('request',r=>{if(r.url().startsWith(base)&&r.method()!=='GET')report.writes.push({path:new URL(r.url()).pathname,method:r.method()});});
 await page.goto(base);await page.getByLabel('登录身份').selectOption('requester');await page.getByLabel('登录密码').fill(passwords.requester);
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const before=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 const replies=before.filter(t=>t.agent_output&&/^(#{1,6} |\|)|\*\*/m.test(t.agent_output)).slice(0,3);
 assert.ok(replies.length>0,'At least one actual historical Markdown reply required');
 for(const task of replies){
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('.task').filter({has:page.locator(`code[title="${task.id}"]`)}).click();
  const reply=page.locator('.agent-output .agent-reply');await reply.waitFor();
  const comparison=await reply.evaluate((element,expectedHtml)=>{
   const expected=new DOMParser().parseFromString(expectedHtml,'text/html').querySelector('.agent-reply');
   return {text_matches:element.textContent===expected.textContent,
    headings:element.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
    strong:element.querySelectorAll('strong').length,
    expected_headings:expected.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
    expected_strong:expected.querySelectorAll('strong').length,
    executable_resources:element.querySelectorAll('img,script,iframe,form,input').length,
    whitespace:getComputedStyle(element).whiteSpace};
  },render(task.agent_output));
  assert.ok(comparison.text_matches);assert.equal(comparison.headings,comparison.expected_headings);
  assert.equal(comparison.strong,comparison.expected_strong);assert.equal(comparison.executable_resources,0);
  assert.equal(comparison.whitespace,'normal');
  assert.equal(await page.locator('.user-message .message-text').textContent(),task.task_text);
  for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:1000});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Existing reply overflow at ${width}`);
  }
  report.checks.push({task_id:task.id,...comparison});
 }
 await page.reload();await page.locator('.identity').waitFor();
 const after=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 assert.deepEqual(after.map(t=>t.id).sort(),before.map(t=>t.id).sort());
 for(const old of before){
  const current=after.find(t=>t.id===old.id);
  assert.equal(current.agent_output,old.agent_output);assert.deepEqual(current.events,old.events);
  assert.equal(current.record?.reservation_evidence?.tx_hash,old.record?.reservation_evidence?.tx_hash);
  assert.equal(current.record?.finalization_evidence?.tx_hash,old.record?.finalization_evidence?.tx_hash);
 }
 assert.ok(report.writes.every(r=>['/ops/v1/login','/ops/v1/logout'].includes(r.path)));
 report.live_task_count=before.length;report.original_outputs_and_events_unchanged=true;
 report.new_tasks=0;report.new_model_calls=0;report.new_tool_dispatches=0;

 // Synthetic UI fixture: no backend routes, model claims or execution evidence.
 const fixture=await browser.newPage();const network=[];
 fixture.on('request',r=>network.push(r.url()));
 await fixture.route('**/*',r=>r.abort());
 const text='# 文档处理结果\n\n已经整理出**三个重点**，并保留原始文件。\n\n## 主要结论\n\n- 完成授权范围内的读取\n- 将总结生成为新文档\n- 查看系统记录核验实际结果\n\n> 来源：文档第 1 页。\n\n| 产物 | 用途 |\n| --- | --- |\n| Word 文档 | 编辑和补充 |\n| PDF 文档 | 阅读和分享 |\n\n### 代码示例\n\n```python\n# 这是代码注释，应该保留\nresult = "**这也是代码原文**"\n'+ 'x'.repeat(180)+'\n```\n\n这是普通说明。Issue #123 与 2 * 3 应该保持原样。\n\n[参考资料](https://example.com)\n\n![不自动加载](https://attacker.invalid/pixel)\n\n<script>alert("unsafe")</script>';
 const css=fs.readFileSync(new URL('../src/agent-reply.css',import.meta.url),'utf8');
 const reset='*{box-sizing:border-box}body{margin:0;background:#faf8fc;color:#67576f;font-family:"Microsoft YaHei",sans-serif}main{width:min(820px,100%);margin:20px auto;padding:28px;background:white;border:1px solid #ece6f2;border-radius:14px}';
 await fixture.setContent(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>${reset}${css}</style><main>${render(text)}</main></html>`);
 assert.equal(await fixture.locator('script,img,iframe').count(),0);assert.deepEqual(network,[]);
 for(const width of [1100,390,320]){
  await fixture.setViewportSize({width,height:1200});
  assert.ok(await fixture.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Fixture overflow at ${width}`);
  assert.equal(await fixture.locator('pre').evaluate(e=>getComputedStyle(e).whiteSpace),'pre');
  assert.equal(await fixture.locator('.reply-table-scroll').evaluate(e=>getComputedStyle(e).overflowX),'auto');
  if(width!==320)await fixture.screenshot({path:path.join(out,`synthetic-layout-${width}.png`),fullPage:true});
 }
 assert.deepEqual(network,[]);assert.deepEqual(report.javascript_errors,[]);
 report.synthetic_fixture={layout_widths:[1100,390,320],external_requests:0,executable_resources:0,used_as_model_evidence:false};
 report.status='PASS';save();
 console.log('PASS: actual historical replies rendered, original outputs/events unchanged; isolated layout and resource safety verified');
}catch(error){report.status='FAIL';report.failure=error.message;save();throw error;}finally{await browser.close();}
