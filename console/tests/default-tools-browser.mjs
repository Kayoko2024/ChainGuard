import {openSettings,openChat} from './navigation.mjs';
// Live UI check. Reads existing tasks; never submits a business task or approval.
import {chromium} from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const [configPath,out]=process.argv.slice(2),config=JSON.parse(fs.readFileSync(configPath,'utf8'));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const passwords=Object.fromEntries(fs.readFileSync(path.join(path.dirname(configPath),'access.local.txt'),'utf8').split(/\r?\n/).filter(l=>l.includes(' : ')).map(l=>l.split(' : ')));
const browser=await chromium.launch({channel:'msedge',headless:true});
const report={status:'RUNNING',business_tasks_created:0,javascript_errors:[]};
try{
 const page=await browser.newPage({viewport:{width:1450,height:1000}});
 page.on('pageerror',e=>report.javascript_errors.push(e.message));
 await page.goto(`http://127.0.0.1:${config.port}/`);
 await page.getByLabel('登录密码').fill(passwords.requester);await page.getByRole('button',{name:'登录',exact:true}).click();
 await openSettings(page,'任务授权');await page.getByLabel('默认工具库').waitFor();
 const tools=(await(await page.request.get(`http://127.0.0.1:${config.port}/ops/v1/tools`)).json()).tools;
 assert.equal(tools.filter(t=>t.enabled&&!t.custom).length,6);
 assert.ok(await page.getByRole('checkbox',{name:'doc.delete',exact:true}).isDisabled());
 await page.getByRole('button',{name:'示例：搜索并总结文档'}).click();await openSettings(page,'任务授权');
 assert.ok(!await page.getByRole('checkbox',{name:'mail.send',exact:true}).isChecked());
 assert.ok(await page.getByRole('checkbox',{name:'doc.search',exact:true}).isChecked());
 await page.getByText('当前为只读任务',{exact:true}).waitFor();
 await page.getByRole('checkbox',{name:'meeting-notes',exact:true}).uncheck();
 await page.getByRole('checkbox',{name:'project-brief',exact:true}).uncheck();
 await openChat(page);assert.ok(await page.getByRole('button',{name:'创建任务并运行真实 Agent',exact:true}).isDisabled());await openSettings(page,'任务授权');
 await page.getByRole('button',{name:'示例：读取本地邮件'}).click();await openSettings(page,'任务授权');
 assert.ok(await page.getByRole('checkbox',{name:'读取 alice@inbox.chainguard.invalid',exact:true}).isChecked());
 await page.getByRole('button',{name:'示例：读取后发送摘要'}).click();await openSettings(page,'任务授权');
 assert.ok(await page.getByRole('checkbox',{name:'mail.send',exact:true}).isChecked());
 await page.getByText('允许发送的收件人',{exact:true}).waitFor();
 await page.screenshot({path:path.join(out,'tools-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:path.join(out,'tools-mobile.png'),fullPage:true});
 assert.deepEqual(report.javascript_errors,[]);
 report.status='PASS';report.tools=tools.map(t=>({name:t.name,enabled:t.enabled}));
}finally{
 fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));await browser.close();
}
