// Real browser + real configured model + isolated document container. No mocked routes.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const [runtimePath,out,source]=process.argv.slice(2),runtime=JSON.parse(fs.readFileSync(runtimePath,'utf8'));
const pdfSource=path.extname(source).toLowerCase()==='.pdf',sourceName=path.basename(source);
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${runtime.port}`,passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(runtimePath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});const report={status:'RUNNING',real_http:true,real_llm:null,real_llm_requested:true,mocked_routes:false,errors:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
try{
 const page=await browser.newPage({viewport:{width:1500,height:1100}});page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(base);await page.getByLabel('登录身份').selectOption('requester');await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 await page.getByRole('navigation',{name:'工作空间导航'}).getByRole('link',{name:'工具与设置',exact:true}).click();
 for(const tool of ['doc.list','doc.search','doc.read','mail.list','mail.read','mail.send']){const input=page.getByRole('checkbox',{name:tool,exact:true});if(await input.isChecked())await input.uncheck();}
 await page.getByRole('link',{name:'保存选择，返回对话',exact:true}).click();
 await page.getByLabel('添加文档附件').setInputFiles(source);await page.getByRole('button',{name:'移除附件 '+sourceName,exact:true}).waitFor({timeout:90000});
 await page.getByLabel('允许生成 / 修改 Word、PDF 副本',{exact:true}).check();
 await page.getByLabel('任务内容').fill(pdfSource?
  '请先通过 attachment_read 读取上传的 source.pdf 的所有页面并引用实际 source_id 和 page 位置。然后调用 document_create 将原文完整转录为新的 Word 文档，包括负责人 Alice、预算 1000 元及第01条至第40条的全部正文，逐条保留，不要缩写或省略。再调用 document_create 生成一份中文 PDF 摘要，包含负责人 Alice 和预算 1000 元。两份文件必须真实生成，原件保留，不发送邮件。':
  '请读取上传的 source.docx，给出负责人和预算并引用实际 source_id 和 paragraph 位置。然后将原文中 Alice 全部替换为 Bob，调用 document_revise 生成新的 Word 修订副本；再调用 document_create 生成一份中文 PDF 摘要，包含修改后的负责人 Bob 和预算 1000 元。两份文件都必须真实生成，原件保留，不发送邮件。');
 await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).click();
 let job;for(let i=0;i<160;i++){const tasks=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;job=tasks[0];if(job&&!['QUEUED','AGENT_RUNNING'].includes(job.display_state))break;await page.waitForTimeout(1500);}
 assert.ok(job);report.task_id=job.id;report.state=job.display_state;report.model=job.model;
 report.attempts=job.events.filter(e=>e.kind==='AGENT_ATTEMPT').map(e=>({tool:e.tool_name,verdict:e.policy_verdict,executed:e.tool_executed,source_id:e.arguments.source_id||null,document_execution_id:e.result.document_execution_id||null}));
 assert.equal(job.display_state,'DOCUMENT_COMPLETED',job.error);assert.equal(job.record,null);
 assert.ok(report.attempts.some(e=>e.tool==='attachment.read'&&e.executed));
 if(!pdfSource)assert.ok(report.attempts.some(e=>e.tool==='document.revise'&&e.executed));
 assert.ok(report.attempts.some(e=>e.tool==='document.create'&&e.executed));
 assert.ok(job.events.some(e=>e.kind==='MODEL_EXCHANGE'&&e.exchange.http_status===200));
 report.real_llm=true;report.model_exchanges=job.events.filter(e=>e.kind==='MODEL_EXCHANGE').length;
 const exchanges=job.events.filter(e=>e.kind==='MODEL_EXCHANGE').map(e=>e.exchange);
 report.model_config=job.model_config;report.finish_reasons=exchanges.map(e=>e.response?.choices?.[0]?.finish_reason);
 assert.equal(job.model_config.parameters.max_tokens,8192);
 assert.ok(!report.finish_reasons.includes('length'));
 report.max_tool_argument_chars=Math.max(0,...exchanges.flatMap(e=>(e.response?.choices?.[0]?.message?.tool_calls||[]).map(c=>c.function.arguments.length)));
 if(pdfSource)assert.ok(report.max_tool_argument_chars>2000,'long-document JSON must exceed the small fixture size');
 assert.deepEqual(job.allowed_tools,[]);assert.deepEqual(job.allowed_recipients,[]);
 assert.equal(job.documents.artifacts.length,2);report.artifacts=[];
 for(const file of job.documents.artifacts){const response=await page.request.get(base+`/ops/v1/tasks/${job.id}/documents/${file.id}`);assert.equal(response.status(),200);const raw=await response.body();assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),file.sha256);assert.equal(raw.subarray(0,2).toString(),file.extension==='pdf'?'%P':'PK');fs.writeFileSync(path.join(out,'model-output.'+file.extension),raw);report.artifacts.push({id:file.id,extension:file.extension,sha256:file.sha256,size:raw.length});}
 const sourceFile=job.documents.attachments[0];const original=await(await page.request.get(base+`/ops/v1/tasks/${job.id}/documents/${sourceFile.id}`)).body();assert.deepEqual(original,fs.readFileSync(source));
 await page.getByLabel('任务文档与下载').waitFor();await page.screenshot({path:path.join(out,'documents-desktop.png'),fullPage:true});
 await page.reload();await page.locator('.identity').waitFor();await page.locator('.task').first().click();await page.getByLabel('任务文档与下载').waitFor();assert.equal(await page.getByLabel('任务文档与下载').getByRole('link').count(),3);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(out,'documents-mobile.png'),fullPage:true});
 assert.deepEqual(report.errors,[]);report.original_unchanged=true;report.refresh_preserves_outputs=true;report.status='PASS';save();console.log('PASS: new web upload, real DeepSeek read/revise/create, two real downloads, source hash and refresh');
}catch(error){report.status='FAIL';report.failure=error.message;save();throw error;}finally{await browser.close();}
