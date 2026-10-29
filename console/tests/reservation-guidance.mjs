import {openDetails} from './navigation.mjs';
// Read-only browser review of an already-expired real task; never executes it.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const [depPath,diagnosisPath,out]=process.argv.slice(2);
assert.ok(!fs.existsSync(out));
const d=JSON.parse(fs.readFileSync(depPath,'utf8'));
const initial=JSON.parse(fs.readFileSync(diagnosisPath,'utf8')).jobs[0];
const passwords=Object.fromEntries(fs.readFileSync(d.access_file,'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
try{
 const p=await browser.newPage();
 await p.goto(d.business_url);await p.getByLabel('登录身份').selectOption('requester');await p.getByLabel('登录密码').fill(passwords.requester);
 await p.getByRole('button',{name:'登录',exact:true}).click();await p.locator('.identity').waitFor();
 const button=p.locator('.task').filter({has:p.locator('code',{hasText:initial.id.slice(0,18)})});await button.waitFor();await button.click();
 await openDetails(p);
 await p.getByTestId('workflow-step').filter({hasText:'动作已过期，无法预约'}).waitFor();
 assert.ok(await p.getByTestId('reserve-execute').isDisabled());
 const audit=await browser.newPage();await audit.goto(d.audit_url);await audit.getByLabel('搜索动作').fill(initial.action_id);await audit.locator('.row-link').first().click();
 await audit.getByRole('button',{name:'实时核验',exact:true}).click();await audit.getByText('未形成链上预约',{exact:true}).waitFor();
 await audit.locator('.verify-box').filter({hasText:'新建任务'}).waitFor();
 fs.writeFileSync(out,JSON.stringify({status:'PASS',actual_browser:true,user_action_id:initial.action_id,expired_reserve_disabled:true,
    audit_explains_new_task:true,no_write_or_execution:true},null,2));
 console.log('PASS: expired user action explicitly requires new task; no execute request');
}finally{await browser.close();}
