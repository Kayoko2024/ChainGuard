import React from 'react';
import {ToolPicker} from './ToolPicker.jsx';
import {CustomTools} from './CustomTools.jsx';
import {Icon} from '../../shared/ui.jsx';
import {ToolScopeNotice} from './ToolScopeNotice.jsx';

export function ToolSettings({tab,setTab,role,api,action,catalog,tools,setTools,documents,setDocuments,mailboxes,setMailboxes,custom,setCustom,recipients,setRecipients,preset,onChange,onPrepare,job,scopeIssues=[]}){
 const tabs=[['scope','任务授权'],['manage','接入与管理']];
 return <section className="tool-settings" aria-label="工具与设置">
  <div className="settings-heading"><div><h1>工具与设置</h1><p>默认工具、个人数据和外部接入，在同一个地方管理。</p></div><a className="back-to-chat" href="#tasks"><Icon name="arrow"/>返回对话</a></div>
  <div className="settings-tabs" role="tablist" aria-label="工具设置分类">{tabs.map(([id,label])=><button key={id} id={`tab-${id}`} role="tab" aria-selected={tab===id} aria-controls={`panel-${id}`} tabIndex={tab===id?0:-1} onKeyDown={e=>{const index=tabs.findIndex(t=>t[0]===tab);const next=e.key==='ArrowRight'?(index+1)%tabs.length:e.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:e.key==='Home'?0:e.key==='End'?tabs.length-1:null;if(next!==null){e.preventDefault();setTab(tabs[next][0]);document.getElementById(`tab-${tabs[next][0]}`).focus();}}} onClick={()=>setTab(id)}>{label}</button>)}</div>
  <div id="panel-scope" role="tabpanel" aria-labelledby="tab-scope" hidden={tab!=='scope'}>
   {role==='requester'?<><div className="settings-note"><Icon name="lock"/><span>以下范围用于新会话。当前会话继续沿用创建时的授权；修改不会扩大历史任务权限，也不会自动调用工具。</span></div>
    <div className="panel"><ToolPicker custom={custom} setCustom={setCustom} catalog={catalog} tools={tools} setTools={setTools} documents={documents} setDocuments={setDocuments} mailboxes={mailboxes} setMailboxes={setMailboxes} preset={preset}/>
     <div className="scope-picker"><label>{tools.includes('mail.send')?'允许发送的收件人':'当前为只读任务'}</label><p>{tools.includes('mail.send')?'仅限本地测试邮箱；执行仍须双组织审批。':'不会生成发送动作，无需组织审批或链上预约。'}</p><div className="checks">{(tools.includes('mail.send')?['alice','bob']:[]).map(name=>{const address=name+'@inbox.chainguard.invalid';return <label key={name}><input type="checkbox" checked={recipients.includes(address)} onChange={e=>setRecipients(e.target.checked?[...recipients,address]:recipients.filter(x=>x!==address))}/><span><strong>{name==='alice'?'Alice':'Bob'}</strong><small>{address}</small></span></label>;})}</div></div>
    </div><ToolScopeNotice issues={scopeIssues}/><div className="settings-bottom"><span>已选 {tools.length} 项工具 · {scopeIssues.length?`还有 ${scopeIssues.length} 项授权待补全`:'创建新会话时固化授权'}</span><a className="primary settings-return" href="#tasks"><Icon name="check"/>保存选择，返回对话</a></div></>:<div className="notice"><Icon name="lock"/>任务授权由请求者设置。当前审批身份可审阅任务，OrgB 可在“接入与管理”审核工具。</div>}
  </div>
  <div id="panel-manage" role="tabpanel" aria-labelledby="tab-manage" hidden={tab!=='manage'}><CustomTools api={api} role={role} action={action} onChange={onChange} onPrepare={onPrepare} job={job} catalog={catalog}/></div>
 </section>;
}
