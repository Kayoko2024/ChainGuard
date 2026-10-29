import React,{useEffect,useState} from 'react';
export function GitHubPolicyPanel({api,action,job,catalog,role}){
 const [proof,P]=useState(null),[error,E]=useState(''),[result,R]=useState(null);
 const tool=job?.custom_tools?.find(g=>catalog.tools.some(t=>t.revision===g.revision&&t.adapter==='github.read'));
 async function check(){E('');try{P(await api('/ops/v1/github-policy?resource=microsoft%2Fvscode'));}catch(e){P(null);E(e.message);}}
 useEffect(()=>{check();R(null);},[job?.id]);
 const history=(job?.events||[]).filter(e=>e.kind==='MANUAL_GITHUB_SCOPE_PROBE').map(e=>e.result);
 async function probe(query){R(await api(`/ops/v1/tasks/${job.id}/github-negative-control`,'POST',{tool_name:tool.name,query}));}
 return <section className="panel" aria-label="GitHub 链上策略验收"><div className="panel-head"><h2>GitHub 链上仓库策略</h2><button onClick={()=>action(check)}>重新核验链上策略</button></div><div className="panel-body">
 <p>双组织治理启用 microsoft/vscode，其余仓库默认拒绝。任务精确键授权与链上仓库准入必须同时通过；不需要 GitHub Token。</p>
 {error&&<p className="error">链上核验不可用：{error}，读取不会降级放行。</p>}
 {proof&&<><p>microsoft/vscode：{proof.allowed?'链上允许':'链上拒绝'} · 高度 #{proof.block_number} · 策略版本 {proof.epoch} · {proof.checked_nodes} 节点</p><label>独立策略合约</label><code>{proof.contract}</code><label>双组织策略交易</label><code>{proof.governance_tx}</code></>}
 {tool&&role==='requester'?<><p>当前任务 {job.id.slice(0,18)}… · {tool.name}。请先用 VS Code 模板创建任务并授权三条测试键。下列为人工协议探测，单独记录，不计为模型攻击成功率。</p><div className="buttons"><button disabled={!job.grant} onClick={()=>action(()=>probe('facebook/react#1'))}>测试其他仓库被链上拒绝</button><button disabled={!job.grant} onClick={()=>action(()=>probe('microsoft/vscode#2'))}>测试未授权 Issue 被工具拒绝</button></div></>:<p>选择一个 GitHub 查询任务后，可验证链上拒绝及工具范围拒绝。</p>}
 {(result||history.at(-1))&&<pre aria-label="GitHub 拒绝验收结果">{JSON.stringify(result||history.at(-1),null,2)}</pre>}
 <small>GITHUB_REPOSITORY_DENIED + chain_enforced=true + no_new_github_fetch=true 才证明本次探测在 HTTPS 前被链上策略阻止。UNAUTHORIZED_SCOPE 说明工具范围拒绝。R0 查询无逐次预约交易，链上不保存 Issue 正文。</small>
 </div></section>;
}
