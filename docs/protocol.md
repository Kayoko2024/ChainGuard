# 统一数据与密码学规范 1.0.0

状态：SPECIFIED。规范源为 `spec/eip712.json`、`spec/schemas/protocol.schema.json`、`spec/identifiers.json`；后续 Python/合约/工具/前端必须共享它们。`scripts/build_specs.py` 生成 Schema/OpenAPI，`--check` 检查提交文件是否漂移。测试辅助代码不构成运行时授权实现。

## 编码与签名域

- JSON 使用 snake_case，Solidity/EIP-712 使用 camelCase；唯一映射和字段顺序见 eip712.json。额外/缺失字段拒绝。JSON `schema_version` 为整数 **1**，映射到被签名的 `uint16 schemaVersion=1`。文档协议版本为 `1.0.0`，EIP-712 domain.version 为字符串 **"1"**。
- `uint64` 与 `uint256` 在 HTTP/JSON 中均为无符号十进制**字符串**，禁止科学计数、前导零、布尔值或 JSON number。标准 Schema 正则完整限制 64/256 位上界，不能用 JS Number 处理。risk/outcome/schema_version 为小整数。
- bytes32 用 `0x`+64位小写十六进制，地址用 `0x`+40位小写十六进制；禁止零值。内部签名库可使用 checksum 地址，但上网前转换为小写；签名计算用20字节地址，与显示大小写无关。
- action_id、task_id 分别由可信服务 CSPRNG 生成32随机字节，不对低熵任务名称直接哈希。task_id 对应不可变任务授权版本；变更授权创建新 task_id。非敏感登记标签映射：`keccak256(UTF8(namespace + "/" + label))`，工具/资源/策略/组织命名空间在 identifiers.json；角色为 `ChainGuard/role/<ROLE>`。标签只允许已登记 ASCII 精确值，不做大小写或 Unicode 自动修复。
- EOA secp256k1 签名，65字节 `r || s || v`，v=27/28，0<s<=curveOrder/2；不接收个人消息签名、EIP-2098 压缩签名或 EIP-1271 合约钱包（后两者 TODO 扩展）。全部恢复与验签采用标准库/OpenZeppelin。

| primaryType | domain.name | domain.version | chainId | verifyingContract |
|---|---|---|---|---|
| ActionIntent | ChainGuard ExecutionRegistry | "1" | 实际部署网络ID | 实际 ExecutionRegistry 地址 |
| ExecutionReceipt | ChainGuard AuditRegistry | "1" | 同一部署网络ID | 实际 AuditRegistry 地址 |

domain 字段顺序固定：`name:string, version:string, chainId:uint256, verifyingContract:address`。digest 为 `keccak256(0x1901 || domainSeparator || structHash)`。不得混用 Python hashlib.sha3_256。所有请求者/批准者均签相同 ActionIntent；工具只签 ExecutionReceipt。后续业务合约应使用 OpenZeppelin EIP712/ECDSA，不能将测试 harness 用作权限校验。

## ActionIntent 每个核心字段

| JSON / typed 字段 | Solidity 类型 | 含义与约束 | 生产者 → 依赖模块 |
|---|---|---|---|
| schema_version / schemaVersion | uint16 | 固定1，必须签入摘要，升级不能静默解释旧字段 | 规范 → 所有模块 |
| action_id / actionId | bytes32 | 全局随机动作ID；在同一 Registry 永不复用 | 网关 → 合约/幂等表/审计 |
| task_id / taskId | bytes32 | 随机任务授权版本ID；不包含任务原文；须匹配 TaskGrant | 任务服务 → 网关/工具/审计 |
| requester | address | 登记用户公钥；签署本动作；校验当前 REQUESTER 及资源scope权限 | 用户身份服务 → 合约/工具 |
| agent | address | 登记的提议者；与 TaskGrant.agent 和 requester 关联；本身不获得敏感凭据 | 任务服务 → 合约/网关/工具 |
| tool_id / toolId | bytes32 | 精确工具标签映射；MVP 高风险只允许 mail.send 或 doc.delete | 工具登记 → 合约/工具 |
| resource_scope / resourceScope | bytes32 | 非敏感授权分类码；不是路径或收件地址；还需检查完整参数的资源集合 | 策略引擎 → 合约/工具 |
| params_commit / paramsCommit | bytes32 | 规范化完整参数与随机盐的域分离承诺 | 网关 → 批准端/工具/审计 |
| policy_id / policyId | bytes32 | 登记策略ID；getEffectiveRule(policyId) 返回唯一工具/作用域/风险组合 | 策略登记 → 合约/工具 |
| policy_epoch / policyEpoch | uint64 | 当前 policyId 的正整数版本；撤销或实质变更递增，不复用旧版本 | PolicyRegistry → 预约/工具 |
| nonce | uint64 | 请求者的一次性序号；可以从0开始；原子消费，不按任务或纪元重置 | 可信请求者/网关协调 → ExecutionRegistry |
| issued_at / issuedAt | uint64 | 签入的签发 Unix 秒；防未来签发及过长许可 | 网关构造、用户确认 → 合约/工具 |
| expires_at / expiresAt | uint64 | 排他有效期上界；必须晚于 issuedAt，不晚于 TaskGrant 到期 | 网关 → 全部批准者/合约/工具 |
| risk | uint8 | R2=2、R3=3；必须由登记策略导出并与工具/资源一致，不能由Agent降级 | 策略 → 合约/工具 |

R0/R1 不使用链上 reserve，也不伪造高风险 ActionIntent；读取路径的 ActionRecord.intent 为 null，使用 TaskGrant 和本地签名日志（日志实现/批量锚定 TODO）。EIP-712 的 uint8 能表示更多数字，但规范 Schema 和业务校验只允许定义的枚举值。

**时效与重放：** 执行开始必须满足 `issuedAt <= now < expiresAt`。R2 `0 < expiresAt-issuedAt <= 120` 秒；R3上限60秒；同时不超任务期限。合约用 block.timestamp，工具用校准 UTC 秒并记录所观察区块时间；部署时钟偏差超配置阈值则停止放行，不能增加隐含到期宽限。副作用开始前消费幂等资格；完成耗时可能越过 expiresAt，合法结果仍可晚到提交。

nonce 的完整域为 `(chainId, ExecutionRegistry地址, requester, nonce)`；actionId 在 Registry 内唯一。预约交易回滚不消费 nonce；成功后即使过期、拒绝、UNKNOWN 或最终失败也不释放。同请求并发由合约原子处理。审批仅能绑定本动作，不是持续授权。requester 签名与审批签名不可互相计数。

## ExecutionReceipt 每个核心字段

| JSON / typed 字段 | Solidity 类型 | 含义与约束 | 后续依赖 |
|---|---|---|---|
| schema_version / schemaVersion | uint16 | 固定1；签入回执 | 工具/审计/独立核验器 |
| action_id / actionId | bytes32 | 必须存在真实预约，与执行幂等记录相同 | 工具持久日志/ExecutionRegistry |
| params_commit / paramsCommit | bytes32 | 必须精确等于原意图与预约，不能换工具参数 | 审计合约/核验器 |
| result_commit / resultCommit | bytes32 | 对真实结果或明确拒绝/未知观测的加盐承诺 | 证据存储/核验器 |
| evidence_index_commit / evidenceIndexCommit | bytes32 | 加密证据清单的加盐承诺；不暴露存储路径 | 证据服务/独立审计 |
| executed_at / executedAt | uint64 | OK/ERROR 为实际执行完成时间；REJECTED 为工具拒绝判定时间；UNKNOWN 为最后观测时间，并非声称已完成 | 工具时钟/审计时间线 |
| outcome | uint8 | 0 OK；1 ERROR；2 REJECTED；3 UNKNOWN，含义如下 | 工具/合约/状态机 |

- OK：真实操作已成功。ERROR：工具已经作出明确失败判断；部分副作用须在加密结果中记录，不能保证“失败就零副作用”。REJECTED：工具确认尚未产生副作用并拒绝。UNKNOWN：无法判定结果，不允许作为成功/失败最终化。
- executedAt 不早于 issuedAt；成功开始时的有效期由工具日志记录，不能仅靠完成时间证明。提交时对不合理未来时间作拒绝；时钟容差必须在部署配置明示。旧动作晚到有效回执可以在许可过期后锚定，不等于重新授权执行。
- 验签后必须检查 TOOL_SIGNER 未撤销且登记绑定预约中的 toolId。仅有任意 TOOL_SIGNER 角色不足以替别的工具签名。当前撤销的旧工具签名不自动最终化，保留未锚定回执，由后续明确治理/历史证据流程处理，不能绕过验签。
- 相同 actionId 的完全相同回执幂等返回已有确认；冲突结果拒绝并保留冲突证据。UNKNOWN 只能通过追加 reconcile 事件变成明确结果；终态不能覆盖。

## 参数、结果和证据承诺

```
canonicalBytes = UTF8(RFC8785_JCS(value))
commit(kind, salt, value) = keccak256(
    UTF8("ChainGuard/" + kind + "/v1") || 0x00 || salt[32] || canonicalBytes
)
kind = "params" | "result" | "evidence"
```

每个承诺使用独立、非零、CSPRNG32字节盐；原文与盐仅在链下加密保存，内部受认证通道交给工具或授权审计者。向量中的公开固定盐只是测试数据，不用于业务。明文不允许直接 `hash(email)` 上链。

JCS 使用 UTF-16 键排序、UTF-8 输出，不做 Unicode NFC/NFKC 归一化；同形异码字符串产生不同承诺。结构化工具标识和 doc_id 只接受严格ASCII；正文保留原始 Unicode。JSON 重复键、非法 Unicode surrogate、NaN/Infinity、超安全整数必须在解析阶段拒绝，不能先丢信息再验签。MVP承诺数据只使用字符串、布尔、null、对象、数组和安全整数，禁用浮点数；业务参数在签名前完成明确格式校验，不静默改写邮箱本地部分、路径或正文。邮箱只接受本地测试域 `inbox.chainguard.invalid`；doc_id 必须在可信沙箱资源表解析。

## 其他接口数据与信任来源

- TaskGrant：schema_version、task_id、requester 由可信任务服务生成/绑定；用户选择 agent、allowed_tools、resource_scopes、allowed_document_ids、allowed_recipients、expires_at、max_risk、allow_sandbox_delete、max_actions，服务逐项与当前用户真实权限求交并拒绝越权，不能原样信任请求。task_text 和资源清单加密留链下。取消由可信任务服务撤销，工具执行前重新查询；访问失败不放行。配额消费需与 actionId 去重协调。
- Solidity Reservation：完整 ActionIntent、intentHash、ReservationStatus、reservedAt、恢复所得 approvers 数组。工具重查当前签名撤销状态需要此数组；不能由网关声明组织。保留原 reserve 交易与调用数据供独立核验请求者和全部批准签名。
- ActionRecord：action_id/task_id/risk 是索引；state 为业务状态；chain_state 是最后确认链状态；anchor_status 表示 NOT_APPLICABLE/PENDING/CONFIRMED；intent/receipt/链证据允许按阶段为null；error 为统一错误。各处重复ID/承诺/风险必须一致，JSON Schema之外还需运行时跨字段验证（TODO）。链状态不明时保留最后已知值，不能编造最终状态。
- ChainEvidence：chain_id、registry、tx_hash、block_hash、block_number 仅为定位信息。接收方使用自己的可信节点重取成功receipt、核对规范链区块和对应事件/预约字段；HTTP提交的所谓证明不能独立授予执行权。
- ProofBundle：意图、请求者/批准签名、可空工具回执和签名、两类链证据、实际合约地址与 evidence_status。不含参数明文或盐。VALID 需要授权取回原文重算承诺，并独立读取角色/组织与事件历史；缺少原文或权限只能 PARTIAL，不能把“哈希存在”当全量核验成功。

## Golden vector 的使用和边界

`spec/vectors/eip712-v1.json` 包含：两份完整 typed_data、每层 typeHash/domainSeparator/structHash/digest、请求者/业务/安全/工具的真实公开签名、参数/结果/证据的规范化字节和加盐承诺，以及UTF-16排序边界案例。nonce 使用 `9007199254740993` 验证JS精度边界。

向量 chainId=31337，两个 verifyingContract 为固定夹具地址；**未声称在这些地址部署业务合约**，也没有交易哈希。结果对象是密码学测试输入，不是邮件执行证据。Python eth-account 与独立 eth-abi、JS ethers、Solidity/OpenZeppelin 在实际本地 EVM 中读取同一文件验证。生成时临时私钥只存在进程内存，不写文件、不输出。

正常复现只运行测试，不运行 generate_vector.py。重新生成会轮换公开签名人和签名，是需要审查的夹具变更；摘要由输入重算，测试不依赖原私钥。生产私钥、测试签名私钥和API Key均不提交。

## 相对原方案的明确细化

1. schema_version 从示例字符串统一为签名内 uint16=1，并补入两个结构。
2. 增加签名字段 issuedAt，以可验证地限制总许可寿命；时间统一Unix秒字符串，排他到期边界。
3. 将“任务名称/工具名/时间字符串”示例替换为明确随机ID/登记映射/整数编码；固定字节承诺公式。
4. 完成 R3 三个不同账户、至少两组织的人审门槛；明确请求者不能充当本动作批准者。
5. 引入 EXECUTION_RECORDED 和 FINALIZED_REJECTED；低风险读取采用独立路径，避免把未上链回执显示为最终成功。
6. 完整治理写协议、批量读日志锚定、部署确认健康阈值、密钥恢复流程仍是后续 TODO，不能由阶段0接口测试代替。
