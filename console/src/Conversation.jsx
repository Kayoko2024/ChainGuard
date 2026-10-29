import React,{useEffect,useRef} from 'react';
import {Icon,StateBadge,PaperLayers,CraftIllustration} from '../../shared/ui.jsx';
import {ReadEvidence} from './ReadEvidence.jsx';
import {DocumentFiles} from './DocumentAttachments.jsx';
import {taskError,serviceError} from './task-error.mjs';
import {AgentReply} from './AgentReply.mjs';
import './agent-reply.css';

// Render persisted model/tool events only. Status cards are explicitly system observations.
export function Conversation({job,step,onDetails,onPreset}){
 const bottom=useRef(null);
 const attempts=(job?.events||[]).filter(e=>e.kind==='AGENT_ATTEMPT');
 useEffect(()=>{bottom.current?.scrollIntoView({block:'nearest'});},[job?.id,attempts.length,job?.agent_output,job?.display_state]);
 if(!job)return <div className="conversation-welcome">
  <div className="welcome-hero"><div className="welcome-copy">
   <span className="welcome-label"><Icon name="activity"/>一点想法，开始一段协作</span>
   <h1>把想法交给 Agent，<br/><em>把执行握在手里。</em></h1>
   <p>读资料、整理邮件，或连接你的工具。<br/>你来定义边界，Agent 帮你把事情做好。</p>
  </div><CraftIllustration/></div>
  <div className="suggestions-caption"><span>从这里开始</span><span>也可以在下方直接输入任务 <Icon name="arrow"/></span></div>
  <div className="conversation-suggestions" aria-label="任务建议">
   {[['read','file','整理一份文档摘要','搜索会议结论，提取负责人和下一步'],['inbox','mail','读一读本地邮件','查看授权邮箱，概括最新邮件'],['mail','shield','把会议摘要发给同事','先读取，再审阅并批准发送']].map(([id,icon,title,description])=>
    <button className={'paper-stack suggestion-'+id} key={id} onClick={()=>onPreset(id)}><PaperLayers/><span className="suggestion-number">0{['read','inbox','mail'].indexOf(id)+1}</span><Icon name={icon}/><strong>{title}</strong><span>{description}</span><Icon name="arrow"/></button>)}
  </div>
  <span className="welcome-sandbox"><Icon name="lock"/>按授权调用工具 · 敏感动作仍需独立审批</span>
 </div>;
 return <div className="conversation-thread" aria-label="任务对话">
  <article className="message user-message"><div className="message-caption">你<span>任务请求</span></div><div className="message-text">{job.task_text}</div></article>
  <article className="message agent-message"><div className="message-caption"><span className="agent-mark"><Icon name="shield"/></span>ChainGuard Agent<span>DeepSeek · deepseek-flash</span></div>
   <div className="read-observations">{attempts.map((event,i)=><div className="tool-message" key={`${job.id}-${i}`}>
    <div className="tool-message-title"><Icon name="activity"/><code>{event.tool_name}</code><span>Agent 调用尝试 · {i+1}</span></div>
    <div className="attempt-outcome"><span>尝试时策略 <b>{event.policy_verdict||'未记录'}</b></span><span>尝试时工具执行 <b>{event.tool_executed===true?'是':event.tool_executed===false?'否':'未知'}</b></span></div>
    <ReadEvidence event={event}/>
    {event.tool_name==='mail.send'&&<p className="proposal-caption">这里记录提议时的结果；审批后的执行以系统记录及工具回执为准。</p>}
   </div>)}</div>
   {job.agent_output&&<div className="agent-output"><h3 className="agent-output-label">Agent 任务结果</h3><AgentReply text={job.agent_output}/></div>}
   {['QUEUED','AGENT_RUNNING'].includes(job.display_state)&&<div className="agent-working" role="status"><Icon name="refresh" className="spin"/>{job.display_state==='QUEUED'?'任务已入队，等待真实模型响应':'Agent 正在运行，等待模型或工具返回…'}</div>}
   {!job.agent_output&&!attempts.length&&!['QUEUED','AGENT_RUNNING'].includes(job.display_state)&&<p>此任务没有可展示的模型回复或工具调用。</p>}
  </article>
  <DocumentFiles job={job}/>
  <section className={'conversation-status '+(['AWAITING_APPROVAL','AWAITING_TOOL_APPROVAL'].includes(job.scheduler_state)?'approval-pending':'')} aria-label="系统执行状态" aria-live="polite"><div className="conversation-status-head"><span><Icon name="shield"/>系统执行记录</span><StateBadge value={job.display_state}/></div>
   {job.record?<><strong>{step.label}</strong><p>{step.hint}</p><div className="conversation-evidence"><span>组织审批 <b>{job.record.approval_signatures.length}/2</b></span><span>预约交易 <b>{job.record.reservation_evidence?'已记录':'尚无'}</b></span><span>沙箱邮件 <b>{job.tool_observation?.mail_count??'未知'}</b></span></div></>:<p>{job.display_state==='DOCUMENT_COMPLETED'?'文档副本已真实生成，可在上方下载；这不表示邮件已发送或获得链上执行认证。':job.display_state==='READ_COMPLETED'?'已记录真实读取结果；只读任务不产生邮件预约或执行回执。':taskError(job)||'授权与工具判定以原网关记录为准。'}</p>}
   <button onClick={onDetails}><Icon name="layers"/>{job.record?'查看审批与执行证据':'查看任务授权与记录'}<Icon name="chevron"/></button>
  </section>
  {job.sync_error&&<p className="error">{serviceError(job.sync_error)}</p>}
  <div ref={bottom}/>
 </div>;
}
