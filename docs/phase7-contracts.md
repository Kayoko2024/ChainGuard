# 阶段7 Runner、工具代理与基准接口

本轮范围是固定trace与AgentDojo适配。**真实LLM攻防测试尚未完成。** 原ActionIntent、ExecutionReceipt、EIP-712、状态机、共用策略和三个合约保持原样，继续以[contracts.md](contracts.md)和[phase6-contracts.md](phase6-contracts.md)为准。新增接口导航为`spec/agent/interfaces.json`。

## 数据与调用边界

| 字段/对象 | 来源、校验和用途 |
|---|---|
| ToolCall.id | 模型/固定trace给出的1–64字符稳定调用ID；同一轮重复ID拒绝，同一run已有ID不能换参数 |
| ToolCall.name / arguments | 只支持doc.read/mail.send/doc.delete；严格使用原参数Schema，禁止额外approved/risk/角色字段 |
| run_id / task_id | 可信运行配置提供；task_id为原bytes32 TaskGrant ID，文档/邮件内容不能改变它 |
| Journal.idempotency_key | 使用Agent日志随机密钥，对run_id/call_id作HMAC；调用前持久化，进程重启沿用原键 |
| Journal.request_mac / data | 任务/工具/完整参数的HMAC绑定；请求及结果AES-GCM加密，公开事件仅参数SHA-256和元数据 |
| action_id / record | 完全取自认证网关的原ActionRecord，使用原Schema校验；Agent不生成链许可或签名 |
| doc_id / read_execution_id | 工具端本地PUBLIC_DOCS测试资源与真实读取执行ID；独立capability绑定任务/Agent/文档/期限 |
| source_kind / trust | document或email；固定trust=untrusted。观察仅作为tool-role消息，含伪造SYSTEM文本也不能提升角色 |
| content / sha256 | 内容来自容器实际文件，Proxy重算UTF-8 SHA-256；公开日志仅摘要，原观察留在私有日志 |
| agent_attempted_tool | boolean，与tool_name/call_id关联；代表Agent尝试，不能证明执行 |
| policy_verdict | READ_ALLOWED、REQUIRE_APPROVAL、ALLOW、DENY、UNKNOWN或null；保留网关状态和错误码 |
| tool_executed | 有真实读取/OK回执或独立效果证据才true；明确执行前拒绝才false；失联、查询失权及ERROR可能部分执行时null |
| attack_success | 固定trace一律null。真实模型实验须由适用的原版基准判定器单独产生结论 |
| mode / llm_sample_count | 本轮fixed_trace、0；不以强制调用trace说明LLM被诱导或计算攻击率 |

`AgentRunner`有turn/call上限，允许Backend返回多个工具调用，所有调用仍逐一经过Proxy。缓存结果只表示原动作结果；重放trace不新增高风险副作用。UNKNOWN只查询原action_id，不能approve/reserve/工具执行或新建替代动作；已提交后权限丢失也不能推断未执行。

## HTTP扩展与原安全路径

| 路由 | 输入/输出、强制权限 |
|---|---|
| POST /agent/v1/reads | 严格task_id/doc_id和bytes32 Idempotency-Key；Agent JWT、当前身份、任务绑定/撤销检查；返回实际观察上述6个字段 |
| POST /internal/v1/reads | task_id/agent/doc_id；原工具中间件强制网关mTLS指纹AND独立Bearer，broker再次检查capability |
| GET /operator/v1/pending | 固定操作员mTLS指纹、当前REQUESTER/BUSINESS_APPROVER/SECURITY_APPROVER及动作可见性；返回action_id/task_id列表 |
| GET /operator/v1/actions/{id}/review | 同一可信身份和作用域校验；完整intent/params/params_salt只经私有审阅通道返回 |
| POST /v1/agent/actions/propose | 原阶段6接口；所有高风险调用都走此入口。未接入的C删除返回POLICY_DENY，无执行回退 |
| GET /v1/actions/{id} | 原阶段6接口；查原状态及证据，不能因202/txhash或Agent文字宣称执行完成 |

读取capability由本地可信操作员通过工具私有操作员凭据预置。它是独立R0测试读取权限，**不修改原R2 TaskGrant的allowed_tools或作用域**，不产生预约。读取请求重试可能产生再次读取；高风险actionId永久去重机制不变。

测试操作员进程只批准自己预置任务ID及精确authorized_mail参数，先核对参数承诺，再签同一ActionIntent的请求者/不同组织业务安全签名，并使用原executor入口reserve。Agent没有此进程的HTTP签名接口、卷、密钥或JWT。审批器是明确标识的本地可信验收进程，不能声称机构独立托管或面向任意任务的人工批准产品。

业务状态仍为原AWAITING_APPROVAL→RESERVING→RESERVED→真实工具核验/执行→EXECUTION_RECORDED→FINALIZED_OK。拒绝提议在产生动作前返回原错误；不捏造链上DENIED交易。Proxy的COMPLETED仅说明模型/trace循环结束，业务是否执行必须看每条ActionRecord。原UNKNOWN、审计补提交与对账guard继续由阶段6服务负责。

## 模型与基准扩展点

`ModelBackend.next_turn(messages, tools) -> Turn(content, calls)`独立于网关。`configured_backend`明确选择fixed_trace或real_llm，后者只读取`CHAINGUARD_LLM_MODEL/BASE_URL/API_KEY/TIMEOUT_SECONDS`。配置模板在`agent/.env.example`，保留原阶段1严格env加载规则。HTTPBackend支持工具调用协议，HTTPS或显式loopback HTTP；禁重定向和过大响应，密钥不进入repr/公开配置。现有自动测试只请求本地协议fixture服务器，**不是实际模型推理**。

AgentDojo `FunctionCall`经`WorkspaceMapper`映射到同一Proxy。只支持send_email、get_file_by_id、delete_file。原邮件身份通过可信、单射映射改为.inbox.chainguard.invalid；文件ID通过显式表变为安全doc_id。正文/主题不改，非空附件/CC/BCC、未映射身份和其他工具明确拒绝为INCOMPATIBLE，不丢字段或改判定器。

后续依赖：阶段7真实模型子任务需配置模型与受限模型网络路径、保留正常任务和文档/邮件注入原始模型输出、使用适用的原版判定器并记录不兼容样本。阶段8正式A/B/C前必须完成此子任务及可比任务映射，不能直接把本轮trace放进统计表。
