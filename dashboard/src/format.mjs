export const short = value => value ? `${value.slice(0,10)}…${value.slice(-6)}` : '—';
export const tone = status => ['VERIFIED','FINALIZED_OK','CENTRAL_OK','ONLINE'].includes(status) ? 'good' : ['INVALID','DENIED','CENTRAL_REJECTED','NO_ACTION'].includes(status) ? 'bad' : 'pending';
export const verificationLabels = {VERIFIED:'实时证据一致',HISTORICAL_ONLY:'中央历史快照',NO_RESERVATION:'未形成链上预约',PENDING_RECEIPT:'待回执 · 副作用未知',PENDING_ANCHOR:'工具回执待链上确认',UNAVAILABLE:'链核验不可用',INVALID:'证据不一致'};
export const effectLabel = value => value === true ? '已观察到本地邮件' : value === false ? '未观察到本地邮件' : '副作用未知';
verificationLabels.READ_ONLY_OBSERVATION='只读任务 · 不适用链上预约';
verificationLabels.LOCAL_DOCUMENT_OBSERVATION='本地文档记录 · 非链上认证';
verificationLabels.EXTERNAL_TOOL_OBSERVATION='外部 API 记录 · 非链上认证';
verificationLabels.PENDING_BATCH='日志待批量上链';
verificationLabels.BATCH_VERIFIED='批量存证 · Merkle 验证通过';
