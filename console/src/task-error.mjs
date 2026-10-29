// Interpret stored model evidence for display; never change persisted states.
export function serviceError(code){
 if(code==='AUTH_EXPIRED')return '会话 LOW 授权已过期，请在当前窗口重新授权；旧消息和执行证据仍保留。';
 if(code==='AUTH_EXHAUSTED')return '会话 LOW 授权额度已用完，请明确续签后继续。';
 if(code==='AUTH_RENEWAL_PENDING')return '会话授权尚在双端安装中，请恢复原续签请求，不要重复提交任务。';
 if(code==='CONVERSATION_BUSY')return '当前会话有正在运行或挂起的任务，请查看原审批或执行记录。';
 if(code==='BACKEND_UNAVAILABLE')return '执行网关暂时失联（BACKEND_UNAVAILABLE）。这不等于链停止出块；原动作结果尚未确认，请等待恢复后查询原记录，不要重复发送。';
 if(code==='CHAIN_UNAVAILABLE')return '联盟链核验暂不可用（CHAIN_UNAVAILABLE）。当前无法确认链上授权或结果，请等待恢复后核验原记录，不要重复发送。';
 if(code==='READ_CAPABILITY_WINDOW_INVALID')return '读取授权期限超过工具允许的24小时上限（READ_CAPABILITY_WINDOW_INVALID）。本轮授权未安装，请检查服务版本与期限配置。';
 if(code==='RESERVATION_EXPIRED')return '授权时间校验未通过（RESERVATION_EXPIRED）。请检查任务、读取凭证或动作的截止时间；旧版本也曾用此代码表示期限上限不匹配。已有动作不会自动重发。';
 return code||'';
}
export function outputTruncation(job){
 if(!job)return null;
 const exchanges=(job.events||[]).filter(e=>e.kind==='MODEL_EXCHANGE');
 const exchange=exchanges.at(-1)?.exchange,last=exchange?.response?.choices?.[0];
 if(job.error!=='MODEL_OUTPUT_TRUNCATED'&&!(job.error==='SCHEMA_INVALID'&&last?.finish_reason==='length'))return null;
 const message=last?.message,calls=message?.tool_calls;
 const tool=Boolean(Array.isArray(calls)&&calls.length||message?.function_call);
 const reply=last?.finish_reason==='length'&&message?.role==='assistant'&&typeof message.content==='string'&&(calls==null||Array.isArray(calls)&&!calls.length);
 const limit=exchange?.request?.max_tokens??job.model_config?.parameters?.max_tokens;
 return {kind:last?.finish_reason==='length'&&tool?'tool_arguments':reply?'reply':'unknown',max_tokens:Number.isInteger(limit)&&limit>0?limit:null};
}
export function taskError(job){
 if(!job?.error)return '';
 const truncated=outputTruncation(job);
 if(truncated){
  const limit=truncated.max_tokens?`（本次上限 ${truncated.max_tokens} tokens）`:'';
  if(truncated.kind==='reply')return `文字回复达到长度上限${limit}，未完整生成；此次截断响应不含工具调用。此前工具结果仍保留，可在原会话要求简短回复或继续说明，无需新建会话。系统不会自动重放工具。`;
  if(truncated.kind==='tool_arguments')return `工具调用参数所在的响应达到长度上限${limit}，无法保证完整性。系统已阻止该响应中的全部工具调用；此前已完成的调用仍保留，不会自动重放。请先核对已有动作与回执，再在原会话明确提出更精简的请求。`;
  return `模型输出被截断${limit}，现有记录不足以区分文字回复与工具参数。请核对原模型记录和已有执行结果；系统不会自动重放工具。`;
 }
 return serviceError(job.error);
}
