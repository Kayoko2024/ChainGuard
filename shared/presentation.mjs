// Presentation only. Original records and gateway guards remain authoritative.
export const icons = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  shield: 'M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6',
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  layers: 'M3 7l9-5 9 5-9 5z M3 12l9 5 9-5 M3 17l9 5 9-5',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  external: 'M14 3h7v7 M21 3L10 14 M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5',
  plus: 'M12 5v14 M5 12h14',
  search: 'M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M6 6a8 8 0 0 1 13 2 M18 18A8 8 0 0 1 5 16',
  lock: 'M6 10h12v11H6z M8 10V6a4 4 0 0 1 8 0v4',
  mail: 'M3 5h18v14H3z M3 6l9 7 9-7',
  check: 'M5 12l4 4L19 6',
  clock: 'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  user: 'M20 21v-2a7 7 0 0 0-14 0v2 M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
  logout: 'M9 4H4v16h5 M9 12h12 M16 7l5 5-5 5',
  file: 'M14 2H4v20h16V8z M14 2v6h6 M8 13h8 M8 17h6',
  chevron: 'M9 5l7 7-7 7',
  info: 'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
};
export const stateLabels = {
  QUEUED:'任务已排队', AGENT_RUNNING:'Agent 运行中', AWAITING_APPROVAL:'等待组织审批',
  APPROVAL_EXPIRED:'审批已过期', PROPOSED:'已生成动作', RESERVING:'预约确认中', RESERVED:'已链上预约',
  EXECUTING:'工具执行中', EXECUTION_RECORDED:'回执待确认', FINALIZED_OK:'执行已完成',
  FINALIZED_REJECTED:'执行已拒绝', FINALIZED_ERROR:'执行异常', DENIED:'策略已拒绝',
  UNKNOWN:'执行结果未知', MODEL_ERROR:'模型服务异常', INTERRUPTED:'任务已中断', NO_ACTION:'未生成动作',
  CENTRAL_OK:'中央执行完成', CENTRAL_REJECTED:'中央执行拒绝', EXPIRED:'已过期',
  AWAITING_TOOL_APPROVAL:'等待工具逐次审批',PENDING_BATCH:'日志待批量存证',PREPARED:'批次交易待广播',ANCHORED:'批次根已上链',BATCH_VERIFIED:'批量包含性已核验',
};
export const stateLabel = value => ({DOCUMENT_COMPLETED:'文档副本已生成',DOCUMENT_CREATED:'允许生成副本',LOCAL_DOCUMENT_OBSERVATION:'本地文档记录',READ_COMPLETED:'读取任务完成',READ_ALLOWED:'允许读取'}[value]||stateLabels[value]) || value || '等待观测';
export const stateTone = value => ['FINALIZED_OK','CENTRAL_OK','VERIFIED','ONLINE'].includes(value) ? 'good' :
  ['DENIED','FINALIZED_REJECTED','FINALIZED_ERROR','INVALID','MODEL_ERROR','CENTRAL_REJECTED'].includes(value) ? 'bad' :
  ['UNKNOWN','UNAVAILABLE','APPROVAL_EXPIRED','EXPIRED','PENDING_RECEIPT','PENDING_ANCHOR'].includes(value) ? 'warning' : 'neutral';
export const compactId = value => value ? `${value.slice(0,10)}…${value.slice(-6)}` : '—';
export function executionStages(record) {
  return [
    {label:'动作意图',done:Boolean(record?.action_id)},
    {label:'跨组织审批',done:(record?.approval_signatures?.length||0)>=2},
    {label:'链上预约',done:Boolean(record?.reservation_evidence)},
    {label:'工具回执',done:Boolean(record?.tool_signature&&record?.receipt)},
    {label:'审计确认',done:Boolean(record?.finalization_evidence)},
  ];
}
