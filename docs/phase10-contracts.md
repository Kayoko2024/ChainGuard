# 阶段10业务台与动态审计契约

## 工具风险、会话与批量存证（2026-10-28）

独立增量，原TaskGrant/ActionIntent/ExecutionReceipt/120秒/R0–R3及三个Registry不变。当前覆盖custom dataset.lookup/github.read/http.request；固定本地默认库沿原capability。注册/versions不要求risk，服务端保留适配器原数值risk；提交risk_level拒绝。OrgB在activation必须给`risk_level: LOW|HIGH`，仅安全会话可提交。标签绑定精确revision并记录真实治理receipt，不自动迁移旧ACTIVE工具。HIGH不赋予查询适配器敏感写能力；mail.send始终原R2链路。

新域`ChainGuard ToolAdmissionRegistry`/version=1/实际chainId/实际ToolAdmissionRegistry地址。`ToolReview(bytes32 revision,uint8 riskLevel,bool enabled,uint64 nonce,uint64 epoch,uint64 issuedAt,uint64 expiresAt)`：riskLevel=1 LOW/2 HIGH，OrgB当前SECURITY_APPROVER或本组织GOVERNANCE_ADMIN签，链验证org/角色/撤销/期限/epoch/nonce，每次更新递增该revision的generation。停用或重打标签立即使旧代际授权失效。原三个EIP-712域不复用。

`SessionGrant(address requester,address agent,bytes32 taskId,bytes32 toolsHash,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint32 maxCalls)`由OrgA请求者容器私钥签一次：

| 字段 | 约束及用途 |
|---|---|
| requester / agent | 当前REQUESTER及其链上绑定的AGENT；签名恢复必须是requester，浏览器/Agent不持私钥 |
| taskId | 原任务精确ID，不能转移给另一个任务 |
| toolsHash | keccak256(JCS(scopes))；scopes为`[{name,revision,allowed_keys,generation}]`，精确绑定≤8个LOW工具、版本、资源键、审核代际 |
| nonce | uint64；新增JSON限制0..2^53−1，实际生成52位随机数；两门各自永久UNIQUE(requester,nonce)，相同信封安装幂等，改任务/参数重放拒绝 |
| issuedAt / expiresAt | Unix秒，当前时间不得早于签发，expiration为排他边界，最长86400秒且不超过任务期限 |
| maxCalls | 1..10000；各门BEGIN IMMEDIATE内先永久占用callId并扣次数，再执行；重复callId仅返回原结果，改参冲突 |

任务API可附加`session_grant={duration_seconds:60..86400,max_calls:1..10000}`，默认24小时/50次，custom任务原TaskGrant上限24小时，邮件意图仍120秒。LOW每次只读核验真实链的标签/代际/暂停/身份、签名、范围、期限和本地剩余额度；不逐次发交易。HIGH、SESSION_MISSING/EXPIRED/EXHAUSTED进入`AWAITING_TOOL_APPROVAL`。精确`ToolUseApproval(bytes32 callId,address requester,address agent,bytes32 taskId,bytes32 revision,bytes32 paramsHash,uint64 generation,uint64 expiresAt)`须当前不同组织的BUSINESS_APPROVER与SECURITY_APPROVER两地址签名（均非requester/agent）；参数哈希含私有盐，工具独立重算，300秒过期须新建授权调用，不延长旧签名。

调用持久状态：AWAITING_TOOL_APPROVAL → STARTED → DONE；STARTED为执行前占位，重启/丢响应只对外UNKNOWN，禁止重新派发。会话过期/超额不重置额度，只允许精确调用强审批；链失联/策略撤销/越界拒绝或保持未知，不能降级直连。工具独立重复会话/额度/当前链及原capability校验；多副本必须共享同一门的持久DB，复制/回滚数据库不属于全局配额保证。

日志先持久写入本地调用表，结果后追加`{schema,sequence,call_id,task_id,agent_id,tool_id,params_hash,timestamp,outcome,result_hash}`；参数/结果哈希为带独立随机盐的keccak承诺，原文和盐在原加密数据库，链上仅root/count/sequence边界。UNKNOWN的结果哈希承诺“不确定”观察，不虚构成功结果。每300秒或50条发布≤50条批次：叶=keccak(0x00||JCS(log))，父=keccak(0x01||left||right)，有序、奇数复制末叶。`LowRiskAuditAnchor`固定独立publisher，batchId一次不可覆盖；签名raw/hash/nonce先持久化，恢复只查/重播同字节，不换nonce。原reserve/finalize不共用发布账户。

批次状态PENDING_BATCH→PREPARED→ANCHORED，交易不可用保持待提交。前端展示链ID/区块/交易/root和Merkle路径；审计服务器从独立公开配置固定新合约地址/codeHash，四节点核对receipt/status/block/输入/publisher及历史batches状态，重算叶/路径后才返回BATCH_VERIFIED。根确认前不声称不可篡改；确认后仅证明包含性，不证明外部数据真实、工具诚实或代替R2签名回执。原始资料丢失无法从root恢复。

新增业务API（均沿原角色/Origin/CSRF，不向GET审计实例加写入口）：

| 入口 | 作用 |
|---|---|
| POST custom-tools/{revision}/activation + risk_level | OrgB标签审核/停用并提交真实链交易 |
| GET tasks/{id} | 原结果外增加session_envelope/custom_calls/batch_observations，私有会话可审阅精确调用 |
| POST tasks/{id}/tool-calls/{call_id}/approve `{digest}` | biz/security独立身份签精确调用 |
| POST tasks/{id}/tool-calls/{call_id}/execute `{}` | requester确认原调用；UNKNOWN不重发 |
| POST audit-batches/flush `{}` | requester/security触发同一个批量发布器，供现场演示，无工具执行权 |
| GET /audit-api/v1/actions/{entry}/verify | 批量记录返回PENDING_BATCH/BATCH_VERIFIED/INVALID/UNAVAILABLE；原高风险验证路径不变 |

跨语言新固定向量`spec/vectors/session-v1.json`独立于原golden vector；Python/ethers/Solidity都实测，不覆盖任何冻结向量。现有集成的输入/返回Schema、GitHub仓库链准入和HTTP公网/固定请求限制继续生效。

## 既有接口与阶段记录

通用 API 增量（2026-10-28）：沿原 custom-tools 注册/versions/activation 与原 custom-tools/query，新增 `http.request`，只接受 **R1 查询／推理**，不能承接 R2/R3 副作用。注册基础字段不变，额外精确 `http={url,method,purpose:"query_or_inference"}`，method 为 GET/POST；key_field 固定 profile，output_fields 固定 profile/response。records 为1–20个 `{profile,query,body}` 请求配置，profile 为1–64个英数/下划线/连字符，query 是平铺 JSON；GET body=null，POST body 为 JSON 对象。参数值支持字符串、布尔、整数、数组及嵌套对象，Body 可含 null；最多6层/每容器32项/字符串4000字符/总规范化32KiB，不接收浮点参数（外部返回的浮点 JSON 可正常展示）。禁止凭据字段；不支持自定义Headers、鉴权、二进制或上传文件。API地址、方法、目的、参数及Schema都覆盖于原版本摘要，变更创建DRAFT版本重审；没有改动任何冻结签名或高风险结构。

OrgB 按精确 revision 审核，须核实目标API确属查询／识别；Method 本身不能证明只读。通过准入后，可信工具安装不可变配置到独立 HTTP 服务，任务仅选择准确的版本/profile，模型参数仍为 `{query:profile}`，不接收模型给出的URL/Body。工具在执行前及返回前独立复核Task/Agent/期限/ACTIVE/精确键，HTTP服务独立检查已安装且未撤销的版本及profile。配置中的数据会发给外部API，返回作为不可信tool-role；原邮件双组织ActionIntent审批/链预约/工具二验保持不变。

HTTP服务只连专属内部服务网与出口网，无宿主挂载、公开端口、链/模型/邮件凭据；内部Bearer仅工具和读取专用卷。仅公开HTTPS默认443、无用户信息/URL查询/片段/编码路径/跳转，URL参数须独立配置；DNS解析全部地址必须为公网，拒绝私网/环回/链路本地/IPv4映射/6to4/Teredo/已知NAT64网段，TLS连接固定已检查IP并核验原主机名，禁继承代理。api.github.com/github.com及其子域必须用原链治理适配器，不允许通用入口绕过仓库限制。请求时限6秒、读取阶段8秒预算（单次阻塞读取最多再6秒）、响应128KiB/投影16000字符、JSON-only、每分钟20请求；超限/跳转/断网明确HTTP_*错误，无mock兜底。这是服务实现约束，不宣称出口域名防火墙或自动证明任意远端无副作用。

工具 `custom_http_results` 和服务 `fetches` 分别持久化调用状态；execution_id 绑定 task/agent/revision/完整调用参数，同任务同配置只发一次且返回原成功记录。服务在发请求前保存STARTED；超时/崩溃保持UNKNOWN，同ID绝不重新发POST；进程重启亦然。目前未知请求的管理端只读对账接口TODO，不能声称支持外部API exactly-once。原始响应、请求配置及结果都AES-GCM保存于私有卷，公开只投影执行ID/版本/摘要，`EXTERNAL_TOOL_OBSERVATION` 明示非链认证，不生成预约、工具签名或finalize交易。单命令新网页/真实模型验收与只读原件复验见README。

GitHub 仓库链上准入增量（2026-10-28）：独立 `RepositoryReadPolicy` 引用原 PolicyRegistry 当前组织/治理角色/撤销与暂停状态，不修改原三合约、ActionIntent/ExecutionReceipt 或 R2/R3 规则。新 EIP-712 域 `ChainGuard RepositoryReadPolicy`/`1`/实际 chainId/新合约，结构为 `RepositoryRuleChange(bytes32 repositoryHash,bool enabled,uint64 nonce,uint64 epoch,uint64 issuedAt,uint64 expiresAt)`，签名顺序与类型由新模块 `github_policy.RULE_TYPES` 和独立合约测试核对，不写入原 eip712.json。repositoryHash 为 keccak256(UTF-8 `ChainGuard/github/repository/` + 规范小写 owner/repo)，Issue 共享父仓库的链准入，但仍须原精确 Issue capability。默认拒绝，首轮双组织治理只启用 microsoft/vscode；两名不同、不同组织的当前 GOVERNANCE_ADMIN 签名，nonce/epoch/期限/链与合约域全部绑定，启用/撤销均需双签。无浏览器治理写接口，原 OrgB 目录审核不等于新合约治理。

工具在 HTTPS 前/结果释放前用 node2/4 独立核验，读取服务另用 node1/3 核验。检查真实链/创世/验证者/区块一致与新鲜度、原三合约及新策略字节码 hash、原策略合约链接、当前 epoch/allowed/paused；任一 RPC 不可用或不一致则 `GITHUB_POLICY_UNAVAILABLE`，不降级、不返回预置数据。链拒绝为 `GITHUB_REPOSITORY_DENIED`，代理映射 DENIED/实际执行 false；可用性失败仍 UNKNOWN。原冻结错误枚举不变。这些是新增 R0 适配器错误，不是原链状态机的新状态。

成功或拒绝外层新增 `repository_policy`：chain_id/contract/code_hash/repository/repository_hash/allowed/epoch/block_number/block_hash/checked_nodes/enforcement。原 data/source Schema、内容摘要和旧 manifest 不变；工具加密记录保存工具/读取服务两份策略检查，读取服务 `repository_policy_checks` 持久保存真实判定；拒绝前不创建 fetch 行或发 GitHub 请求，读取中撤销则保存 WITHHELD_POLICY 原件、不给调用者内容。逐读取采用 eth_call，不伪造 reserve/finalize；双签策略变更才有治理交易。来源摘要不是 GitHub 签名，也不是逐读取链上存证。

`GET /ops/v1/github-policy?resource=owner/repo%23n`：已登录，使用宿主独立 RPC 返回当前判定及 deployment_tx/governance_tx。`POST /ops/v1/tasks/{id}/github-negative-control`：requester+同源+CSRF，body 精确 tool_name/query；仅该任务已选 GitHub 工具，必须是本地未授权键或当前链上拒绝的键，不能触发一个当前已授权读取。强制走原 Agent 网关/工具并返回实际拒绝、链证据、前后 fetch 计数及 chain_enforced；人工事件为 MANUAL_GITHUB_SCOPE_PROBE，agent_attempted_tool=false、attack_success=null，不混入模型 ASR。链策略在预检后可能变化，若真实调用意外放行则结果 UNEXPECTED_RESPONSE 且不伪报阻断。

原 `/v1`、TaskGrant、ActionIntent、ExecutionReceipt、EIP-712域/顺序、参数承诺、链状态机、120秒动作期限全部不变。独立业务API前缀 `/ops/v1`；只读审计仍为 `/audit-api/v1`，进程分离。

GitHub增量（2026-10-28）：沿现有custom-tools注册/审核/任务接口增加唯一可信`github.read`适配器。注册字段形状不变，key_field固定resource，records仅为`[{"resource":"owner/repo"},{"resource":"owner/repo#1"}]`授权目录，output_fields固定适配器白名单。名称/资源/版本/风险/目录摘要/Schema都被原manifest revision覆盖；此适配器的dataset_sha256是授权目录摘要，绝不作为GitHub内容摘要。资源为小写规范形式、Issue正整数且无前导零，精确逐资源授权，不允许URL/路径/通配符或继承整仓Issue范围。原dataset.lookup manifest字节及冻结协议不变；新版本仍DRAFT重审，不赋予写权限。

Agent继续`/agent/v1/custom-tools/query`和原mTLS工具通道，参数仍只有query。工具端在联网前独立查当前ACTIVE版本、Task/Agent/期限/精确键及Schema；等待HTTPS后再查停用/期限，才释放结果并落custom_tool_reads。GitHub读取服务连接独立内部服务网、专属出口网及原QBFT网（只用公开RPC核验、不持链密钥），Agent不在新读取网络、服务无公开端口，仅有专属卷/随机内部Bearer，不挂载工具/网关/签名器卷。工具不连接新的出口网；固定POST /fetch只接受query，内部只执行证书校验的`GET https://api.github.com/repos/<owner>/<repo>[/issues/<n>]`，禁继承代理/重定向、请求5秒、原始响应1MiB、每分钟20请求。只读取公开元数据/精确Issue；无GitHub令牌、私有库、PR/附件/仓库文件或写操作。

成功返回data.record（resource/kind/repository/title/description/url/state/number/updated_at/stars/open_issues/body）和data.source（url/http_status/fetched_at_utc/response_sha256/github_request_id/api_version/rate_limit_remaining），不适用字段为空串/0；Issue正文最多4000字符。外层沿原untrusted/sha256/read_execution_id/revision。来源API版本固定2022-11-28，response_sha256覆盖真实原始HTTP响应字节，外层sha256覆盖规范化投影。读取服务专属卷保存真实raw/data/fetch_id，工具卷另加密保存查询结果和关联fetch_id；公开审计仍只发读取摘要，原文不进公开投影/链。远端内容仅tool-role，不作为审批或系统指令。

HTTP限流、404、重定向、响应过大/不匹配和真实失联均保存明确GITHUB_*错误；工具返回READ_FAILED失败分支，代理显示UNKNOWN及原错误，不伪造READ_ALLOWED或链状态、不返回预置结果。该分支仅作用于新增GitHub适配器，不增加冻结高风险错误或状态枚举。模型日志、读取日志和原始响应可离线关联复验，不重新请求动态GitHub；本机摘要关联不是GitHub签名或链上来源证明。

部署：先`update_default_tools.py --feature github --config <本地runtime> --out <新results/github目录> --apply`保留原卷/回退容器升级，再`setup_github_reader.py --config <同runtime> --out <新results/github目录>`建立读取服务；然后按原启动脚本恢复Web。读取令牌仅stdin传入两个受控卷，不在环境、浏览器或模型中。首次实际初始化早于升级完成而失败，原件reader-setup-01保留；脚本已增加创建资源前的模块检查。网络事实限制：原工具所在chainguard_qbft的Internal=false，本轮没有给工具增加出口网，但不声称网络层阻断一切外网；须进一步防火墙/节点代理评审。固定域名/GET限制在读取服务实现层，专属出口网不是域名防火墙。

导入/版本增量（2026-10-28）：`POST /ops/v1/custom-tools/import-preview`仅 requester+同源+CSRF，精确 body 为 format/content/column_types。format 为 csv/json，UTF-8 内容最大64KiB（HTTP整个JSON请求仍最大64KiB）；CSV默认string，column_types可显式指定string/integer/boolean，JSON必须为空映射且为对象数组。拒绝重复列/JSON键、混列类型、浮点/null/嵌套值、非规范整数及超限；最多200行/12列、每格500字符、结果规范化32KiB。返回 records/columns/column_types/row_count/persisted=false，不存文件、不注册、不授予权限；整行内容属于私有会话，不进公开审计。

`POST /ops/v1/custom-tools/{revision}/versions`沿原注册字段，只限 requester，强制同名且父版本是本名称最新版本，否则PARAMS_MISMATCH/STATE_CONFLICT。注册及versions可携带Bytes32 Idempotency-Key，相同请求返回同一revision，变参409；无header保留原注册兼容行为。新版本始终DRAFT，不继承ACTIVE或任务授权；旧版本字节不变，父子关系另表保存，不修改manifest/冻结协议。GET版本新增parent_revision、changes（added/removed/changed_keys及changed_fields）和history（持久事件序号、角色、UTC时间）。表单只从最新版本修改；准入仍审核新revision，停用仍不可复活。准备任务只填写最新ACTIVE版本及明确所选键，清除mail.send/发送范围、文档/邮箱授权；不会自动注册、批准或创建任务，点击创建后仍由原网关和工具验证。当前dataset.lookup仍是数据快照，实时工具接入TODO，需确定实际数据源与适配器。

自定义工具第二步（2026-10-28）：仅支持R0 `dataset.lookup`可信适配器。`POST /ops/v1/custom-tools`由requester提交name/label/description/adapter/risk/key_field/output_fields/records，精确字段集；名称限custom.<小写标识>，risk必须为整数0，最多200行/12列/规范化32KiB，行列同类型、键唯一且为字符串；字段值仅string/integer/boolean。服务端生成输入/输出Schema、dataset_sha256、递增version和revision（SHA-256覆盖完整manifest）。资料及注册事件用原业务AES-GCM存储，工具卷另加密保存。不能上传脚本、URL适配或凭据，也不能自定义R2/R3执行器。

`GET /ops/v1/custom-tools`返回各版本元数据，`GET /ops/v1/custom-tools/{revision}`在私有已登录会话返回manifest及原资料供审阅。`POST .../{revision}/activation`仅security身份，同源/CSRF，body精确为revision/enabled，必须与路径一致；工具端成功确认后才标ACTIVE/DISABLED。DRAFT→ENABLING→ACTIVE，ACTIVE/ENABLING→DISABLING→DISABLED；通信失败保留过渡状态供显式重试，不假报成功。DISABLED不可重新启用，修改/恢复须提交新版本。以上是目录调度状态，不加入冻结安全状态机；R0准入不冒充双组织ActionIntent签名。GET tools目录仅列每名称最新ACTIVE版本；旧任务仍绑定原版本，停用旧版本后不再允许新读取。

任务请求可在原五字段上新增custom_tools列表（最多8项），每项精确name/revision/allowed_keys；所选custom工具必须与此列表相等，键是该数据版本的非空子集。原幂等MAC覆盖全部范围，不能同键换版本/扩权。模型只接收任务选中的Schema。`POST /agent/v1/custom-tools/query`精确接受task_id/tool_name/revision/arguments，经当前Agent JWT、任务绑定/撤销/期限检查，转发原mTLS+Bearer工具通道。工具独立核验当前ACTIVE版本、任务/Agent/版本/键/期限及输入输出Schema，参数仅query（精确键匹配），只返回output_fields。目录预置/停用/capability授予仅可信操作员CLI，Agent无此权限；无模型侧安装接口。

工具持久化custom_tool_reads的调用ID、任务/Agent/revision、参数/结果SHA-256及时间；结果固定untrusted，正文只进tool-role及私有加密Journal。审计仅投影调用ID/revision/摘要，纯R0返回READ_ONLY_OBSERVATION，既无工具签名回执也无链上认证；混合任务的mail.send继续原精确意图双组织签名、reserve、独立二验、本地MIME和finalize。读取缓存返回原记录不代表新执行，R0读取不承诺exactly-once。

联系人/库存示例来自console/src/custom-tool-examples.json，只是注册输入模板（合成数据），不增加API或执行权限。联系人按contact_id查询本地.invalid测试邮箱；库存按sku查询整数quantity/reorder_level及仓库。模板按钮不注册、不启用、不调用Agent；提交、版本摘要、安全准入、任务键授权和实际查询仍走上述原路径。库存补货提示由模型依据真实查询结果生成，不代表库存变更或采购动作。

默认工具库增量（2026-10-28）：`GET /ops/v1/tools`需登录，返回六个启用工具的参数Schema、两份合成文档及本地邮箱目录；doc.delete显式禁用。`POST /ops/v1/tasks`保留原两字段请求，另外接受五字段请求：task_text、allowed_recipients、allowed_tools、allowed_document_ids、read_mailboxes，字段须完整、列表去重且是目录子集。只读任务allowed_recipients必须为空；涉及文档/邮箱须单独选非空资源范围。原请求幂等MAC覆盖全部选择，不能同键扩权。

工具为doc.list/search/read、mail.list/read/send；前五项只处理R0合成沙箱资料，不扩展R1/R3或外部邮件。模型仅看到所选工具Schema；DefaultToolProxy拒绝未选工具，原ToolExecutionProxy继续处理doc.read及mail.send。新增`POST /agent/v1/library`严格接受task_id/tool_name/arguments及原Agent JWT、mTLS和幂等键，检查当前角色、任务Agent绑定/撤销/期限；工具`POST /internal/v1/library`仍强制网关证书AND服务Bearer，独立检查工具/资源/期限capability。原doc.read走`/agent/v1/reads`并补查任务到期。Agent不能调用工具目录授权、签名或reserve。

为保留原ChainService的R2专用TaskGrant限制，读取许可沿用独立capability，不把新工具名称加入冻结allowed_tools枚举。只读任务的原R2授权载体allowed_recipients为空，任何真实mail.send仍由原冻结策略拒绝；capability由可信BFF按任务选择经工具操作员CLI预置，Agent不持预置凭据。单次任务最多12轮/12调用，成功读取后继续模型循环，首个高风险提议或拒绝即暂停。READ_COMPLETED只是任务调度结果，不是新的链状态。

doc.list仅列已授权实际资源；doc.search为最长200字符的字面匹配，返回有限实际片段；doc.read读取原工具文件。mail.list最多50条授权收件箱实际MIME元数据；mail.read接受1–18位十进制message_id，先过滤授权邮箱再查ID，重算MIME SHA-256。两个读取服务的结果固定untrusted，内容仅进入tool消息；文档/邮件不提升为指令。查询、内容和模型交互留加密私有Journal/业务事件；新增library_reads持久化调用ID、任务/Agent、工具、参数/结果摘要及时间，不存正文。原读取可重试，不承诺读取exactly-once。

业务页显示逐调用agent_attempted_tool/policy_verdict/tool_executed/attack_success、读取内容/结果及调度输出。审计自动投影只附read_observations的工具/执行ID/摘要，不含原文。无任何高风险意图/签名/交易的R0条目返回READ_ONLY_OBSERVATION，明确“不适用链上预约、仅本地日志观察”；有任何高风险证据仍须原四节点验证器。该标签不证明链上执行成功，读取摘要也不是工具签名回执或独立物理证明。原发送UNKNOWN/双组织审批/工具二验/nonce与actionId永久去重全部不变。

预约操作补充：双组织批准不自动执行，请求者需在120秒内审阅并点击“发起链上预约并执行”；原接口不变。动态NO_RESERVATION只新增next_step说明（COMPLETE_APPROVALS / REQUESTER_RESERVE / CREATE_NEW_TASK），不伪造链上状态或授权；过期动作不得补发。历史RPC配置与现场操作见[预约排错](history.zip)。

| 业务接口 | 权限与语义 |
|---|---|
| POST /ops/v1/login | role和password；角色限requester/biz/security，独立密码；返回HttpOnly/SameSite=Strict随机会话与CSRF，不返回链JWT/密钥 |
| GET /ops/v1/session；POST /ops/v1/logout | 会话查询/失效；会话最多3600秒，数据库仅存token SHA-256 |
| POST /ops/v1/tasks | requester；Idempotency-Key为Bytes32，body仅task_text/allowed_recipients；同键同请求返回原任务，变参409；202不代表执行成功 |
| GET /ops/v1/tasks[/{id}] | 已登录三角色；原网关record、模型/工具尝试、审批事件、只读工具观测分列，界面每2.5秒更新 |
| GET /ops/v1/tasks/{id}/review | 角色自己的可信mTLS审阅通道；返回完整原intent、params、intent_digest，不返回盐 |
| POST /ops/v1/tasks/{id}/approve | biz或security；body只有intent_digest。服务端从会话选签名器，各自重读原意图/参数承诺后核对digest；不能传role/params替换审批目标 |
| POST /ops/v1/tasks/{id}/execute | requester确认digest；请求者签原意图，原executor调用reserve。缺任一组织签名由原网关拒绝；重复只查询/返回原动作，不重新派发 |
| GET /ops/v1/tasks/{id}/mailbox | 已登录角色；独立readonly卷/SQLite mode=ro读取，验证真实MIME SHA-256、结果/证据承诺和工具签名后返回本地测试原件 |
| POST /ops/v1/tasks/{id}/negative-control | requester；空body。显式手动协议负例，不计作模型攻击；用任务范围外本地收件人调用原propose，记录真实错误 |
| POST /ops/v1/tasks/{id}/receipt-loss | requester；body hold布尔值。仅本地测试故障适配器，转发真实工具执行后丢响应并暂拒原回执查询；解除后只GET原回执，不重发 |

写操作须精确同源Origin和会话CSRF头，login只需Origin；无跨域开放；TrustedHost/CSP/no-store。密码scrypt；限速；私有任务、模型请求/响应与参数AES-GCM落盘。模型时延等私有观测元数据允许有限浮点JSON；所有原协议字段仍拒绝浮点，不经过改写的规范化器。

业务任务QUEUED/AGENT_RUNNING/NO_ACTION/MODEL_ERROR/INTERRUPTED是UI调度状态，不加入业务安全状态机。AWAITING_APPROVAL等原状态取自原加密网关；APPROVAL_EXPIRED仅为展示标签，不能延长签名或伪写链EXPIRED。进程重启不自动重调中断模型；已有动作从原网关重新载入，UNKNOWN只查原回执。Agent可连续调用已授权读取工具；首个高风险动作提议后暂停等人审，不模拟后续模型回答。

两个测试审批身份分别为OrgA_Business/BUSINESS_APPROVER、OrgB_Security/SECURITY_APPROVER，地址/组织/当前权限仍由原链核验。签名精确绑定action_id/task_id/requester/agent/tool_id/resource_scope/params_commit/policy_id/epoch/nonce/issued_at/expires_at/risk/schema_version，浏览器不接收签名私钥。分组织测试容器/卷并不代表真实组织的独立硬件托管。

动态审计服务只接收公开DB/deployment/static配置，使用SQLite mode=ro，无Docker业务bridge、模型Key、工具卷或执行路由。刷新每次读取最新自动投影；公开条目ID interactive-<业务任务随机ID>不是新actionId。失败提议没有actionId时保留null，不编造拒绝交易。原动作/审批/工具签名/交易证明复用原字段。VERIFIED来自原verify_action四节点/历史角色/调用数据/事件/nonce/工具签名核验；公开投影本身不授予执行权。历史查询失效仍UNAVAILABLE。

只读界面每3秒重新GET投影；动作/签名/交易版本改变时清除旧核验标签，必须重新查链形成新结论。投影异步更新，业务record和审计投影有短暂延迟，checked_at/updated_at与状态必须分列，测试等待真实投影收敛而不补写数据。工具回执已到但finalize尚未确认时，新观察标签PENDING_ANCHOR先复核原预约及工具签名，只声明待锚定；不加入业务状态机或伪造FINALIZED。

MIME真实副作用与链核验分列，tool_observation含检查时间/status/mail_count/receipt，公开侧不展示MIME或正文。ABSENT只表示该actionId在该次原卷查询未见邮件，不推断UNKNOWN从未执行。显式negative-control无生成动作时由原工具卷/网关无新增记录与测试前后计数佐证；固定协议探测不得计入LLM ASR。

信任限制：Windows BFF的固定Docker stdio桥是可信本机操作员控制面；它可以调度签名容器，不是面向不可信宿主的生产隔离。Agent transport仅允许原propose/get及任务绑定的reads/library读取，不提供Docker或签名操作。签名器JWT由可信控制面定期续发，单个token仍最多900秒，Agent不获得其他主体token。模型固定DeepSeek/deepseek-flash、temperature0/top_p1/thinking disabled，Key只读本地.env.local。交互配置独立于实验计划，见`config/interactive-agent.json`：普通任务max_tokens4096，带附件或输出权限的文档任务8192；实际版本/参数持久化为任务model_config，挂起恢复继续使用原参数，新消息使用当前配置。原模型响应仍加密存入MODEL_EXCHANGE。finish_reason=length整轮报MODEL_OUTPUT_TRUNCATED，该响应中的全部工具调用均不派发、不补全、不自动重试；先前已完成的调用不回滚。页面按原响应有无tool_calls区分“文字回复截断”与“工具参数所在响应截断”，缺证据则明确无法区分；历史SCHEMA_INVALID仅有原length证据才解释为截断，原状态不改。纯文字截断可在原会话继续，无需新建；不将原512历史额度显示成4096。原实验计划512及冻结协议不变。若API失败明确MODEL_ERROR，无mock兜底。

对话额度分层：max_tokens是每次模型响应的输出上限（文字与工具调用参数共用），不是整个会话总额度，也不是字符数；工具读取后再次请求模型，各次分别有此上限。网页/API单条输入最多8000字符；Runner每个任务最多12次模型响应、12次工具调用，恢复共用原计数；累计模型messages序列化JSON超过180000字符时报CONTEXT_LIMIT，不静默丢历史。模型服务自身的上下文/账户余额/速率限制仍独立存在。LOW会话凭证默认24小时/50次调用，为工具授权额度，不是文字输出额度；超时或用尽仍须显式续签，高风险仍走原逐动作双组织审批。

2026-10-28 界面重排：业务台默认对话，工具/资源授权与外部接入统一在独立“工具与设置”页，审批及原交易证据按需展开。对话仅投影原持久任务、AGENT_ATTEMPT 与 agent_output；提议时判定和当前执行状态分别标明。发送仍为原 POST 创建独立任务，不新增续聊、自动批准或执行接口；设置选择仅作用于下一任务，原任务不扩权。

2026-10-28 附件增量：`POST /ops/v1/attachments?name=<文件名>`只接受requester+同源+CSRF，Content-Type可为application/octet-stream或与扩展名匹配的浏览器MIME（PDF为application/pdf，DOC/DOCX/TXT/MD对应各自类型），Bytes32 Idempotency-Key。流式5MiB上限；返回随机id/name/extension/size/sha256/created；同键同文件返回原件，变参409。只支持doc/docx/pdf/txt/md；禁止路径名、宏/嵌入对象/外链DOCX、加密PDF、表单及无文字扫描件；不执行原文。zip展开≤25MiB/1000条，≤50PDF页、≤8万文字，所有解析/转换在非root、无网络、无主机挂载、只读根、有CPU/内存/进程/时限的容器中完成。DOC经容器LibreOffice转换读取；不调用桌面Office。

创建任务可附加`document_scope={attachment_ids:[Bytes32],allow_create:boolean}`，最多4件，准确绑定该持久请求；不改变原TaskGrant/ActionIntent/EIP-712或原三合约。新增工具`attachment.read(source_id,start,limit)`返回真实page/paragraph/line单元、原件摘要、next_start；`document.create(title,format,content)`与`document.revise(source_id,title,format,find,replace)`仅在allow_create=true时允许生成docx/pdf新副本，不覆盖文件、发信或访问路径。原件/输出均在业务私有AES-GCM数据库，100MiB总配额；原文件不接触主机路径。工具模块与容器各自核验工具/源ID/期限/输出权限；每task_id+call_id的MAC绑定完整参数，SQLite事务保存原输出，同调用不重复生成，改参冲突；最多12次文档调用。源读取仍为untrusted tool-role，不得提升权限；模型仅有提议接口，不持Docker或密钥。

`GET /ops/v1/tasks/{id}/documents/{file_id}`须已登录且文件属于该任务附件/产物，强制attachment下载+no-store/nosniff及X-Document-SHA256；返回真实文件字节。任务detail.documents分attachments/artifacts，包含SHA-256及修改限制，持久模型/文档调用记录保留在原私有事件；公开审计只投影摘要/执行ID。DOCUMENT_COMPLETED/DOCUMENT_CREATED只是文档调度与判定，LOCAL_DOCUMENT_OBSERVATION明确本地文件观察且无链结论；含原高风险证据的记录仍由原验证器处理。文档副本是受限R1本地输出，不要求邮件双签；原R2路径及UNKNOWN保持不变。

DOCX精确替换正文/表格内文字，未变内容保留，变化段落重建文字run；PDF修订为重新排版的文字副本，不承诺原图片/版式/表单/数字签名，Word到PDF同理。非文字扫描件报DOCUMENT_OCR_REQUIRED；加密/表单报明确错误；不支持OCR/复杂排版保真/原件覆盖/邮件附件/历史任务续聊。临时未挂任务的上传占用配额，暂未提供物理清理接口；不擅删原数据。宿主BFF仍是可信控制面，非生产多租户身份隔离。
# 连续对话增量（2026-10-29）

旧会话恢复/LOW续期增量：`POST /ops/v1/tasks/{id}/conversation`以legacy映射幂等引用原任务，不改原job/意图/签名。`GET /ops/v1/conversations/{sid}`增加可展示messages、authorization及blocking_run；历史原tool-role/已返回assistant和失败控制观察用于模型记忆，不补造未返回的推理或工具结果。messages仍使用原message_id/text/expected_version；同ID已受理先返回原结果。新消息进队前校验owner/生命周期/版本/阻塞及两门当前LOW签名/准入/期限/额度，过期409/AUTH_EXPIRED、耗尽409/AUTH_EXHAUSTED，均accepted=false且不创建run；登录失效仍401/AUTH_REQUIRED。无LOW范围不强制无用途凭证。

`POST .../{sid}/grant`保留duration_seconds/max_calls（60–86400秒、1–10000次），增加expected_grant_digest和Idempotency-Key；使用原ConversationGrant类型/域，绑定原session及精确LOW scopes，新nonce/时间。续签请求、待签消息及签名加密持久化，双门install/activate成功才发布ACTIVE；CAS拒绝旧摘要，半途失败恢复同一签名/nonce。Prefer: respond-async用既有operations轮询，202不是授权完成；只有固定request_id的纯续签控制允许崩溃后继续，执行类RUNNING仍UNKNOWN不重派。旧task binding、旧额度和ActionIntent均不续期。前端保留未受理草稿/原message_id，仅在当前窗口/原版本/ACTIVE且无阻塞时重提；切窗不误发。

AWAITING_APPROVAL/AWAITING_TOOL_APPROVAL、UNKNOWN、INTERRUPTED分别显示阻塞原因；等待原双审/确认/真实finalize，不靠清状态恢复。LOW新日志schema=3增加被Merkle承诺的grant_digest，旧schema=2继续验证；authorization_epochs保存起止序号，续期不重置session/sequence，也不closed=true。发布者先补原pending raw，再按续期边界构造旧周期closed=false累计前缀根，随后新周期沿previousRoot继续；无调用周期不多发交易。HIGH仍逐动作原双组织审批/预约/工具二验/回执，不加入LOW根。原合约ABI、签名向量与21+8冻结规范不变。

业务传输错误增量（2026-10-29）：`/ops/v1`在可信Docker桥命令失败、超时或进程不可用时返回HTTP 503、`error.code=BACKEND_UNAVAILABLE`；真实链RPC/健康核验失败仍为503、`CHAIN_UNAVAILABLE`。两者均不是执行终态或未执行证明；UNKNOWN保持原记录查询，不重派。原冻结`/v1`错误表不变。客户端复用只复用传输对象，不缓存RPC数据、授权或验证结论。

`/ops/v1/conversations`是新增业务编排接口；登录cookie session与业务`session_id`分开。浏览器生成随机bytes32会话ID；服务端固定owner/组织，ID本身不授予权限。旧任务不自动合并。创建绑定原任务工具/资源/附件授权，后续消息只提交`message_id,text,expected_version`；同message_id同正文幂等，变更拒绝，一个会话只允许一个活动运行。各轮保留独立原TaskGrant与max_actions=1。

新增GET/POST `/ops/v1/conversations`、GET `/{session_id}`、POST `/{session_id}/messages`、POST `/{session_id}/grant`（明确续签选项，只在无活动运行时）、POST `/{session_id}/close`。请求者写接口仍要求同源、cookie、CSRF；两测试审批身份沿原tasks/{id}/approve/execute。会话工具范围不随设置页变更；改变范围需要新会话。明确续签只影响下一轮的新task binding，旧nonce、计数和调用保持。

Runner加密快照保存已返回的role消息、完整assistant tool_calls批次、游标、预算与结果；不保存模型未返回的内部推理。模型/工具结果不提升为system指令。会话记忆上限180000 JSON字符，超限显式CONTEXT_LIMIT，无自动丢历史。模型请求中断不盲重试；工具边界按原持久call/action ID恢复。数据库CAS/租约阻止重复调度，工具自己的永久幂等仍是副作用边界。快照不投影到任务API。

HIGH邮件沿原独立双组织精确签名→请求者确认→reserve→工具二验→签名回执→finalize。挂起不是执行成功；只有原四节点交易/签名核验和工具卷观察通过后，将原调用结果注入一次并自动续模型。UNKNOWN只查原记录，不发新动作、不自动续模型。原120秒及原三Registry不改；超期不继承旧审批。

LOW会话签名使用独立`ChainGuard ConversationSessionRegistry` version=1域，结构`ConversationGrant(address requester,address agent,bytes32 sessionId,bytes32 toolsHash,uint64 nonce,uint64 issuedAt,uint64 expiresAt,uint32 maxCalls)`；实际类型/顺序以`spec/vectors/conversation-v2.json`为准。`ConversationBinding(sessionId,taskId,grantDigest,expiresAt)`由OrgA独立签名，防新轮task从其他会话偷用额度；`ConversationClose(sessionId,grantDigest,closedAt)`关闭两门新调用。新类型不替换原task-bound SessionGrant或原ActionIntent。整数使用安全JSON整数，nonce≤2^53−1，nonce与maxCalls含义分开。

toolsHash是JCS/keccak承诺的有序scopes：name/revision/allowed_keys/generation。仅OrgB链上审核为LOW的默认doc.list/search/read、mail.list/read及自定义查询适配器纳入。网关/工具独立验证当前链身份/准入代数、签名、session/task/Agent/资源、期限和持久调用配额；先原子扣额及STARTED再派发，丢响应UNKNOWN不重发。过期/额度耗尽转原精确调用双组织审批，不自动续签。旧read端点对绑定会话task拒绝绕过。附件读取/生成仍属原无网络文档沙箱capability路径，其上下文和事件关联会话，但未冒充新链上LOW凭证或R2认证。

LOW日志schema=2，显式session_id、会话内sequence、call/task/Agent/tool/revision、加盐参数/结果哈希、时间和结果。盐和原始结果加密留各门数据库。新会话根按累计前缀构造（0x00叶/0x01父，有序，奇数复制末叶），每300秒/50条或关闭触发；不同会话不混根，HIGH邮件不入根。链上checkpoint绑定session/index/root/count/previousRoot/closed，历史根不可覆盖。关闭先禁止新调用；存在STARTED且尚无结果日志的LOW调用时，已完成前缀只可提交closed=false，不能封存最终根。结果或明确UNKNOWN观察落库后才能纳入最终前缀；pending_calls展示尚未归档调用，不能伪造完成。独立发布账户与持久raw outbox恢复相同交易字节。零LOW调用会话无需交易。审计必须核对明确leaf_index、session、sequence、count、完整路径与四节点交易/calldata/合约状态；BATCH_VERIFIED只证明包含性，不证明外部工具诚实或HIGH副作用。


## 会话隐藏与异步控制（2026-10-29）

`DELETE /ops/v1/conversations/{id}`及旧`DELETE /ops/v1/tasks/{id}`要求请求者/同源/CSRF，仅幂等设置hidden_items.is_hidden=true并返回`{id,is_hidden:true}`。旧任务若属于会话则隐藏整个会话；私有消息、调度状态、审批、原交易及公开审计不删除。审批者列表/后台worker不按请求者隐藏过滤；隐藏不等于撤销授权、结束会话或取消在途动作。网页成功后移除列表，无额外确认。

审批、执行、工具准入、LOW批次提交、会话关闭/续签的网页POST携带`Prefer: respond-async`和Bytes32 Idempotency-Key，返回202及`{operation_id,status,stage,tx_hash,...}`；`GET /ops/v1/operations/{id}`仅原身份查询持久结果/性能。status=PENDING表示排队或处理中；SUCCEEDED仅控制调用成功，HIGH结果仍看原ActionRecord和真实receipt。未广播时tx_hash=null，后续从原outbox读取实际reserve哈希。队列重启遇RUNNING转UNKNOWN，不自动重派。无Prefer旧接口和冻结/v1保持兼容。

只读`GET /audit-api/v1/actions/{id}/verify`带同一Prefer头返回202及verification_id，轮询`GET /audit-api/v1/verifications/{id}`直至COMPLETED/result；核验任务只存在内存，重启后可重新发起只读核验。列表/详情查询只读SQLite，不触发逐动作RPC；网络健康按钮和实时核验可查真实链。事件监听独立于业务线程，验证四节点区块/日志一致后原子保存日志及游标，历史追赶不阻塞业务。缓存不作为新授权凭据。性能JSON日志与持久指标不含参数、密钥或令牌；广播到四节点receipt核验含RPC/轮询/调度延迟，非纯共识计时。

## 24小时审批与执行窗口（2026-10-29，用户明确授权）

本节取代本文此前“新邮件仍120秒”和“精确工具审批300秒”的当前配置描述；历史记录/实验及冻结原文件不重写。

- 新TaskGrant.expires_at为创建时间+86400秒，原max_actions=1、允许工具/收件人/组织/风险和撤销规则不变。ActionIntent.issued_at仍为实际提议时间，expires_at=min(issued_at+86400、issued_at+链规则maxLifetime、TaskGrant.expires_at)。因此模型耗时消耗同一任务窗口；不是每审批一次重新计24小时，也不是执行后24小时。
- 默认工具库DefaultLibrary新读取凭证同样允许最多86400秒，编排层继续使用本轮TaskGrant的原expires_at，不重置或续期。工具端仍复核操作员、task/Agent、工具与资源范围以及到期时间；相同task/Agent不能改期限或扩权。工具端授权安装的过期值报RESERVATION_EXPIRED，超过24小时报READ_CAPABILITY_WINDOW_INVALID，类型错误报SCHEMA_INVALID；后两者只属增量本地安装接口，不改冻结/v1错误规范。既有1小时凭证不延长；旧ReadBroker独立grant仍保持1小时，DefaultLibrary生成的doc.read凭证按其已验证期限在ReadBroker.read执行时复核。会话LOW签名及调用配额仍独立核验。
- 原PolicyRegistry不可升级且限制120秒。独立MailApprovalWindowPolicy构造使用`ChainGuard MailApprovalWindowPolicy`/version=1/实际chainId/预测新地址域，签名结构`MailApprovalWindow(address sourcePolicy,uint64 mailLifetime,uint64 nonce,uint64 issuedAt,uint64 expiresAt)`。精确mailLifetime=86400，两名当前不同组织GOVERNANCE_ADMIN签名；部署授权自身过期最多24小时。只将原启用R2 mail.send/ORG_A_INTERNAL_MAIL规则的maxLifetime=120映射为86400；旧治理收紧到小于120时按原值、禁用/epoch/角色撤销/暂停实时委托原策略。STATICCALL转发只读查询，不能透过适配器修改源治理。R3仍60秒，未开放R3。
- 使用原字节码部署新ExecutionRegistry/AuditRegistry固定互链；ActionIntent/ExecutionReceipt类型、字段顺序与domain.name/version完全不变，verifyingContract采用新地址，所以旧签名不能用于新部署。两个组织仍签同一意图，reserve、工具独立二验、参数承诺、永久幂等、nonce、UNKNOWN/回执恢复规则全部保留。
- 网关与工具使用同一个可信mailApprovalWindow配置，固定源策略/新字节码，并在链健康检查核对sourcePolicy与mailLifetime。缺该配置的旧部署本地上限仍120秒，不会因换程序获得24小时。LOW工具准入/会话/根仍链接原策略，未迁移。
- 新建精确ToolUseApproval过期改为生成时间+86400；结构不变，原task/capability仍独立过期核验。已有pending调用保存原expiresAt，重复访问、续聊、重启均不延长。LOW会话预授权的用户自选期限和调用配额不自动改变。
- deployment.legacyDeployments只接受可信本机配置，历史审计按reservation_evidence.registry选择准确原部署，四节点/原签名/nonce/工具回执检查不减少；未知registry拒绝。工具MIME观察只尝试固定可信回执域且必须唯一恢复原tool_signer。历史未预约动作与旧任务不延长、不重签、不自动重跑。
- 部署/回退配置只在忽略目录及私有Docker卷保存。setup_mail_window.py先检查无在途HIGH/未过期审批，保留旧链/卷及配置，然后部署3份实例、复核四receipt、停gateway/tool切换domain、恢复服务；部分切换失败保持关闭并报告人工恢复，不盲目重部署。

现场新地址、真实等待超过120秒后执行及回归命令，以`results/lifetime/20261029-24h-01/summary.json`及同目录deployment-01/setup.json为准。复现真实延迟验收：`.venv/Scripts/python.exe scripts/check_mail_window.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/lifetime/<新目录>`，会真实等待125秒并向本地沙箱发送1封合成MIME，无模型调用。
