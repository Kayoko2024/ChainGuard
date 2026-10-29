import React,{useEffect,useState} from 'react';
import {githubRegistration} from './github-tools.mjs';
import {registrationFrom} from './custom-management.mjs';
import acceptance from './github-acceptance.json';
const newKey=()=> '0x'+Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');
export function GitHubToolForm({api,action,onRegistered,source,onCancel}){
 const [name,N]=useState('custom.github_lookup'),[resources,R]=useState('microsoft/vscode\nmicrosoft/vscode#1'),[key,K]=useState(newKey),[preset,P]=useState(false);
 const [open,O]=useState(false);
 useEffect(()=>{if(source){N(source.manifest.name);R(source.records.map(r=>r.resource).join('\n'));K(newKey());P(false);O(true);}},[source]);
 return <details className="github-registration" open={open} onToggle={e=>O(e.currentTarget.open)}><summary>接入真实 GitHub 只读工具</summary><form className="custom-form" aria-label="GitHub 工具接入" onSubmit={e=>{e.preventDefault();action(async()=>{const registration=githubRegistration(name,resources),body=source?{...registrationFrom(source),records:registration.records}:registration;const r=await api(source?`/ops/v1/custom-tools/${source.manifest.revision}/versions`:'/ops/v1/custom-tools','POST',body,{'Idempotency-Key':key});await onRegistered(r);K(newKey());O(false);onCancel?.();});}}>
 {source&&<p className="wide">正在创建 v{source.manifest.version+1}：仓库或 Issue 范围变更须重新审核，原版本和历史任务不变。</p>}
 <label>工具名称<input aria-label="GitHub 工具名称" readOnly={!!source} required pattern="custom\.[a-z][a-z0-9_]{2,31}" value={name} onChange={e=>{N(e.target.value);K(newKey());}}/></label>
 <label className="wide">允许查询的公开仓库 / Issue（每行一项）<textarea aria-label="GitHub 授权资源" rows={4} value={resources} onChange={e=>{R(e.target.value);K(newKey());}} required/></label>
 <div className="wide"><button type="button" disabled={!!source} onClick={()=>{N(acceptance.tool_name);R(acceptance.allowed_resources.join('\n'));K(newKey());P(true);}}>填入 VS Code 验收用例</button>{preset&&<div aria-label="VS Code 验收说明"><p>正常：读取 microsoft/vscode#1。链上拒绝：facebook/react#1。三条键刻意列入本地测试授权，以证明其他仓库由独立链上策略拒绝。新建任务时勾选三条键。</p><p>microsoft/vscode#2 未列入本地授权，预期由工具范围检查拒绝。按钮只填写目录，不注册或运行任务，也不修改链上策略。</p></div>}</div>
 <p className="wide">每次实际查询固定访问 api.github.com，只开放仓库元数据和精确 Issue；不克隆、不写 Issue、不读取私有仓库。仓库授权不会自动包含全部 Issue。提交后仍须 OrgB 审核，再选记录准备任务。</p>
 <div className="buttons"><button className="primary" type="submit">{source?'提交 GitHub 新版本':'提交 GitHub 工具待审版本'}</button>{source&&<button type="button" onClick={()=>{onCancel?.();N('custom.github_lookup');R('microsoft/vscode\nmicrosoft/vscode#1');P(false);K(newKey());}}>取消版本修改</button>}</div></form></details>;
}
