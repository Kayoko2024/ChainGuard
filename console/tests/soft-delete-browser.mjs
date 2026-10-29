// Mutates only the explicitly prepared isolated acceptance conversation.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {verificationLabels} from '../../dashboard/src/format.mjs';
const [configFile,sourceConfig,out,job]=process.argv.slice(2),c=JSON.parse(fs.readFileSync(configFile,'utf8'));
assert.ok(c.acceptance_only&&c.port===8092);assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const credentials=Object.fromEntries(fs.readFileSync(path.join(path.dirname(sourceConfig),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const report={status:'RUNNING',dialogs:[],checks:[],verify_http_status:null};const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1280,height:800}});
page.on('dialog',async d=>{report.dialogs.push(d.type());await d.dismiss();});
try{
 await page.goto('http://127.0.0.1:8092/');await page.getByLabel('登录密码').fill(credentials.requester);await page.getByRole('button',{name:'登录',exact:true}).click();
 const row=page.locator('.task-list-row').filter({has:page.locator(`code[title="${job}"]`)});await row.waitFor();await row.hover();
 const deleted=page.waitForResponse(r=>r.request().method()==='DELETE');await row.getByRole('button',{name:`删除 ${job}`,exact:true}).click();assert.equal((await deleted).status(),200);await row.waitFor({state:'detached'});
 assert.equal(await page.locator('.task-list-row').count(),0);assert.deepEqual(report.dialogs,[]);
 await page.reload();await page.locator('.identity').waitFor();assert.equal(await page.locator('.task-list-row').count(),0);report.checks.push('delete hides the prepared conversation immediately and after refresh, without dialogs');
 const audit=await browser.newPage();await audit.goto('http://127.0.0.1:8093/');const entry='interactive-'+job.slice(2);
 const response=audit.waitForResponse(r=>r.url().includes(`/actions/${entry}/verify`));await audit.getByRole('button',{name:'实时核验',exact:true}).click();const initial=await response;report.verify_http_status=initial.status();assert.equal(initial.status(),202);
 const accepted=await initial.json();let result;
 for(let i=0;i<120;i++){result=await(await audit.request.get('http://127.0.0.1:8093/audit-api/v1/verifications/'+accepted.verification_id)).json();if(result.status==='COMPLETED')break;await new Promise(r=>setTimeout(r,300));}
 assert.equal(result.result.status,'VERIFIED');assert.equal(result.result.tool_signature_valid,true);report.verification=result.result;
 await audit.getByTestId('verification-status').filter({hasText:verificationLabels.VERIFIED}).waitFor();await audit.reload();const rows=(await(await audit.request.get('http://127.0.0.1:8093/audit-api/v1/actions')).json()).actions;assert.ok(rows.some(r=>r.entry_id===entry));
 report.checks.push('hidden record remains in audit; realtime button returns 202 then four-node VERIFIED with the original tool signature');report.status='PASS';save();
}catch(e){report.status='FAIL';report.error=String(e);save();throw e;}finally{await browser.close();}
console.log(JSON.stringify({status:report.status,checks:report.checks.length}));
