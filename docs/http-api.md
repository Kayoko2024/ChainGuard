# HTTP API 契约

状态：仅设计。OpenAPI 3.1 文件为 `spec/openapi.json`，所有 JSON DTO 使用共享 Schema；阶段0没有监听端口或 FastAPI 应用。

Content-Type 为 application/json；拒绝未知字段、重复JSON键、无效编码和超界整数。时间为Unix秒十进制字符串；bytes32/address/signature严格遵循 protocol.md。所有错误统一为 `{ "error": { "code", "message", "retryable", "trace_id" } }`，code与HTTP状态的唯一映射见 `spec/errors.json`。message不泄漏原文、盐、密钥或真实路径。

## 身份与入口

外部API使用Bearer JWT，校验签名、issuer、audience、exp、subject、组织与角色登记；角色不能从请求体决定。createTask 的requester由已认证用户映射得出。Agent只允许propose。reserve为受信执行服务入口；交易账户仅是relayer，不能替用户/审批者签名。审计者须有相应组织作用域；无权访问的action返回NOT_FOUND，避免泄露存在性。

内部工具API同时要求mTLS客户端身份与独立服务Bearer（OpenAPI的同一security对象表示AND）；两者绑定同一个受信网关身份，不能二选一。工具网络禁止Agent容器直连、不映射公共端口；TLS/网络隔离在后续部署实现（TODO）。审计的proof输入不授予执行权。

| 方法与路径 | 输入 → 成功输出 | 入口权限 / 语义 |
|---|---|---|
| POST /v1/tasks | CreateTaskRequest → 201 TaskGrant | REQUESTER；资源清单与Agent先验证权限；原文链下加密 |
| POST /v1/agent/actions/propose | ProposeRequest → 202 ActionRecord | 登记AGENT且绑定task；只提出动作，不能携带新的授权/风险/凭据 |
| POST /v1/actions/{id}/approve | ApproveRequest(signature) → 200 ActionRecord | 当前业务/安全/人工批准角色；恢复公钥并校验准确意图、组织与时效 |
| POST /v1/actions/{id}/reserve | ReserveRequest(requester_signature) → 202 ActionRecord | 受信执行服务；从持久记录加载审批，不信任客户端宣称已批准；202不意味着预约已确认 |
| POST /v1/tools/execute | ExecuteRequest → 200 ToolExecutionResponse | 仅mTLS+服务Bearer；R2/R3，工具自己查链/策略/授权；意图中toolId决定参数Schema |
| GET /v1/tools/actions/{id} | 无body → 200 ToolStatusResponse | 同时要求mTLS+服务Bearer；查询工具持久幂等日志及原始回执，绝不再次执行 |
| GET /v1/actions/{id} | 无body → 200 ActionRecord | 任务所有者或获授权作用域用户；返回真实当前状态 |
| GET /v1/actions/{id}/proof | 无body → 200 ProofBundle | 授权AUDITOR；R2/R3元数据，不含正文/路径/盐；R0/R1此接口返回STATE_CONFLICT，读日志接口后续定义 |
| POST /v1/audit/verify | VerifyRequest → 200 VerifyResponse | 授权AUDITOR；VALID/INVALID/PARTIAL，验证失败也不是HTTP传输失败 |
| POST /v1/actions/{id}/reconcile | ReconcileRequest → 202 ActionRecord | 独立RECONCILER；只提交找回的原始工具回执，不触发工具操作 |
| GET /v1/metrics/summary | 无body → 200 MetricsSummary | 仅本地评测/审计；从真实实验记录聚合；无样本时sample_count=0、P95=null，不返回虚构数值 |

## 幂等与状态

创建任务、propose、reserve、execute和reconcile必须带 `Idempotency-Key: 0x<32bytes>`。键作用域为认证主体+operation；服务持久存储规范化请求摘要和创建的任务/action。相同键/相同请求返回同一实体及其当前可用状态；相同键/不同规范化请求返回IDEMPOTENCY_CONFLICT。approve按恢复出的签名人+actionId去重，重复相同签名只返回已有状态，不能多算一票。

execute必须另外按actionId永久去重，客户端换Idempotency-Key不能增加执行次数。已完成动作返回原始回执（即使许可已过期或链暂不可达），仍检查调用身份和参数一致性；UNKNOWN不允许盲目新执行。GET /v1/tools/actions/{id} 返回action_id、checked_at、工具持久status和可空的原始receipt/tool_signature。NOT_STARTED仅描述该时刻；只有到期/撤销已经阻止新claim、且不存在先前CLAIMED，才能据此转EXPIRED/DENIED。未知动作返回NOT_FOUND，不能伪造“未执行”证明。

202表示已接受并可继续轮询GET，不表示链交易成功或工具成功。200 ToolExecutionResponse也不保证成功：state=UNKNOWN时无明确结果，receipt可为null或outcome=3的有效未知观测；state=EXECUTION_RECORDED要求完整工具签名和outcome=0/1/2，但尚未完成审计上链。明文仅在内部execute传输，盐不得回显到ActionRecord/ProofBundle/日志。

R0/R1不调用高风险execute/reserve。proposal接入后由网关在读取路径处理，ActionRecord使用READ_*，实际内容和签名读取日志的返回/批量锚定API留待读取模块实现阶段定义（TODO），当前仅冻结高风险闭环接口。

## 关键错误及重试原则

| 类别 | 代码 | 调用者行为 |
|---|---|---|
| 结构/身份 | SCHEMA_INVALID(422)、AUTH_REQUIRED(401)、FORBIDDEN(403)、NOT_FOUND(404) | 修正结构或取得有效身份；不得绕过工具入口 |
| 策略/作用域 | UNKNOWN_TOOL(422)、UNAUTHORIZED_SCOPE(403)、POLICY_DENY(403)、POLICY_REVOKED(409) | 停止；新授权必须创建新意图 |
| 批准 | APPROVAL_MISSING(409)、APPROVAL_INVALID(403) | 收集同一意图的有效独立签名；不能降级门槛 |
| 许可 | NONCE_REUSED、PARAMS_MISMATCH、RESERVATION_UNCONFIRMED、RESERVATION_EXPIRED(均409) | 不执行；查原action；参数变化申请新批准 |
| 并发/幂等 | TOOL_ALREADY_EXECUTED、IDEMPOTENCY_CONFLICT、STATE_CONFLICT(均409) | 正常重复请求应返原结果；此类错误用于冲突/不允许的状态操作 |
| 可用性 | CHAIN_UNAVAILABLE(503)、EXECUTION_UNKNOWN(409) | 只查状态或补交原回执；高风险不离线放行 |
| 回执 | RECEIPT_INVALID(422) | 保留原始异常证据，禁止写入虚假终态 |

无预约或参数调包请求直接错误响应并记录拒绝；若已登记预约的真实工具在开始副作用前作出确定业务拒绝，可产生outcome=REJECTED的签名回执，之后finalize为FINALIZED_REJECTED。尚未实现端点不能返回静态“成功”；实现阶段开始前应保持无业务服务，或明确未实现状态。

相对原方案新增 reconcile 和内部工具状态查询，二者只用于原动作对账，不增加执行权。TaskGrant增加明确Agent、文档和收件人集合，防止仅按粗粒度scope或域名替代任务授权。
