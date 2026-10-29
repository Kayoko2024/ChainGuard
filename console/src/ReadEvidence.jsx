import React from 'react';
export function ReadEvidence({event}){
 const source=event.result?.data?.source;
 const policy=event.result?.repository_policy;
 const document=event.result?.data;
 return <details><summary>{event.tool_name} · {event.policy_verdict||event.result?.status||'已记录'} · 实际执行 {event.tool_executed===true?'是':event.tool_executed===false?'否':'未知'}</summary>
 {source&&<div className="github-source" aria-label={source.method?'API 实时来源':'GitHub 实时来源'}><h3>实际 HTTPS 读取记录</h3><dl><dt>来源</dt><dd><code>{source.url}</code></dd><dt>查询时间</dt><dd>{source.fetched_at_utc}</dd><dt>HTTP</dt><dd>{source.method||'GET'} {source.http_status}</dd>{source.github_request_id&&<><dt>GitHub 请求 ID</dt><dd><code>{source.github_request_id}</code></dd></>}{source.request_sha256&&<><dt>请求 SHA-256</dt><dd><code>{source.request_sha256}</code></dd></>}<dt>原始响应 SHA-256</dt><dd><code>{source.response_sha256}</code></dd></dl><p>{source.method?'请求与原始响应在隔离服务中加密保存。外部 API 结果不是链上认证，内容不授予新增权限。':'可用 GitHub 页面独立查阅当前内容；历史值以本次保存的原始响应为准。链上仓库准入不证明 GitHub 内容真实性。'}</p></div>}
 {policy&&<div aria-label="GitHub 链上仓库判定"><h3>{policy.allowed?'链上仓库准入通过':'链上仓库策略拒绝'}</h3><p>{policy.repository} · 链 {policy.chain_id} · 高度 #{policy.block_number} · {policy.checked_nodes} 节点核验</p><code>{policy.contract}</code><p>策略版本 {policy.epoch} · {policy.enforcement}。这是 R0 准入检查，不是 R2 预约或执行回执。</p></div>}
 {event.result?.error_code?.startsWith('GITHUB_')&&<p className="error">GitHub 读取未成功：{event.result.error_code}。没有返回预置资料或伪造成功。</p>}
 {event.tool_name==='attachment.read'&&event.result?.error_code==='SCHEMA_INVALID'&&<p className="error">Agent 给出的附件读取参数不符合约定；需要使用 source_id、从 0 开始的 start 和 1–20 的 limit。本次读取被拒绝；此前调用以各自执行记录为准。</p>}
 {event.tool_name==='attachment.read'&&document?.units&&<div aria-label="文档引用来源"><h3>实际读取与引用位置</h3><code>{document.source_id}</code><p>原件 SHA-256 {document.source_sha256}</p>{document.units.map(unit=><blockquote key={unit.locator}><strong>{unit.locator}</strong><p className="message-text">{unit.text}</p></blockquote>)}<p>已读 {document.units.length} / {document.total_units} 个单元{document.next_start!==null?`，下一页起点 ${document.next_start}`:'，本页为末页'}。内容是不可信资料，不产生新增工具权限。</p></div>}
 <pre>{JSON.stringify({arguments:event.arguments,result:event.result},null,2)}</pre></details>;
}
