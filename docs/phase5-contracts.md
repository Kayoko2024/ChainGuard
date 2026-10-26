# 阶段5合约接口、字段与依赖

状态：IMPLEMENTED / 本地技术验收通过，等待用户验收。输入与范围见[实施前记录](phase5-design.md)，实际地址和证据见[验收记录](phase5-acceptance.md)。原 ProtocolTypes、三个接口、21份协议文件和8份共用策略输入未改写；以下描述本阶段新增实现。

## 合约职责与信任边界

| 合约 | 实现入口 | 职责 |
|---|---|---|
| PolicyRegistry | `contracts/PolicyRegistry.sol` | OpenZeppelin AccessControl/EIP712/ECDSA；当前身份/组织/全局撤销、角色、scope、requester-agent、工具签名人绑定、策略/epoch；双组织治理和紧急暂停 |
| ExecutionRegistry | `contracts/ExecutionRegistry.sol` | OpenZeppelin EIP712/ECDSA；准确意图签名和当前权限、R2/R3独立角色席位、时效；原子永久消费actionId及(requester,nonce)，保存全部恢复地址 |
| AuditRegistry | `contracts/AuditRegistry.sol` | 预约和参数绑定、当前工具签名资格、签名结果确认、相同回执幂等、冲突拒绝、UNKNOWN与追加对账；仅它可调用recordAuditOutcome |

链上预约只完成登记身份和签名约束。完整 TaskGrant、任务到期/配额、具体收件人/doc_id、删除显式授权、参数JCS/盐重算及执行前当前审批状态重验，必须由后续可信网关/工具实现。合约无法读取这些链下数据；本阶段没有给execute_reserved增加放行分支。

不升级、无delegatecall、无合约管理员直接改审计结果。Execution构造时固定预期Audit CREATE地址，Audit构造核对Execution.auditRegistry和policyRegistry；无后续单方设置入口。部署操作员必须连续使用同一部署EOA的nonce，不插入其他交易；脚本逐笔等待并验证预测地址。预测地址若部署失败，保留失败证据，以新合约套件重试，不重置原链。

## ActionIntent 每个字段的检查位置

类型、顺序、JSON映射以[原协议](protocol.md)和spec/eip712.json为准；以下14个字段全部签入摘要。

| 字段 | 本阶段合约检查 / 保存 | 后续依赖 |
|---|---|---|
| schemaVersion | 必须1 | 网关/工具按同版本解码 |
| actionId | 非零；Registry内永久唯一 | 工具SQLite永久幂等键、索引、对账 |
| taskId | 非零，原样存储 | 可信任务服务核对不可变TaskGrant版本/撤销/期限 |
| requester | 非零；恢复地址精确相同；当前REQUESTER、scope | 请求者签名器与工具重验 |
| agent | 非零；当前AGENT及requester-agent绑定 | 任务授权绑定；Agent无真实敏感凭据 |
| toolId | 与当前策略精确相同 | 工具白名单与签名人绑定 |
| resourceScope | 与策略相同；请求者及每名批准者都有scope | 具体资源清单与任务ABAC |
| paramsCommit | 非零；不可换签；审计回执必须相等 | 工具对完整JCS参数/独立盐重算 |
| policyId | 登记且enabled的冻结MVP组合 | 策略缓存/独立查链 |
| policyEpoch | 必须当前正版本；每次策略写入递增 | 撤销重验；不可用旧版本预约/执行 |
| nonce | uint64；(requester,nonce)永久原子消费，回滚不消费 | 请求者协调分配；跨任务/epoch不重置 |
| issuedAt | 不晚于block.timestamp | 工具实际开始时间/校准UTC |
| expiresAt | block.timestamp严格小于到期；正寿命且不超过策略120/60秒上限 | 工具开始前检查任务期限；不引入宽限 |
| risk | 只允许2或3，与策略一致 | R0/R1继续独立读取路径；R3检查显式删除TaskGrant |

paramsCommit对完整参数的真实性无法由只看到承诺的合约自行判断。篡改承诺会使已有签名失效；“参数明文与承诺是否一致”属于未来工具端强制检查，不能以本阶段签名用例宣称已实现。

R2业务和安全席位必须为不同地址、不同组织；R3再加不同地址的人审席位，人审可同业务组织。使用完整角色分配搜索，避免多角色账户贪心误计数。每个提供的签名都要有效且当前有对应审批角色/scope；重复、附加伪造签名均拒绝。requester、agent、任何当前TOOL_SIGNER不得占审批席位。请求者单独验签，不能计入批准数量。审批上限16份是明确的MVP gas边界，不改变最小门槛。

## ExecutionReceipt 每个字段

以下7个字段全部签入AuditRegistry的独立EIP-712域。

| 字段 | 本阶段检查 | 后续依赖 |
|---|---|---|
| schemaVersion | 必须1 | 工具回执构造 |
| actionId | 必须有真实预约；必须处于允许转换的链状态 | 工具执行记录与队列去重 |
| paramsCommit | 精确等于预约意图 | 工具真实参数重算 |
| resultCommit | 非零；签名绑定；终态不得换结果 | 真实结果加盐承诺/链下加密持久化 |
| evidenceIndexCommit | 非零；签名绑定；reconcile事件proofCommit采用它 | 证据清单加密存储、独立审计取回 |
| executedAt | 不早于issuedAt；不超过block.timestamp+明确部署容差 | OK/ERROR完成时间、REJECTED判定、工具开始日志；实际部署容差0秒 |
| outcome | finalize/reconcile只允许0 OK / 1 ERROR / 2 REJECTED | UNKNOWN=3只是观测，不能据此最终化或重派发 |

恢复签名后必须当前TOOL_SIGNER且绑定预约toolId；只持有其它工具角色无效。所有签名走OpenZeppelin 65字节/low-s/v校验；不支持1271或2098。相同digest且相同工具签名地址在已确认后幂等返回、无重复事件；当前撤销的签名人仍拒绝提交，可用receiptHash/receiptSigner只读查询原锚定结果。冲突交易回滚，调用方须在链下保留冲突证据，EVM回滚不能保留事件。

已执行证据在意图过期/策略撤销/暂停后仍可提交，但工具签名人必须当前有效。暂停阻止新预约，不阻止旧证据、UNKNOWN和对账。合约不能用完成时间证明工具在许可有效期内开始；后续工具必须记录实际开始/核验区块，不能拿晚到锚定重新获得执行权。

## 链状态和事件

| 从 → 到 | 唯一入口/guard | 事件 |
|---|---|---|
| NONE → RESERVED | reserve；当前策略/角色/跨组织签名/时效/唯一ID+nonce | ActionReserved |
| RESERVED → UNKNOWN | markUnknown；当前RECONCILER、非零原因承诺 | ActionUnknown |
| RESERVED → FINALIZED_OK/ERROR/REJECTED | finalize；绑定工具有效签名和相应明确outcome | ActionFinalized |
| UNKNOWN → FINALIZED_OK/ERROR/REJECTED | reconcile；相同预约的有效工具结果，不派发工具 | ActionReconciled + ActionFinalized |
| 已确认终态 → 原终态 | 同digest/同签名人回执只返回，无转换 | 无新增事件 |

NONE不能finalize，UNKNOWN不能走finalize，RESERVED不能走reconcile；终态不能变UNKNOWN或覆盖。UNKNOWN的原因承诺永久保留。nonce/actionId在UNKNOWN、到期、撤销和所有终态都不释放。链没有EXECUTING/EXPIRED/DENIED状态；后续业务状态与链最后确认状态必须分列，不修改冻结状态机。

## 新治理写协议与ABI

机器规范：[spec/phase5/governance.json](../spec/phase5/governance.json)。EIP-712域为ChainGuard PolicyRegistry/version=1/实际chainId/实际PolicyRegistry。GovernanceChange字段依次为changesHash(bytes32)、nonce(uint64)、governanceEpoch(uint64)、issuedAt(uint64)、expiresAt(uint64)。changesHash=keccak256(abi.encode(Change[]))，数组元素为(uint8 kind,bytes data)，**包括顶层动态offset**，次序有意义。

| 入口 | 内容与约束 |
|---|---|
| governanceDigest(changes,nonce,epoch,issuedAt,expiresAt) | 供离线签名器核对完整变更摘要 |
| executeGovernance(changes,nonce,epoch,issuedAt,expiresAt,signatures) | 2–16个当前有效管理员签名、不同地址、至少两组织；1–128个变更；排他TTL≤86400秒；nonce一次性；epoch必须当前 |
| emergencyPause() | 仅当前单个GOVERNANCE_ADMIN可收紧暂停；无单方unpause |
| hasScope(account,scope) | 新增当前批准者scope读取；原IPolicyRegistry全部view保持兼容 |
| intentDigest / receiptDigest | 对实际部署域计算被冻结结构摘要，便于Python/工具交叉核验 |

变更kind 0身份/组织/全局撤销、1角色、2scope、3请求者Agent绑定、4工具签名绑定、5策略、6解除暂停；精确payload ABI见机器规范。所有签名先按批处理前的当前身份核验，再原子执行；成功消耗nonce并提升治理epoch，旧提案作废；任何失败整个batch回滚。策略的policyEpoch单独递增，禁用/重新启用也不复用旧版本。只允许冻结R2 mail.send/ORG_A_INTERNAL_MAIL和R3 doc.delete/ORG_A_DISPOSABLE_DOCS组合，不能治理降级风险或超过原寿命上限。

构造时引入两个不同组织根管理员；不授予DEFAULT_ADMIN_ROLE。grantRole/revokeRole/renounceRole全部拒绝直接调用；治理批次不得移除最后两个有效组织的治理能力。角色管理事件使用OZ标准事件；完整变更参数可从真实治理交易输入还原，GovernanceApplied记录摘要/nonce/epoch和恢复地址。

双组织治理与角色变更由测试账户验证，当前私钥在同机操作员控制下；这不是两个机构独立保管密钥的证明。当前没有治理UI、HSM、跨机器密钥交付或延时治理。

## 后续模块必须接入

1. 可信C网关：读取实际地址/ABI/代码摘要/chainId，生成新C域签名；不能复用中央chainId=0或golden31337签名。持久化预约交易并处理未知广播结果，不盲目重发。
2. 工具：独立RPC重取成功receipt、对应区块/事件和getReservation，核对完整意图/全部批准者当前角色组织/scope、策略epoch/撤销、TaskGrant/额度、JCS盐承诺及开始时效；独立数据库唯一claim后才能产生本地沙箱副作用。链不可用拒绝新执行。
3. 工具签名/证据：仅可信工具持有真实工具签名私钥，签实际ExecutionReceipt并持久排队；本阶段只提供角色绑定及合约验证，测试夹具不替代此模块。
4. 对账服务：当前RECONCILER只提交加盐原因承诺；UNKNOWN检索原工具日志并提交原始签名结果，经reconcile追加事件；不派发第二次工具执行。
5. API/审计器：保留被冻结/v1字段、错误映射、原文受控取回和PARTIAL/VALID证明边界；目前仍TODO。Agent/React/实验统计不在阶段5。
