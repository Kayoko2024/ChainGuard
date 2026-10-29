import React,{useEffect,useRef,useState} from 'react';
import examples from './custom-tool-examples.json';
import {ImportData} from './ImportData.jsx';
import {GitHubToolForm} from './GitHubToolForm.jsx';
import {HttpToolForm} from './HttpToolForm.jsx';
import {GitHubPolicyPanel} from './GitHubPolicyPanel.jsx';
import {registrationFrom} from './custom-management.mjs';
import {Icon} from '../../shared/ui.jsx';
import {groupToolVersions,matchesTool,matchesState,toolIcon,catalogState} from './tool-catalog.mjs';
const newKey=()=> '0x'+Array.from(crypto.getRandomValues(new Uint8Array(32)),b=>b.toString(16).padStart(2,'0')).join('');

export function CustomTools({api,role,action,onChange,onPrepare,job,catalog}){
 const [items,I]=useState([]),[review,R]=useState(null),[name,N]=useState('custom.project_lookup'),[label,L]=useState('项目资料查询');
 const [description,D]=useState('按项目编号查询已授权的项目资料。'),[key,K]=useState('project_id'),[fields,F]=useState('project_id, owner, status'),[records,B]=useState('');
 const [example,X]=useState(null);
 const [base,V]=useState(null),[formOpen,O]=useState(false),[taskKeys,Q]=useState([]),[requestKey,J]=useState(newKey);
 const [adapter,A]=useState('dataset.lookup');
 const [httpEdit,H]=useState(null);
 const [connection,setConnection]=useState('http'),[githubEdit,setGithubEdit]=useState(null);
 const [riskLevel,setRiskLevel]=useState('');
 const [query,setQuery]=useState(''),[status,setStatus]=useState('all'),[category,setCategory]=useState('all'),[intakeOpen,setIntakeOpen]=useState(false);
 const intake=useRef(null),detail=useRef(null),opener=useRef(null);
 const grouped=groupToolVersions(items);
 const visible=grouped.filter(t=>matchesTool(t,query,category)&&matchesState(t,status));
 function openIntake(){setIntakeOpen(true);R(null);setTimeout(()=>intake.current?.scrollIntoView({block:'start',behavior:'smooth'}),0);}
 function closeReview(){R(null);opener.current?.focus();}
 async function inspect(t,event){opener.current=event?.currentTarget;R(await api(`/ops/v1/custom-tools/${t.revision}`));Q([]);}
 useEffect(()=>{if(review)detail.current?.focus();},[review?.manifest.revision]);
 useEffect(()=>{const escape=e=>{if(e.key==='Escape'&&review)closeReview();};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[review]);
 useEffect(()=>setRiskLevel(review?.admission?.risk_level||''),[review?.manifest.revision]);
 function fill(value){A(value.adapter);N(value.name);L(value.label);D(value.description);K(value.key_field);F(value.output_fields.join(', '));B(JSON.stringify(value.records,null,2));J(newKey());}
 function fillExample(item){fill(item.registration);X(item);V(null);setConnection('dataset');}
 async function refresh(){const data=await api('/ops/v1/custom-tools');I(data.tools);}
 useEffect(()=>{action(refresh);const timer=setInterval(()=>refresh().catch(()=>{}),10000);return()=>clearInterval(timer);},[role]);
 async function register(){const value={name,label,description,adapter,risk:0,key_field:key,output_fields:fields.split(',').map(v=>v.trim()),records:JSON.parse(records)};
  const result=await api(base?`/ops/v1/custom-tools/${base}/versions`:'/ops/v1/custom-tools','POST',value,{'Idempotency-Key':requestKey});await refresh();R(await api(`/ops/v1/custom-tools/${result.revision}`));Q([]);V(null);O(false);J(newKey());await onChange();}
 async function activate(enabled){await api(`/ops/v1/custom-tools/${review.manifest.revision}/activation`,'POST',{revision:review.manifest.revision,enabled,risk_level:riskLevel});R(await api(`/ops/v1/custom-tools/${review.manifest.revision}`));await refresh();await onChange();}
 return <section className="panel custom-library" aria-label="自定义工具管理"><div className="panel-head"><div><h2>已接入工具 <span className="count">{grouped.length}</span></h2><p className="catalog-subtitle">按工具管理，按版本审核。</p></div>{role==='requester'&&<button className="primary" type="button" onClick={openIntake}><Icon name="plus"/>接入新工具</button>}</div><div className="panel-body">
 {role==='requester'&&<div ref={intake} hidden={!intakeOpen} className="connection-intake" aria-label="添加工具"><div className="intake-heading"><h3>连接你的工具</h3><button type="button" onClick={()=>setIntakeOpen(false)}>收起接入表单</button></div>
 <label>接入方式<select aria-label="工具接入方式" value={connection} onChange={e=>setConnection(e.target.value)}><option value="http">通用 API · 自填地址与参数</option><option value="github">应用模板 · GitHub 仓库与 Issue</option><option value="dataset">个人数据 · CSV / JSON</option></select></label>
 <p>{connection==='http'?'适用于公开查询、天气或识别类 JSON API，支持 GET / POST。':connection==='github'?'GitHub 是预配置的 API 模板，保留只读与链上仓库范围检查。': '导入联系人、库存等资料，按记录键查询并管理版本。'}</p>
 <div hidden={connection!=='http'}><HttpToolForm api={api} action={action} source={httpEdit} onCancel={()=>H(null)} onRegistered={async r=>{await refresh();R(await api(`/ops/v1/custom-tools/${r.revision}`));Q([]);await onChange();}}/></div>
 <div hidden={connection!=='github'}><GitHubToolForm api={api} action={action} source={githubEdit} onCancel={()=>setGithubEdit(null)} onRegistered={async r=>{await refresh();R(await api(`/ops/v1/custom-tools/${r.revision}`));Q([]);await onChange();}}/></div>
 <div hidden={connection!=='dataset'}><details open={formOpen} onToggle={e=>O(e.currentTarget.open)}><summary>注册新的查询工具</summary><form className="custom-form" onChange={()=>J(newKey())} onSubmit={e=>{e.preventDefault();action(register);}}>
 {base&&<div className="custom-example-picker" aria-label="新版本来源"><strong>基于原版本创建修改版</strong><code>{base}</code><p>工具名保持一致；旧资料和任务不变，新版本须重新审核。</p><button type="button" onClick={()=>{V(null);J(newKey());}}>取消版本关联，改为注册</button></div>}
 <div className="custom-example-picker"><div className="buttons">{examples.map(item=><button key={item.id} type="button" onClick={()=>fillExample(item)}>填入{item.title}示例</button>)}</div><p>示例均为合成资料，只填写表单。可修改后提交，仍需安全身份审核启用。</p>{example&&<div aria-label="示例任务说明"><strong>{example.title} · 启用后可尝试</strong><p>{example.task_example}</p><small>新建任务时勾选本工具和目标记录键。查询权限不授予发送、库存调整或采购权限。</small></div>}</div>
 <label>工具名称<input aria-label="自定义工具名称" value={name} readOnly={!!base} onChange={e=>N(e.target.value)} required pattern="custom\.[a-z][a-z0-9_]{2,31}"/></label>
 <label>显示名称<input aria-label="自定义工具显示名称" value={label} onChange={e=>L(e.target.value)} required maxLength={60}/></label>
 <label>用途描述<textarea aria-label="自定义工具描述" value={description} onChange={e=>D(e.target.value)} required maxLength={500}/></label>
 <label>记录键字段<input aria-label="记录键字段" value={key} readOnly={adapter==='github.read'} onChange={e=>K(e.target.value)} required/></label>
 <label>返回字段（英文逗号分隔）<input aria-label="返回字段" value={fields} readOnly={adapter==='github.read'} onChange={e=>F(e.target.value)} required/></label>
 {adapter==='dataset.lookup'?<ImportData api={api} action={action} onUse={p=>{B(JSON.stringify(p.records,null,2));F(p.columns.join(', '));if(!p.columns.includes(key))K(p.columns[0]);J(newKey());}}/>:<p className="wide">当前为 GitHub 实时适配器：下面 JSON 只配置授权 resource，不包含或预填 GitHub 查询结果。输出字段保持固定。</p>}
 <label className="wide">资料 JSON（最多 200 条，同列同类型）<textarea aria-label="自定义工具资料" rows={5} value={records} onChange={e=>B(e.target.value)} required placeholder='[{"project_id":"DEMO-1","owner":"Alice","status":"测试中"}]'/></label>
 <div className="buttons"><button type="button" onClick={()=>{B(JSON.stringify([{project_id:'DEMO-1',owner:'Alice',status:'测试中'},{project_id:'DEMO-2',owner:'Bob',status:'待评审'}],null,2));J(newKey());}}>填入合成示例资料</button><button className="primary" type="submit">{base?'提交修改后的新版本':'提交待审版本'}</button></div></form></details></div></div>}
 {(connection==='github'||review?.manifest.adapter==='github.read')&&<details className="connection-policy"><summary>仓库策略与验证</summary><GitHubPolicyPanel api={api} action={action} job={job} catalog={catalog} role={role}/></details>}
 <div className="catalog-toolbar"><label className="catalog-search"><Icon name="search"/><input aria-label="搜索已接入工具" placeholder="搜索工具名称或用途" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="筛选工具状态" value={status} onChange={e=>setStatus(e.target.value)}><option value="all">全部状态</option><option value="ACTIVE">已启用</option><option value="pending">待处理版本</option><option value="DISABLED">含停用版本</option></select></div>
 <div className="catalog-categories" aria-label="已接入工具分类">{[['all','全部接入'],['api','外部 API'],['data','个人数据']].map(([id,label])=><button type="button" key={id} aria-pressed={category===id} onClick={()=>setCategory(id)}>{label}</button>)}</div>
 <div className="managed-tools custom-versions" aria-label="已接入工具列表">{visible.map(t=><article className="managed-tool-row" key={t.name}>
  <button type="button" className="tool-row-open" onClick={e=>action(()=>inspect(t,e))}><span className="catalog-icon"><Icon name={toolIcon(t)}/></span><span className="tool-row-copy"><strong>{t.label}</strong><code>{t.name}</code><small>{t.description||({ 'http.request':'通用 API · 查询 / 推理','github.read':'GitHub · 仓库与 Issue','dataset.lookup':'个人数据 · 结构化查询'}[t.adapter])}</small></span><span className="tool-row-state"><span className={'catalog-status state-'+t.state}>{catalogState[t.state]||t.state}</span><small>最新 v{t.version}{t.active&&t.active.version!==t.version?` · 启用 v${t.active.version}`:''}</small></span><Icon name="chevron"/></button>
  <details className="tool-version-history"><summary>{t.versions.length} 个版本 · 查看版本记录</summary><div className="tool-version-list">{t.versions.map(v=><button type="button" key={v.revision} onClick={e=>action(()=>inspect(v,e))}><span>v{v.version}</span><span>{catalogState[v.state]||v.state}</span><code>{v.revision.slice(0,14)}…</code><Icon name="chevron"/></button>)}</div></details>
 </article>)}{!visible.length&&<div className="catalog-empty"><Icon name="grid"/><strong>{items.length?'没有匹配的工具':'连接你的第一个工具'}</strong><span>{items.length?'调整搜索或筛选条件。':'添加 API 或导入个人数据，提交后由 OrgB 审核。'}</span></div>}</div>
 {review&&<aside className="tool-detail-drawer" aria-label="工具详情" tabIndex={-1} ref={detail}><div className="tool-detail-heading"><span>版本详情 · v{review.manifest.version}</span><button type="button" className="icon-button" aria-label="关闭工具详情" onClick={closeReview}>×</button></div><div className="review" aria-label="自定义工具版本审阅">
 <h3>{review.manifest.label} · v{review.manifest.version} · {review.state}</h3><p>{review.manifest.description}</p>
 <p>适配器：{review.manifest.adapter==='http.request'?'通用 HTTP 查询／识别；下面是实际请求配置，不是返回结果':review.manifest.adapter==='github.read'?'GitHub 实时读取；下面是授权资源目录，不是查询结果':'导入数据的版本快照'}</p>
 <label>版本摘要（审阅与启用绑定）</label><code>{review.manifest.revision}</code>
 <label>{review.manifest.adapter==='http.request'?'请求配置 SHA-256':review.manifest.adapter==='github.read'?'授权资源目录 SHA-256':'数据 SHA-256'}</label><code>{review.manifest.dataset_sha256}</code>
 <details><summary>查看参数与返回 Schema</summary><pre>{JSON.stringify({input:review.manifest.input_schema,output:review.manifest.output_schema},null,2)}</pre></details>
 <details><summary>{review.manifest.adapter==='http.request'?'查看本版本请求参数':'查看本版本实际资料'}</summary><pre>{JSON.stringify(review.records,null,2)}</pre></details>
 {review.manifest.http&&<div aria-label="API 版本绑定"><h3>R1 · 外部查询／识别请求</h3><code>{review.manifest.http.method} {review.manifest.http.url}</code><p>安全审批须核实此端点只用于查询或推理，不产生发送、删除、付款等敏感副作用。下面的资料是请求参数配置，不是 API 返回结果；浏览器不执行请求。</p></div>}
 {review.changes&&<details open><summary>与父版本的数据差异</summary><p>{review.changes.previous_rows} → {review.changes.current_rows} 条</p><pre>{JSON.stringify(review.changes,null,2)}</pre></details>}
 <details><summary>版本事件历史</summary><pre>{JSON.stringify(review.history||[],null,2)}</pre></details>
 <p>审核风险标签：{review.admission?.risk_level||'尚未链上审核'}{review.admission?.evidence&&` · 区块 #${review.admission.evidence.block_number}`}</p>
 {role==='security'?<><label>OrgB 审核风险等级（必选）<select aria-label="工具审核风险等级" value={riskLevel} onChange={e=>setRiskLevel(e.target.value)}><option value="">请选择</option><option value="LOW">LOW · 查询／推理，可使用会话预授权</option><option value="HIGH">HIGH · 每次调用需独立强审批</option></select></label><p>标签由安全审核方决定，提交者不能指定；标签与精确版本绑定并上链。HTTP 适配器仍不能用于敏感写操作。</p><div className="buttons"><button className="primary" disabled={!riskLevel||!['DRAFT','ENABLING','ACTIVE'].includes(review.state)} onClick={()=>action(()=>activate(true))}>核对本版本并启用</button><button disabled={!riskLevel||!['ACTIVE','ENABLING','DISABLING'].includes(review.state)} onClick={()=>action(()=>activate(false))}>停用本版本</button></div></>:<p>启用、风险标记与停用需退出后使用 OrgB 安全审批身份。</p>}
 {role==='requester'&&<><button disabled={items.some(t=>t.name===review.manifest.name&&t.version>review.manifest.version)} onClick={()=>{const source=review;openIntake();if(source.manifest.adapter==='http.request'){setConnection('http');H(source);return;}if(source.manifest.adapter==='github.read'){setConnection('github');setGithubEdit(source);return;}setConnection('dataset');fill(registrationFrom(source));V(source.manifest.revision);X(null);O(true);}}>以此版本修改资料</button>
 <fieldset aria-label="准备查询任务"><legend>选择本版本的任务查询范围</legend>{review.records.map(r=>{const k=r[review.manifest.key_field];return <label key={k}><input type="checkbox" aria-label={`准备查询 ${k}`} checked={taskKeys.includes(k)} onChange={e=>Q(e.target.checked?[...taskKeys,k]:taskKeys.filter(v=>v!==k))}/>{k}</label>;})}
 <button className="primary" disabled={review.state!=='ACTIVE'||items.some(t=>t.name===review.manifest.name&&t.state==='ACTIVE'&&t.version>review.manifest.version)||!taskKeys.length} onClick={()=>action(()=>onPrepare(items.find(t=>t.revision===review.manifest.revision),taskKeys))}>用本版本准备 Agent 任务</button><p>只填写只读任务及精确版本/记录授权，点击“创建任务”才运行模型。新任务入口使用最新已启用版本。</p></fieldset></>}
 </div></aside>}
 <details className="catalog-boundaries"><summary><Icon name="lock"/>接入与执行边界</summary><p>http.request 实际调用审核绑定的 HTTPS API，同任务同配置复用原记录，UNKNOWN 不自动重发；github.read 保留独立链上仓库准入；dataset.lookup 查询版本快照。外部结果均是不可信数据，不作为链上执行认证。不接受脚本或浏览器凭据。</p></details>
 </div></section>;
}
