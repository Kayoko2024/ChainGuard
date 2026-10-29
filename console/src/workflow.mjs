// Presentation only. The original gateway independently authorizes reserve/execution.
export function workflow(job,role,now=Date.now()){
 const record=job?.record;
 if(!record)return {label:'等待 Agent 提议动作',hint:'生成动作后，由两个组织审阅，再由请求者发起链上预约。',executeLabel:'发起链上预约并执行',blocked:true};
 const waiting=record.state==='AWAITING_APPROVAL'&&!record.reservation_evidence;
 const expired=waiting&&Number(record.intent.expires_at)*1000<=now;
 const approvals=record.approval_signatures.length;
 if(expired)return {label:'动作已过期，无法预约',hint:'原意图的审批/执行期限已过。请新建任务并重新审批；不会延长或复用旧签名。',executeLabel:'动作已过期，不能预约',blocked:true};
 if(waiting&&approvals>=2)return {label:'审批已齐，等待请求者发起链上预约',hint:role==='requester'?'请先审阅原意图与邮件参数，再点击“发起链上预约并执行”。审批本身不会自动发送邮件。':'请切换到请求者身份，选择此任务并审阅，然后点击“发起链上预约并执行”。',executeLabel:'发起链上预约并执行',blocked:false};
 if(waiting)return {label:`等待组织审批（${approvals}/2）`,hint:'业务审批与安全审批须来自两个不同组织。审批齐备后，请求者仍需确认发起链上预约。',executeLabel:'发起链上预约并执行',blocked:false};
 if(record.state==='UNKNOWN')return {label:'执行结果未知，禁止再次发送',hint:'可能已产生邮件。仅允许查询原记录或原回执，不能重新发起发送。',executeLabel:'查询原执行状态（不会重发）',blocked:false};
 if(record.state.startsWith('FINALIZED_'))return {label:'已有链上终态',hint:'查看原预约交易、工具签名和沙箱邮件。再次确认仅验证幂等，不产生新邮件。',executeLabel:'查询原记录 / 验证重复提交',blocked:false};
 return {label:'链上预约或执行处理中',hint:'等待原交易和工具签名回执确认；不要创建替代动作重复发送。',executeLabel:'查询原执行状态（不会重发）',blocked:false};
}
