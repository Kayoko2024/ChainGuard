# 阶段9只读审计接口

本接口为独立展示层，前缀`/audit-api/v1`；冻结`/v1`业务API、两个EIP-712结构及状态机不变。只绑定本机回环；可信本地操作员启动，不作为多租户生产服务。API无任何执行/签名/审批/恢复写入口；不提供用户输入RPC地址或通用RPC方法代理。

实际运行应用导出的OpenAPI保存在`spec/audit/openapi.json`，7条GET路径；它不加入或覆盖原冻结协议。

| GET路径 | 返回及解释 |
|---|---|
| `/health/live` | `read_only=true`，只证明进程存活 |
| `/health/ready` | 原协议检查通过、已载入公开目录；`ledger_checked=false`，不能当链健康 |
| `/audit-api/v1/network` | 四节点chainId/genesis/验证者/peer/共同块/合约代码与引用核验，成功ONLINE；失败HTTP503/UNAVAILABLE |
| `/audit-api/v1/actions?group=C&state=UNKNOWN` | 公开历史投影，支持组别/状态过滤；不是实时执行数据库 |
| `/audit-api/v1/actions/{entry_id}` | 单条公开证据；找不到404 |
| `/audit-api/v1/actions/{entry_id}/verify` | 当前只读链证据和签名核验结果；业务结论见下表 |
| `/audit-api/openapi.json` | 独立OpenAPI描述；不是冻结业务契约的替代品 |

`entry_id`只标识导出记录；`action_id`为原协议动作ID，无动作时为null，不能用记录ID伪造动作。`state`和`chain_state`是导出时历史状态，实时`current_chain_state`与`checked_at_utc/snapshot`独立返回。`observed_tool_executed`、`observed_mail_count`来自原工具卷独立核验；null保留未知，不凭模型文字或页面状态猜测副作用。

原`intent`/`receipt`保留原schema及十进制字符串，参数/结果/证据只展示加盐承诺。`requester_signature`/`approval_signatures`/`tool_signature`为链上可公开原签名；恢复身份、组织和角色从原预约区块PolicyRegistry读取，并单列当前active。`reservation_evidence`/`finalization_evidence`含原chain_id、registry、tx_hash、block_hash、block_number，实时查四节点receipt/区块成员/事件/calldata。确认数=共同高度-交易高度+1。没有预约不补造拒绝交易。

`provenance`保存源轨/源记录SHA256、导出时原卷验证PASS和信任说明；目录SHA256用于本地完整性检查，不是独立信任根。控制台不挂载原工具私有卷，实时核验不能从链上承诺恢复原始MIME；原副作用证明应使用`export-verification.json`和原工具卷验证器。

| 核验status | 含义及允许行为 |
|---|---|
| VERIFIED | 真实预约、同意图跨组织签名、nonce、真实finalize/reconcile、工具签名与当前链记录吻合；不是一次新执行授权 |
| HISTORICAL_ONLY | A/B中央历史证据；没有声称当前链上确认 |
| NO_RESERVATION | 该导出记录无预约；不能当链上执行成功，也不能仅据缺失记录证明全链没有其他动作 |
| PENDING_RECEIPT | 已验证预约，缺工具回执；仍可能有副作用，不重新派发 |
| UNAVAILABLE | 四节点、历史权限或RPC不可用，未形成结论；保留历史状态 |
| INVALID | 导出字段、签名、链证据或状态关系不吻合；禁止显示已验证 |

核验接口返回200和上述明确结论；网络总体端点失联返回503。POST/PUT/DELETE不支持（404/405），无CORS开放；TrustedHost及CSP、no-store、nosniff、no-referrer、frame-ancestors限制浏览器内容。输入中任何链RPC地址均无效，部署端固定四节点。审计RPC类只允许显式读取方法，但本地Docker操作员仍处于可信边界，不能据此宣称生产节点不可写。

依赖：阶段0字段/承诺与golden vector、阶段3冻结B/C策略、阶段5真实ABI/部署、阶段6工具签名/幂等、阶段8原始证据和原卷验证器。新测试适配器只将缺失的真实验证者查询转为CHAIN_UNAVAILABLE，交由既有有限轮询处理；不改变核心执行代码或提供伪造区块/receipt。
