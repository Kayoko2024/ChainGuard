# 阶段3中心化A/B HTTP契约

全部业务接口位于/central/v1。冻结/v1的链预约/执行契约保持不变且未实现；不把中央状态映射成链上RESERVED。实际OpenAPI由启用中心化服务的/operations/openapi.json生成，验收导出results/phase3/{a,b}-openapi.json。

所有业务请求使用Authorization: Bearer JWT，固定HS256，校验issuer=chainguard-local-central、audience=chainguard-central-gateway、exp/nbf/iat、subject；角色/组织/资源从服务自己的加密登记读取。没有HTTP注册管理员、签发JWT、生成审批私钥或修改组别的入口。请求JSON必须UTF-8，最大64KiB；重复键、浮点、NaN、超安全整数、无效Unicode和未知字段拒绝，不自动归一化正文/地址。

| 方法/路径（前缀/central/v1） | 输入 | 输出与权限 |
|---|---|---|
| POST /tasks | 冻结CreateTaskRequest；Idempotency-Key | 201冻结TaskGrant；REQUESTER，与当前账号权限求交，Agent必须已登记绑定同组织 |
| POST /actions/propose | 冻结ProposeRequest；Idempotency-Key | 202 CentralActionRecord；仅TaskGrant绑定的AGENT；工具白名单由冻结规则导出，risk不能由调用者传入 |
| POST /actions/{id}/approve | 冻结ApproveRequest(signature) | 200中央动作；B组当前业务/安全/人工角色，恢复签名地址必须等于JWT登记地址；精确意图、当前scope/组织/撤销/时效；相同签名不重复计票 |
| POST /actions/{id}/execute | CentralExecuteRequest；Idempotency-Key | 200实际中央状态；仅任务REQUESTER；B的R2/R3必须requester_signature和全部独立批准；A及B低风险可用{} |
| GET /actions/{id} | 无body | 200当前中央状态；所有者/绑定Agent或有scope的审批/审计角色；无权访问返回404；完整工具结果仅所有者/绑定Agent可见 |
| GET /audit/entries | 无body | 200真实ActionTrace条目、签名/哈希链和检查点；仅拥有全部测试scope的AUDITOR；A的signature/checkpoint为空 |
| GET /audit/checkpoint | 无body | 200当前签名检查点及公开签名者；相同审计权限；B应由独立持有者保存 |

所有错误使用冻结ErrorResponse与spec/errors.json映射。X-Trace-Id为每次请求的随机bytes32。成功的幂等重放返回原实体/结果，不新增副作用；键作用域为认证主体+operation，execute的请求摘要同时绑定action_id。同键不同规范请求409，同动作换键也不能增加执行次数。审批按恢复出的signer+action_id去重。

## CentralActionRecord与状态

定义在spec/central/schemas.json，运行时校验；task_id/action_id/tool_name/risk、ActionIntent和签名均复用冻结类型。

| 字段 | 语义 |
|---|---|
| record_type/group | CentralActionRecord、A或B；组别由私有部署配置固定，不由请求选择 |
| action_id/task_id/tool_name/risk | CSPRNG全局动作/任务ID、白名单工具、工具资源映射导出的风险 |
| central_state | READY、AWAITING_APPROVAL、DENIED、CENTRAL_OK、CENTRAL_REJECTED、UNKNOWN |
| policy_verdict/policy_error_code/policy_enforced | 共用策略实际判断及原因；A记录shadow结果但不强制任务ABAC；B强制执行 |
| intent/typed_data | B的R2/R3冻结ActionIntent与精确typed data；A和低风险为空。参数原文/盐不在响应中 |
| approval_count | 已持久签名数，不表示当前撤销状态仍有效；执行时重验全部签名 |
| result | 实际LocalExecutionRecord；不是ExecutionReceipt；未执行/未知可为空 |
| chain_state/chain_evidence/execution_receipt | 恒为NONE/null/null，因为本阶段没有链交易或工具签名回执 |

提议时B确定拒绝→DENIED；B低风险与A获常规账号授权→READY；B高风险→AWAITING_APPROVAL，审批签名持久追加，请求者在execute签署同一意图。执行事务先原子消费任务配额并写内部DISPATCHING和签名dispatch日志；工具再核验当前授权后实际执行。明确结果→CENTRAL_OK/CENTRAL_REJECTED；响应丢失或崩溃遗留DISPATCHING对外为UNKNOWN。UNKNOWN不再次分发，完成动作换键/重启后返回原结果。没有FINALIZED状态或伪链交易。

## ActionTrace与签名日志

字段由同一schemas.json定义并在写入前校验：trace_id/action_id/task_id、deployment_id/group、subject_hash、event、tool_name/risk、policy_verdict/error_code、policy_fingerprint/policy_epoch、params_commit、tool_state/tool_executed、approval_count/independent_org_count、observed_at、elapsed_ms、sequence。日志不包含正文、收件人、文件路径、JWT、盐或私钥。tool_executed为null时明确结果未知；DISPATCH事件仅表示尚未调用工具。elapsed_ms为实际单调时钟耗时，不是LLM/链性能指标。

B：eventHash=keccak256("ChainGuard/central-audit/v1" || 0x00 || previousHash || JCS(event))，用独立审计EOA密钥进行EIP-191签名；检查点对deployment_id、group、policy_fingerprint、sequence、last_hash在独立checkpoint域签名。普通SQL UPDATE/DELETE被触发器拒绝；每次追加先重验现有签名链和签名头，损坏后禁止新分发。该签名不是ExecutionReceipt签名。

无独立检查点只可PARTIAL；持有完整合法尾部以前的日志无法自证未被截短。独立检查点可检测截断；若同一运营者同时控制日志私钥、数据库与所有检查点，不宣称能防其重写。B仍是单域治理，与未来C的多验证主体共同历史不同。

B的ActionIntent域：冻结name/version，chainId=0，verifyingContract为本部署审计公钥地址（中央域标识，未部署合约）。未来C使用真实非零链ID和真实合约地址；不得复用B签名。
