import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configFile,credentialsFile,out,sid]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configFile,'utf8'));
fs.mkdirSync(out,{recursive:false});const base=`http://127.0.0.1:${c.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(credentialsFile),'access.local.txt'),'utf8').split(/\r?\n/).filter(x=>x.includes(' : ')).map(x=>x.split(' : ')));
const report={status:'RUNNING',new_model_calls:0,new_tool_calls:0,new_tasks:0,javascript_errors:[],writes:[]},save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1450,height:1000}});
page.on('pageerror',e=>report.javascript_errors.push(e.message));page.on('request',r=>{if(r.method()!=='GET')report.writes.push({method:r.method(),path:new URL(r.url()).pathname});});
try{
 await page.goto(base);await page.getByLabel('登录身份').selectOption('requester');await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const before=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 await page.evaluate(id=>localStorage.setItem('chainguard.activeConversation.v1',id),sid);await page.reload();await page.getByLabel('任务对话').first().waitFor();assert.equal(await page.getByLabel('任务对话').count(),2);
 await page.getByRole('button',{name:'审批与证据',exact:true}).click();await page.getByLabel('会话授权与批量审计').waitFor();
 assert.match(await page.getByLabel('会话授权与批量审计').innerText(),/区块 #\d+/);
 for(const width of [1450,390,320]){await page.setViewportSize({width,height:1000});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);assert.equal(overflow,false);}
 const after=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 // The record projection hydrates asynchronously from the gateway after restart.
 // Compare durable task identity here; the wrapper separately hashes the original
 // encrypted DB rows, and verify_conversation_sessions rechecks actual receipts.
 const durable=tasks=>tasks.map(t=>[t.id,t.events.length,t.action_id]);
 assert.deepEqual(durable(after),durable(before));
 assert.ok(report.writes.every(w=>w.path==='/ops/v1/login'));assert.deepEqual(report.javascript_errors,[]);report.status='PASS';save();
}catch(e){report.status='FAIL';report.failure=e.message;save();throw e;}finally{await browser.close();}
