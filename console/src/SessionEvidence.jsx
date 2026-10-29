import React from 'react';

export function SessionEvidence({job,role,api,action,refresh,conversation}){
 if(!job)return null;
 const calls=job.custom_calls||[],observations=[...(job.batch_observations||[]),...(conversation?.low_status?.observations||[])],grant=job.session_envelope?.message||conversation?.low_grant?.message;
 if(!calls.length&&!grant&&!observations.length)return null;
 return <section className="panel session-evidence" aria-label="会话授权与批量审计"><div className="panel-head"><h2>会话授权与批量审计</h2></div><div className="panel-body">
 {grant&&<p>OrgA 已签名预授权 · 最多 {grant.maxCalls} 次 · 有效至 {new Date(grant.expiresAt*1000).toLocaleString()}。仅覆盖签名中的 LOW 工具、版本和资源键。</p>}
 {conversation?.low_status?.authorization_epochs?.map(epoch=><p key={epoch.digest}>授权周期 <code>{epoch.digest}</code>LOW 序号 {epoch.start_sequence}–{epoch.end_sequence??'进行中'}{epoch.end_sequence!==null&&epoch.end_sequence<epoch.start_sequence?'（本周期无调用）':''}</p>)}
 {calls.map(c=><article key={c.call_id} className="review"><strong>{c.request.tool_name} · {c.state}</strong><code>{c.call_id}</code>
 {c.state==='AWAITING_TOOL_APPROVAL'&&<><p>当前调用需逐次审批。两组织须核对以下精确参数及摘要；批准后由请求者确认执行。</p><pre>{JSON.stringify(c.request.arguments,null,2)}</pre><code>{c.digest}</code><p>审批截止 {new Date(c.approval.expiresAt*1000).toLocaleString()} · 已记录 {Object.keys(c.signatures).length} 份签名</p>
 {['biz','security'].includes(role)?<button onClick={()=>action(async()=>{await api(`/ops/v1/tasks/${job.id}/tool-calls/${c.call_id}/approve`,'POST',{digest:c.digest});await refresh();})}>审阅并以本组织批准本次工具调用</button>:<button onClick={()=>action(async()=>{await api(`/ops/v1/tasks/${job.id}/tool-calls/${c.call_id}/execute`,'POST',{});await refresh();})}>确认执行本次已审批调用</button>}</>}
 {c.state==='STARTED'&&<p>执行结果未知，仅保留原调用记录。重试不会重新派发。</p>}
 {c.result&&<details><summary>原调用结果</summary><pre>{JSON.stringify(c.result,null,2)}</pre></details>}</article>)}
 {observations.map(o=><article key={o.log.call_id}><strong>{o.status==='ANCHORED'?'批量根已上链 · 待独立核验':'等待批量存证'}</strong><code>{o.log.call_id}</code>{o.log.session_id&&<p>LOW · 会话 {o.log.session_id} · 序号 {o.log.sequence}</p>}{o.batch?.evidence&&<p>区块 #{o.batch.evidence.block_number}<br/>交易 {o.tx_hash}<br/>根 {o.batch.root}</p>}<a href="http://127.0.0.1:8091/" target="_blank" rel="noreferrer">在只读审计台核验包含性证明</a></article>)}
 {!conversation&&observations.some(o=>o.status!=='ANCHORED')&&['requester','security'].includes(role)&&<button onClick={()=>action(async()=>{await api('/ops/v1/audit-batches/flush','POST',{});await refresh();})}>立即提交待存证批次</button>}
 <small>自动每 5 分钟或累计 50 条打包。上链前显示待存证；根哈希只证明日志被包含，不等同于外部数据真实性或 R2 执行回执。</small>
 </div></section>;
}
