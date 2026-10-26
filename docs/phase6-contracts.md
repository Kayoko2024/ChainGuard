# 阶段6 R2 接口、状态与依赖

原规范入口为[contracts.md](contracts.md)。阶段6复用原ActionIntent/ExecutionReceipt、EIP-712、Schema、错误和状态机；没有修改原21份冻结文件、8份B/C策略或三个业务合约。原设计中的伪代码/示例是需求依据，最终字段以阶段0冻结文件为准。

## 动作与审批

| 字段 | 本阶段来源和强制核验 | 后续依赖 |
|---|---|---|
| schema_version | 固定整数1；签入uint16 | 所有客户端不能自行升级 |
| action_id | 网关CSPRNG bytes32；链永久唯一，工具PRIMARY KEY | 证据查询/对账使用原ID |
| task_id | 加密不可变TaskGrant的随机版本；工具核对三方绑定 | 后续任务撤销/授权管理 |
| requester / agent | 认证身份映射；当前链角色、requester-agent绑定与工具TaskGrant复验 | Agent仅有propose JWT，不能持审批/工具凭据 |
| tool_id / resource_scope | 精确mail.send / ORG_A_INTERNAL_MAIL标签keccak；Agent不能传风险替代值 | 其他工具需单独阶段接入 |
| params_commit | 原JCS+32字节独立随机盐+域分离keccak；工具完整重算to/subject/body | 正文与盐仅可信内部传输/加密存储 |
| policy_id / policy_epoch | POLICY_R2_MAIL及当前链版本；签名、预约和执行前当前值一致 | 治理变更不能复用旧审批 |
| nonce | 请求者持久序号，uint64十进制字符串；合约永久消费 | 不随过期/UNKNOWN/审计完成释放 |
| issued_at / expires_at | Unix秒字符串；R2至多120秒、不超任务期限；开始执行前排他检查 | 完成可能晚于expiresAt，原回执可晚到 |
| risk | 固定R2整数2，工具/策略/范围共同确定 | R0/R1/R3链业务仍TODO |

请求者与业务、安全批准者签同一完整ActionIntent。动作域为`ChainGuard ExecutionRegistry`、version `1`、chainId `20261026`、verifyingContract `0x5effbc396c8532801c2a5e7a4d903b7c8702878a`。工具从真实reserve调用数据恢复请求者和全部审批签名，与链存储approvers逐个匹配，再检查当前角色、组织、scope、撤销和策略。业务/安全必须不同地址、不同组织；排除requester、agent和工具签名人。原golden vector的31337和中央B的0保持不变。

## 回执与真实副作用

| 字段 | 本阶段来源和核验 |
|---|---|
| schema_version / action_id / params_commit | 固定1、原动作ID和原参数承诺；网关与AuditRegistry均核对 |
| result_commit | 本地SQLite邮箱真实message_ids、收件人、MIME SHA-256和transport结果的独立加盐承诺 |
| evidence_index_commit | 含核验区块、实际started_at和MIME索引的加密证据清单承诺；盐独立 |
| executed_at | 真实工具完成时间字符串；不早于issuedAt，不接受未来时间 |
| outcome | 本场景真实成功为0；不把未知写成失败或成功；原协议1/2/3枚举不变 |

工具域为`ChainGuard AuditRegistry`、version `1`、同一chainId、verifyingContract `0x5d505b4ad2c4596b3ba3742ca5b338eb4d05f2ee`。工具独占签名私钥；网关恢复公钥、核对当前具体toolId绑定，合约再次验证。结果、证据和盐AES-GCM保存在工具卷，网关保存加密原回执/签名及待提交记录。

邮箱是真实本地SQLite MIME邮箱，transport=`LOCAL_SQLITE_MAILBOX`，不调用SMTP或外部邮箱。actionId占用、任务配额、MIME投递、执行记录和签名回执在**同一个SQLite事务**提交；签名/写盘失败时一并回滚。本阶段的原子一次性保证只覆盖该本地数据库，不外推到不可回滚第三方SMTP/API。缓存只返回已完成原回执；不同参数拒绝，即使换HTTP幂等键也不新增投递。

## HTTP 实现子集

成功DTO和错误格式均复用`spec/openapi.json`和原Schema。外部Bearer JWT经签名、issuer、audience、有效期和当前登记身份校验；传输还使用本地测试CA签发证书。

| 路由 | 权限 / 行为 |
|---|---|
| POST /v1/tasks | REQUESTER；本阶段只允许R2内部邮件任务；201 TaskGrant |
| POST /v1/agent/actions/propose | 绑定AGENT；拒绝任务外收件人/外部域；202 ActionRecord |
| POST /v1/actions/{id}/approve | 认证主体必须匹配恢复签名人；同一签名幂等；200 |
| POST /v1/actions/{id}/reserve | 独立executor服务主体；不能由Agent调用；202仅表示持久受理 |
| GET /v1/actions/{id} | 所有者或有scope的审阅者；准确返回本地/链状态和证据 |
| POST /v1/actions/{id}/reconcile | 当前链RECONCILER；只接受原始工具签名回执；202，无工具执行 |
| POST /v1/tools/execute | mTLS真实客户端证书指纹 **且** 独立Bearer；完整校验后唯一执行；200 |
| GET /v1/tools/actions/{id} | 同一双重服务身份；只查原始持久回执，未知ID为NOT_FOUND |

create/propose/reserve/execute/reconcile要求32字节Idempotency-Key，持久比较规范请求MAC；换键不能改变actionId幂等。内部`GET /internal/v1/authorization/{id}`是工具到任务权威的双重认证读取，不授予链权限，只返回当前TaskGrant/身份/撤销、配额已占用和dispatch标记。其与工具独立查链必须同时满足。

`/operations/openapi.json`从冻结OpenAPI筛出网关已实现子集；全量审计proof/verify、metrics、R0/R1读取和R3工具API仍TODO，未实现路由返回NOT_FOUND。`/health/ready`只表示进程可接收请求；每个敏感操作另行强制链健康检查，不能把该健康HTTP视为执行许可。

## 状态和故障边界

| 变更或等待 | 必须成立的事实 |
|---|---|
| 提议 → AWAITING_APPROVAL | 确定性ABAC/RBAC通过；PROPOSED事件持久化 |
| AWAITING_APPROVAL → RESERVING | 当前完整三方签名、任务配额和时效通过；持久状态在广播之前 |
| RESERVING → RESERVED | 成功receipt在两个节点一致、规范区块成员和ActionReserved事件/存储匹配；健康QBFT共同提交区块 |
| RESERVED派发中 | 先持久dispatch_started，保持RESERVED；这不是工具已执行证明。恢复后有该标记只能进入UNKNOWN，不能再派发 |
| RESERVED → EXECUTING → EXECUTION_RECORDED | 工具独立核验并在本地事务占用、执行、签回执；网关取得有效回执后在同一事务记录EXECUTING_CONFIRMED及明确结果，避免提前宣称已开始 |
| RESERVED / EXECUTING → UNKNOWN | 派发响应失联、篡改回执、崩溃等；保留异常及最后确认chain_state，绝不再次dispatch |
| UNKNOWN → EXECUTION_RECORDED | 认证查询原工具日志或授权reconcile找回原有效签名回执；查不到继续UNKNOWN |
| EXECUTION_RECORDED → FINALIZED_OK | 成功AuditRegistry receipt、事件、receiptHash/signer及ExecutionRegistry终态全部匹配；anchor_status才变CONFIRMED |
| 链上RESERVED → UNKNOWN → FINALIZED_OK | 独立reconciler先markUnknown，原工具回执走AuditRegistry.reconcile；不删除历史事件、不增加执行权 |

网关节点1/3，工具节点2/4，分别核对实际chainId/genesis、4名验证者、peer=3、共同区块、区块新鲜度10秒和部署代码摘要。QBFT已提交区块就是确认条件，不用公链概率确认数。此设置偏保守：部分节点故障即使链仍可形成quorum，也可能暂停工具放行。撤销核验使用观察到的共同区块；核验后并发撤销无法事后撤回副作用，证据记录检查区块和开始时间。

待提交事务先加密保存nonce/raw/hash。查询已存在hash；若节点没有该交易、链健康且该nonce未被其他交易消费，**只重投完全相同的签名字节**。不生成新nonce或交易、不重发工具动作；已有pending/receipt只查询。nonce被其他交易消费时停止并记录STATE_CONFLICT，需人工分析。每个部署只支持一个worker/relayer；不与另一服务共享同一发送账户并发写入。

TODO边界：尚无自动的未派发动作过期/撤销收尾服务；保守保留原记录并拒绝执行，不伪造DENIED/EXPIRED证据。工具无明确原回执的UNKNOWN不自动终结。链上工具签名人被撤销后的旧回执不绕过当前验签；保留待提交等待明确治理处理。真实SMTP、生产密钥托管、机构独立部署、完整审计API/前端/Agent/统计评测均待后续阶段授权。
