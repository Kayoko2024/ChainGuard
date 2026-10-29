export function taskBody(text,tools,documents,mailboxes,recipients,custom=[],documentScope=null){
 return {task_text:text,allowed_tools:tools,allowed_document_ids:tools.some(t=>t.startsWith('doc.'))?documents:[],
  ...(documentScope&&(documentScope.attachment_ids.length||documentScope.allow_create)?{document_scope:documentScope}:{}),
  ...(tools.some(t=>t.startsWith('custom.'))?{custom_tools:custom.filter(t=>tools.includes(t.name))}:{}),
  read_mailboxes:tools.some(t=>['mail.list','mail.read'].includes(t))?mailboxes:[],allowed_recipients:tools.includes('mail.send')?recipients:[]};
}
export function selectionIssues(tools,documents,mailboxes,recipients,custom=[],documentScope=null,catalog=[]){
 const issues=[];
 if(!tools.length&&!Boolean(documentScope&&(documentScope.attachment_ids.length>0||documentScope.allow_create)))issues.push({code:'TOOLS_MISSING',message:'请选择至少一个工具，或添加文件。'});
 if(tools.some(t=>t.startsWith('doc.'))&&!documents.length)issues.push({code:'DOCUMENT_SCOPE_MISSING',message:'已选择文档工具，请选择允许读取的文档。'});
 if(tools.some(t=>['mail.list','mail.read'].includes(t))&&!mailboxes.length)issues.push({code:'MAILBOX_SCOPE_MISSING',message:'已选择读取邮件工具，请选择允许读取的本地邮箱；发送收件人不等于可读邮箱。'});
 if(tools.includes('mail.send')&&!recipients.length)issues.push({code:'RECIPIENT_SCOPE_MISSING',message:'已选择发送邮件工具，请选择允许发送的本地收件人。'});
 for(const name of tools.filter(t=>t.startsWith('custom.'))){
  const tool=catalog.find(t=>t.name===name),grant=custom.find(t=>t.name===name&&t.revision&&(!tool||t.revision===tool.revision));
  const label=tool?.label?`${tool.label}（${name}）`:name;
  if(!grant||!Array.isArray(grant.allowed_keys)||!grant.allowed_keys.length)issues.push({code:'CUSTOM_SCOPE_MISSING',tool:name,message:`${label} 尚未选择允许查询的记录或资源，请在任务授权中勾选具体范围。`});
 }
 return issues;
}
export function selectionValid(...args){
 return selectionIssues(...args).length===0;
}
export function toolAuthorizationLabel(tool){
 if(!tool.enabled)return '尚未开放';
 if(tool.custom){
  if(tool.risk_level==='HIGH')return 'HIGH · 每次调用须双组织审批';
  if(tool.risk_level==='LOW')return 'LOW · 有效会话内免逐次审批';
  return '尚无链上风险标签 · 需 OrgB 复审';
 }
 return tool.requires_approval?'双组织审批 + 链上预约':'任务范围内读取';
}
