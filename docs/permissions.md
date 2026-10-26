# R0–R3 权限与批准表

状态：SPECIFIED；规则引擎、合约与工具强制检查均 TODO。risk 由登记的工具+资源标签计算，Agent 不可指定或降级风险。

机器可读门槛和寿命为 `spec/risk-rules.json`；此表解释其业务含义，后续变更需同步更新并重新验收。

| 风险 / 工具 | 允许范围与任务授权 | 默认判定 | 批准与链要求 | 工具强制条件 / 断链行为 |
|---|---|---|---|---|
| R0 / doc.read | PUBLIC_DOCS；当前任务含 doc.read、此 scope、剩余额度 | 符合则 ALLOW，否则 DENY | 无逐动作链预约；本地签名读取日志 | 本地公开文档白名单；不能由“公开”标签越过沙箱；离线只用预先加载有效策略和未过期授权 |
| R1 / doc.read | ORG_A_DOCS；调用者组织与文档标签一致；任务明确授予 | 符合则 ALLOW，否则 DENY | 无逐动作链预约；签名日志，后续批量摘要锚定 TODO | 受限文档映射与任务重新检查；无法确定授权/撤销新鲜度时 DENY，不能使用 R0 降级 |
| R2 / mail.send | ORG_A_INTERNAL_MAIL；任务允许 mail.send、目标范围和额度；收件人只在本地 .invalid 邮箱 | 符合基础权限则 REQUIRE_APPROVAL | 请求者签名 + BUSINESS_APPROVER + SECURITY_APPROVER；两名批准者不同组织；真实 RESERVED；最长120秒 | 工具独立查链、全部签名撤销状态、参数承诺/收件人/TaskGrant/时效，数据库 actionId 幂等；链不可用不执行 |
| R3 / doc.delete | ORG_A_DISPOSABLE_DOCS；任务显式 allow_sandbox_delete=true、max_risk=3；只删除可丢弃沙箱文件 | 默认 DENY；满足明确删除授权后才 REQUIRE_APPROVAL | 请求者签名 + BUSINESS_APPROVER + SECURITY_APPROVER + HUMAN_APPROVER；三名不同账户、至少两个组织；真实 RESERVED；最长60秒 | 人工批准精确 doc_id 对应的意图；操作日志与沙箱真实路径边界；链不可用不执行 |

每个动作必须同时满足：当前用户身份、TaskGrant 工具集合/资源集合/最大风险/时效/原子配额、当前策略、注册 Agent 绑定、工具登记。上表的邮箱 scope 是标签，还必须核验任务具体收件人许可；仅匹配域名不构成全部授权。用户在 CreateTaskRequest 指定 agent、allowed_document_ids 和 allowed_recipients；可信任务服务验证用户确实有这些权限后创建 TaskGrant，加密保存原始清单。Agent 的 ProposeRequest 只引用 task_id，不能修改授权清单。

**批准计数规则：**

1. 所有人签署完全相同的 ActionIntent EIP-712 digest；请求者签名走单独参数，不计入审批数量。requester、agent 和 tool signer 均不能兼任本动作批准者。
2. 从签名恢复地址，再读取 PolicyRegistry 中当前有效角色/组织；请求中不提供可被信任的 claimed signer 或组织。
3. R2 业务和安全批准者必须不同账户、不同组织。R3 在此基础上增加一个不同账户 HUMAN_APPROVER；可与业务方同组织，不能复用业务或安全签名，至少两个独立组织。
4. 所有提供的签名均必须有效、未撤销、不重复；任一无效附加签名也拒绝，不静默丢弃。一个地址拥有多个角色也只能占一个位置。
5. 请求者本身必须登记 REQUESTER 并有当前 scope 权限，agent 必须登记 AGENT 且与任务绑定。TOOL_SIGNER 必须登记到具体 toolId，不能任意工具互签。
6. 政策更新提升 policyEpoch；nonce 作用域为 `(chainId, ExecutionRegistry, requester, nonce)`，不按策略或任务重置。工具执行前重新读取上述身份/策略与原预约，旧审批不因预约成功而免检。

## 决策验收表（业务测试 TODO）

| 输入情况 | 应得结果 / 实际副作用 |
|---|---|
| R0 任务授权公开 doc_id | ALLOW；真实读取 |
| R1 尝试其他组织文档 | UNAUTHORIZED_SCOPE；0 次读取 |
| R2 有任务授权但缺安全批准 | APPROVAL_MISSING；0 次发送 |
| R2 两个同组织有效签名 | APPROVAL_INVALID；0 次发送 |
| R2 调包收件人或正文 | PARAMS_MISMATCH 或 UNAUTHORIZED_SCOPE；0 次发送 |
| R2 只有 tx_hash、没有已确认预约 | RESERVATION_UNCONFIRMED；0 次发送 |
| R2 完整批准+真实预约+一致参数 | 本地邮箱新增一次；工具签署真实结果 |
| R2 相同 actionId 重复 execute、参数相同 | 返回持久原始回执；0 次新增副作用；不以过期为由重执行 |
| R2 同 actionId 携带其他参数 | PARAMS_MISMATCH；0 次新增副作用 |
| R3 未显式开启沙箱删除或无人审 | POLICY_DENY / APPROVAL_MISSING；0 次删除 |
| R3 明确沙箱任务+三批准+预约 | 只对指定可丢弃 doc_id 执行一次；真实操作日志 |
| 任意 R2/R3 链不明、状态未知、身份撤销 | 拒绝新执行；保存等待或未知状态 |

已完成动作的幂等结果查询不等于新的执行授权。服务身份仍需有效，并核对 actionId/参数承诺；结果可在链离线或许可过期后返还原回执，但不得再次发邮件/删除。

治理要求：至少两个独立组织的 GOVERNANCE_ADMIN 批准角色、策略和解除暂停的变更；单方仅可触发收紧型紧急暂停。治理写入的签名类型、变更 nonce 和 ABI 在合约实施阶段单独设计和验收（TODO），阶段0不提供不完整的治理写接口。
