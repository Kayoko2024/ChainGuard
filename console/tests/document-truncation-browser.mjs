// Read-only verification of the actual historical failed task. No task replay.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {taskError,outputTruncation} from '../src/task-error.mjs';
import {activeSessionKey} from '../src/session-state.mjs';
const [runtimePath,taskId,out]=process.argv.slice(2);
const runtime=JSON.parse(fs.readFileSync(runtimePath,'utf8'));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const base=`http://127.0.0.1:${runtime.port}`;
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(runtimePath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',real_http:true,mocked_routes:false,checks:[],new_business_tasks_created:0,model_reexecuted:false,private_text_exported:false};
try{
 const page=await browser.newPage();const writes=[];
 page.on('request',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.method()))writes.push(new URL(r.url()).pathname);});
 await page.goto(base);await page.getByLabel('登录身份').selectOption('requester');await page.getByLabel('登录密码').fill(passwords.requester);
 await page.getByRole('button',{name:'登录',exact:true}).click();await page.locator('.identity').waitFor();
 const tasks=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 report.available_truncations=tasks.filter(t=>outputTruncation(t)).map(t=>({id:t.id,...outputTruncation(t)}));
 // "all" checks both real historical failure categories without replaying either.
 const selected=taskId==='all'?['reply','tool_arguments'].map(kind=>tasks.find(t=>outputTruncation(t)?.kind===kind)):[tasks.find(t=>t.id===taskId)];
 assert.ok(selected.every(Boolean),'Required historical truncation records must exist');
 for(const before of selected){
  const truncated=outputTruncation(before);assert.ok(truncated);
  assert.ok(['SCHEMA_INVALID','MODEL_OUTPUT_TRUNCATED'].includes(before.error));
  if(before.conversation_id){
   await page.evaluate(({key,id})=>localStorage.setItem(key,id),{key:activeSessionKey,id:before.conversation_id});
   await page.reload();await page.locator('.identity').waitFor();
  }else{
   await page.locator('.task').filter({has:page.locator(`code[title="${before.id}"]`)}).click();
  }
  await page.getByLabel('系统执行状态').filter({hasText:taskError(before)}).first().waitFor();
  assert.doesNotMatch(taskError(before),/请新建任务/);
  report.checks.push({task_id:before.id,kind:truncated.kind,max_tokens:truncated.max_tokens,correct_explanation_visible:true});
 }
 await page.reload();await page.locator('.identity').waitFor();
 const after=(await(await page.request.get(base+'/ops/v1/tasks')).json()).tasks;
 assert.equal(after.length,tasks.length);
 for(const before of tasks){
  const original=after.find(t=>t.id===before.id);assert.ok(original);
  assert.ok(JSON.stringify(original.events)===JSON.stringify(before.events),'Original events must be unchanged');
  assert.equal(original.error,before.error);
  assert.equal(original.agent_output,before.agent_output);
 }
 assert.ok(writes.every(p=>p==='/ops/v1/login'||p==='/ops/v1/logout'));
 report.status='PASS';report.stored_errors_and_events_unchanged=true;report.new_truncation_explanation_visible=true;report.task_count=after.length;
}catch(error){report.status='FAIL';report.error_type=error.name;report.error=error.message;throw error;}
finally{fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));await browser.close();}
console.log('PASS: actual historical truncations explained, original failures/events preserved, no task replay');
