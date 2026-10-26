// Actual browser against actual localhost service; no route interception/fixture network.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const [url='http://127.0.0.1:8080',output='browser-smoke.json']=process.argv.slice(2);
assert.match(url,/^http:\/\/127\.0\.0\.1:\d+$/);
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage({viewport:{width:1500,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(url,{waitUntil:'networkidle'});
 await page.getByRole('heading',{name:'动作审计',exact:true}).waitFor();
 await page.getByRole('button',{name:'实时核验',exact:true}).click();
 await page.getByTestId('verification-status').filter({hasText:'实时证据一致'}).waitFor({timeout:60000});
 assert.ok(await page.getByText('OrgA_Business',{exact:true}).count());
 assert.ok(await page.getByText('OrgB_Security',{exact:true}).count());
 await page.getByRole('button',{name:'C · 联盟链',exact:true}).click();
 await page.getByLabel('搜索动作').fill('UNKNOWN');
 await page.locator('tbody .row-link').first().click();
 await page.getByRole('button',{name:'实时核验',exact:true}).click();
 await page.getByTestId('verification-status').filter({hasText:'待回执'}).waitFor({timeout:60000});
 await page.getByLabel('搜索动作').fill('no-such-action');
 await page.getByText('没有匹配记录',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});
 await page.getByLabel('搜索动作').fill('');
 assert.ok(await page.locator('tbody .row-link').count());
 assert.equal(errors.length,0);
 fs.writeFileSync(output,JSON.stringify({status:'PASS',browser:'Microsoft Edge / Playwright',actual_http:true,fixture_routes:false,verified_signature_and_organizations:true,unknown_preserved:true,search_and_group_filter:true,mobile_viewport:true,javascript_errors:errors},null,2));
 console.log('Actual browser/HTTP/ledger smoke PASS');
}finally{await browser.close();}
