// Isolated component/layout fixture. Synthetic metadata only; no upload/API/LLM calls.
import {chromium} from 'playwright';
import {build} from 'esbuild';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const out=process.argv[2],tests=path.dirname(fileURLToPath(import.meta.url));
assert.ok(!fs.existsSync(out));fs.mkdirSync(out,{recursive:true});
const report={status:'RUNNING',scope:'isolated React attachment UI fixture; synthetic file metadata only',layout:[],checks:[]};
const save=()=>fs.writeFileSync(path.join(out,'browser.json'),JSON.stringify(report,null,2));
const fixture=`import React,{useState} from 'react';import{createRoot}from'react-dom/client';import{DocumentAttachments}from'../src/DocumentAttachments.jsx';
function Fixture(){const[files,setFiles]=useState(Array.from({length:4},(_,i)=>({id:'fixture-'+i,name:'非常长的测试文档名称_合同与数据说明_版本_'+i+'.pdf',size:2048})));const[allow,setAllow]=useState(false);const[locked,setLocked]=useState(false);return <div className="shell chat-shell"><div className="conversation-main"><div className="conversation-layout"><section className="conversation-center"><div className="conversation-scroll"><p>组件布局测试 / 合成文档信息</p><button onClick={()=>setLocked(!locked)}>切换锁定</button></div><div className="composer-dock"><div className="composer-container"><div className="composer-utilities"><DocumentAttachments files={files} setFiles={setFiles} allowCreate={allow} setAllowCreate={setAllow} busy={false} locked={locked} upload={()=>{throw Error('No upload in UI fixture')}}/></div><form className="chat-composer"><textarea aria-label="任务内容" rows={3}/></form></div></div></section></div></div></div>;}createRoot(document.getElementById('root')).render(<Fixture/>);`;
const bundled=await build({stdin:{contents:fixture,loader:'jsx',resolveDir:tests},nodePaths:[path.join(tests,'../node_modules')],bundle:true,write:false,format:'iife',platform:'browser',define:{'process.env.NODE_ENV':'"production"'}}).catch(e=>{report.status='FAIL';report.error='Fixture bundle could not resolve its dependencies';save();throw e;});
const css=['shared/theme.css','console/src/style.css','console/src/conversation.css'].map(f=>fs.readFileSync(path.join(tests,'../..',f),'utf8')).join('\n');
const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage();
try{
 await page.setContent(`<style>${css}</style><div id="root"></div>`);await page.addScriptTag({content:bundled.outputFiles[0].text});await page.getByLabel('本次任务附件').waitFor();
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:800});
  const layout=await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,attachments:document.querySelector('.document-composer').getBoundingClientRect().height,chips:document.querySelector('.attachment-chips').getBoundingClientRect().height,chat:document.querySelector('.conversation-scroll').getBoundingClientRect().height}));
  assert.ok(layout.documentWidth<=width+1);assert.ok(layout.attachments<=95);report.layout.push(layout);
 }
 await page.screenshot({path:path.join(out,'four-attachments-320.png')});
 assert.equal(await page.locator('.attachment-chips li').count(),4);assert.ok(await page.getByLabel('添加文档附件').isDisabled());
 await page.getByRole('button',{name:'移除附件 非常长的测试文档名称_合同与数据说明_版本_0.pdf',exact:true}).click();
 assert.equal(await page.locator('.attachment-chips li').count(),3);assert.ok(await page.getByLabel('添加文档附件').isEnabled());
 await page.getByRole('checkbox',{name:'允许生成 / 修改 Word、PDF 副本'}).check();
 await page.getByRole('button',{name:'切换锁定',exact:true}).click();assert.ok(await page.getByLabel('添加文档附件').isDisabled());
 assert.ok(await page.getByRole('checkbox',{name:'允许生成 / 修改 Word、PDF 副本'}).isDisabled());assert.equal(await page.getByRole('button',{name:/移除附件/}).count(),0);
 await page.getByText('文件说明',{exact:true}).click();assert.ok(await page.getByText(/修改范围请新建会话/).isVisible());
 report.checks.push('4 long attachment names remain one scrollable row','remove updates only selected metadata and restores file picker','existing conversation locks upload/output permission/removal');report.status='PASS';save();
}catch(e){report.status='FAIL';report.error=String(e);save();throw e;}finally{await browser.close();}
console.log(JSON.stringify({status:report.status,checks:report.checks.length}));
