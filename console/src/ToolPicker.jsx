import React,{useState} from 'react';
import {toolAuthorizationLabel} from './tool-selection.mjs';
import {toolCategories,toolCategory,toolIcon,matchesTool} from './tool-catalog.mjs';
import {Icon} from '../../shared/ui.jsx';

export function ToolPicker({catalog,tools,setTools,documents,setDocuments,mailboxes,setMailboxes,preset,custom=[],setCustom}){
 const [query,setQuery]=useState(''),[category,setCategory]=useState('all');
 const toggle=(list,value,checked)=>checked?[...list,value]:list.filter(v=>v!==value);
 return <section className="tool-library" aria-label="默认工具库"><div className="sectionhead"><h3>本任务可用工具</h3><span>逐任务授权 · 默认沙箱</span></div>
 <div className="catalog-toolbar"><label className="catalog-search"><Icon name="search"/><input aria-label="搜索可用工具" placeholder="搜索名称、用途或 API" value={query} onChange={e=>setQuery(e.target.value)}/></label><span className="catalog-count">已选 {tools.length} 项</span></div>
 <div className="catalog-categories" aria-label="可用工具分类">{toolCategories.map(c=><button type="button" key={c.id} aria-pressed={category===c.id} onClick={()=>setCategory(c.id)}>{c.label} · {catalog.tools.filter(t=>c.id==='all'||toolCategory(t)===c.id).length}</button>)}</div>
 <div className="tool-cards">{catalog.tools.filter(t=>matchesTool(t,query,category)).map(t=><label key={t.name} className={'tool-card '+(tools.includes(t.name)?'is-selected ':'')+(!t.enabled?'disabled':'')}><input type="checkbox" aria-label={t.name} disabled={!t.enabled} checked={tools.includes(t.name)} onChange={e=>setTools(toggle(tools,t.name,e.target.checked))}/><span className="catalog-icon"><Icon name={toolIcon(t)}/></span><span className="tool-card-copy"><strong>{t.label}</strong><code>{t.name}</code><span>{t.description}</span></span><small className="tool-permission" title={toolAuthorizationLabel(t)}>R{t.risk} · {toolAuthorizationLabel(t)}</small></label>)}</div>
 {!catalog.tools.some(t=>matchesTool(t,query,category))&&<p className="catalog-empty">没有匹配的工具，试试其他关键词或分类。</p>}
 {tools.some(t=>t.startsWith('doc.'))&&<fieldset><legend>允许读取的测试文档</legend>{catalog.documents.map(d=><label key={d.doc_id}><input type="checkbox" aria-label={d.doc_id} checked={documents.includes(d.doc_id)} onChange={e=>setDocuments(toggle(documents,d.doc_id,e.target.checked))}/>{d.title} <code>{d.doc_id}</code></label>)}</fieldset>}
 {tools.some(t=>['mail.list','mail.read'].includes(t))&&<fieldset><legend>允许读取的本地测试邮箱（与发送权限分别授权）</legend>{catalog.mailboxes.map(m=><label key={m}><input type="checkbox" aria-label={'读取 '+m} checked={mailboxes.includes(m)} onChange={e=>setMailboxes(toggle(mailboxes,m,e.target.checked))}/>{m}</label>)}<p>只读取沙箱中实际存在的邮件；空邮箱返回空列表，不预填邮件。</p></fieldset>}
 {catalog.tools.filter(t=>t.custom&&tools.includes(t.name)).map(t=>{const grant=custom.find(g=>g.name===t.name&&g.revision===t.revision);return <fieldset key={t.revision}><legend>{t.label} · v{t.version} · 允许查询的记录键</legend><code>{t.revision}</code>{t.resources.map(k=><label key={k}><input type="checkbox" aria-label={`${t.name} 记录 ${k}`} checked={grant?.allowed_keys.includes(k)||false} onChange={e=>setCustom([...custom.filter(g=>g.name!==t.name),{name:t.name,revision:t.revision,allowed_keys:toggle(grant?.allowed_keys||[],k,e.target.checked)}])}/>{k}</label>)}<p>未选记录不可查询；任务精确绑定本版本。</p></fieldset>;})}
 <div className="buttons"><button type="button" onClick={()=>preset('read')}>示例：搜索并总结文档</button><button type="button" onClick={()=>preset('mail')}>示例：读取后发送摘要</button><button type="button" onClick={()=>preset('inbox')}>示例：读取本地邮件</button></div></section>;
}
