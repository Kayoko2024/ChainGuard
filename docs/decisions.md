# ChainGuard 决策记录

- D077（2026-10-29，普通回复额度与截断分流）：用户授权普通交互上限512提升4096，附件/文档8192及实验512不变。配置版本和实际参数按任务持久化；新消息取新版本，旧挂起恢复保留原参数，历史额度按原请求展示。前端按原length与tool_calls区分纯文字/工具响应/证据不足，不重写原失败；纯文字允许原会话明确继续，工具响应仍整批阻止派发、不补全、不自动重放。HTTP/前端/真实历史页面及只读原件摘要证据见progress/handoff；本轮无新DeepSeek运行或安全协议变更。

- D076（2026-10-29，网站实页视觉重绘）：实际观察StyleKit完整Paper Craft showcase后，以大字双色/白纸/原创本地CSS-SVG拼贴重构展示。装饰与真实证据分离，LOW/HIGH原协议及审计只读边界不改；不引入外链字体或运行素材依赖。展示测试基于原任务/原MIME及四节点receipt，不生成新模型/业务样本；私有截图以结果父目录隔离。

- D075（2026-10-29，Paper Craft显示改版）：依据用户风格附件统一共享主题及业务/只读审计页；彩纸层仅装饰、状态仍来自原持久记录与实际核验。保留主对话/历史滚动/紧凑附件/工具设置与全部权限，不因视觉减少OrgA/OrgB或链/工具二验。真实Edge只读核验旧MIME及四节点receipt，不产生新业务或实验样本；结果入口见progress/handoff。

- D074（2026-10-29，C/B贡献补验）：按原bc_live_plan检验治理根、分裂状态和公共证据可得性，必须保留共享强事务B、完整签名日志B+log附加对照及C双工具库重复反例，区分当前实现差异与区块链必需性。独立新部署原三合约仅继承链身份，不能复制线上24h profile或历史签名域到新地址；修复仅限实验夹具，不改线上安全校验/原期限。真实运行、首轮失败、强对照、成本及未测完整B+见本轮报告与progress/handoff。

- D073（2026-10-29，A/B/C重新实跑）：原固定任务、摘要、目录注入开发探测和协议轨使用原计划各自重跑并分别统计，前置与只读复核不新增对照样本。模型核验器允许操作员显式指定完整内容ID的非root只读观察镜像，默认不自动降级；仍以原容器/原卷身份、真实四链/签名及统计为依据，报告分别披露执行镜像和观察镜像，不改原manifest。原执行镜像缺失不能宣称已恢复。旧实验清理保留回归/部署依赖，归档验证后删除散文件被自动审批检查拒绝，原文件保留，不更换工具绕过。具体新运行、测试与限制见progress/handoff及本轮报告。

- D072（2026-10-29，用户确认旧会话恢复/LOW续期方案）：legacy job通过独立幂等映射引用，不重写原任务或继承旧动作审批；模型上下文只用已保存role/真实观察，失败保留且不重派。新消息受理前两门实时预检，AUTH_EXPIRED/AUTH_EXHAUSTED以409/accepted=false区别401登录失效；显式续签原ConversationGrant域，签名/nonce先持久化、CAS及双门激活后才发布，原message_id仅重提未受理请求。旧task binding/配额不改；HIGH忙碌/UNKNOWN不续签或清状态，完成原证据后续模型。LOW schema3以Merkle承诺grant_digest，兼容schema2；授权周期分界不重置累计sequence或关闭session，pending交易先恢复。六原卷/冻结21+8/原邮件协议和合约保留，真实单封MIME/双周期根/四节点及当前限制见progress/handoff。

- D071（2026-10-29，24h读取凭证修复）：原业务TaskGrant和期限制定单测已为24h，实际DefaultLibrary.grant漏改且仍只收1h，导致新任务在模型启动前被误报RESERVATION_EXPIRED。本轮只将该任务绑定默认库上限对齐86400秒，不改原邮件/会话签名结构、HIGH双审/预约/二验/回执。旧凭证不延长、同task/Agent不能改期限/范围，过期仍拒绝；本地安装区分过期、超过上限和类型错误。旧ReadBroker独立grant的1h不改。回归必须触达实际工具校验器与受限容器真实文件读取，不能仅用忽略期限的Bridge夹具；现场新会话及旧失败记录不重试的证据见progress/handoff。

- D070（2026-10-29，会话隐藏及异步性能）：统一DELETE仅更新hidden_items；请求者列表过滤，审批者、worker和审计保留原件。网页通过Prefer: respond-async提交持久控制任务/只读核验，202/PENDING是控制面受理，广播前tx_hash=null，原/v1和无Prefer兼容调用保持。控制队列RUNNING重启转UNKNOWN，不自动重派。审计列表只读本地投影，独立事件线程按四节点eth_getLogs/区块一致原子保存事件与游标，并补读已知历史receipt；AuditRPC只增加只读eth_getLogs，写RPC仍拒绝。原签名/双审/工具二验不变。原QBFT已2秒，保留创世配置；实测原JVM超过512MiB，采用1GiB容器/512MiB堆而非512MiB硬限。性能记录区分HTTP/存储/排队与广播至四节点回执核验的观测间隔，不把后者冒充纯共识耗时。

- D069（2026-10-29，反复CHAIN_UNAVAILABLE修复）：原网关真实OOM退出与RPC opener/TLS上下文循环引用导致的原生内存增长分别有Docker和400次核验证据。仅复用无代理传输，不缓存链状态/授权或放宽新鲜度；受限资源与unless-stopped用于服务恢复，不授予UNKNOWN重发权。业务桥连接/进程失败单独BACKEND_UNAVAILABLE，/ops/v1返回503并区分链核验故障；原冻结/v1错误表和高风险链/签名协议不改。原卷/合约/历史状态保留，最新镜像与实测入口见progress/handoff。

- D068（2026-10-29，用户明确要求24小时审批/执行）：不修改原21+8冻结源、ActionIntent/ExecutionReceipt类型或原三合约源码。独立MailApprovalWindowPolicy以新域/预测合约地址绑定原治理两组织签名，在原R2规则仍为120秒时映射86400秒；原身份、角色撤销、禁用、暂停、policyEpoch和收紧到120秒以下仍即时生效。部署原Execution/Audit新实例使用该策略，旧部署保留为可信历史域，不能把旧签名迁往新域。新任务24小时，动作取min(issued+链上上限、issued+86400、任务截止)；自定义精确ToolUseApproval新建24小时，旧调用不延长。LOW原部署、会话额度与批量存证不迁移；旧实验结果不并入新配置对照。现场证据与限制见progress/handoff。

- D067（2026-10-29，会话分层，用户已授权编码）：业务session_id/消息运行/加密Runner快照独立于登录session和原TaskGrant；HIGH原双组织签名、逐动作reserve/finalize及UNKNOWN查原记录保持。LOW ConversationGrant/Binding/Close采用独立域与会话累计Merkle检查点，旧V1不改；仅模型已返回消息可快照。默认读取须显式OrgB链审核；无网络附件沙箱暂保留原capability与本地观察，不声称获得新链认证。当前实现和现场验证状态以progress/handoff最新记录为准。

- D066（2026-10-29，回复展示）：模型持久原文与前端排版分离，仅业务对话agent_output使用锁定Markdown/GFM渲染，不以删除#/*方式损坏代码或内容。跳过HTML、禁自动图片/嵌入、外链限显式无凭据HTTP(S)且隔离新页；用户输入仍普通文本。旧任务刷新即显示新排版，不重跑Agent或改写历史/执行结论，原冻结协议及审计只读边界不变。31项前端测试及真实既有回复/无新增业务写核验见results/ui/20261029-markdown-01。

- D065（2026-10-29，PDF任务真实故障修复）：读取用户实际任务的原加密事件证实attachment.read已成功，失败为后续document_create在512 token输出上限下finish_reason=length，JSON被截断。前次MIME兼容是传输改进，不能视作该任务根因。业务改用独立`config/interactive-agent.json`，文档任务8192、其余512，版本与参数存model_config；正式实验配置原字节不变。模型边界对length整轮拒绝并报MODEL_OUTPUT_TRUNCATED，不拼接JSON、不自动重试/重放，原响应与之前真实读取保留。界面据原finish_reason解释旧SCHEMA_INVALID，不改历史失败状态；任务授权、工具schema、审批/预约/签名/UNKNOWN不变。

- D064（2026-10-29，PDF上传MIME兼容）：保留原始二进制上传与所有文档安全限制，同时接受与扩展名匹配的浏览器MIME（PDF为`application/pdf`，其余类型按白名单），避免旧前端或直接客户端把合法PDF误报为`SCHEMA_INVALID`。扩展名、魔数、大小、加密/表单/OCR限制仍由DocumentLibrary和无网络容器执行；不改变attachment.read参数schema、任务授权、R2链逻辑或权限。前端发送`file.type`，无类型时回退`application/octet-stream`；测试覆盖PDF MIME成功及错配拒绝。

- D063（2026-10-28，mTLS维护）：原部署CA与所有叶证书仅2天，过期导致真实请求握手失败。按用户明确选择改为7天叶证书、365天本地CA；保留现有RSA私钥、Subject/SAN/EKU和各角色，原密钥重签后同步六卷信任证书及精确指纹。维护只停Web及gateway/tool，不重部署链、不改EIP-712或JWT期限；原件/含凭据runtime备份只存忽略目录／私有卷。默认只读检查，到期前24小时提示，实际更新需--apply且拒绝执行中动作；UNKNOWN不重派。没有自动定时续签。过期／无证书／错主机名／Agent冒用operator仍实测拒绝，四节点真实邮件闭环及原件复核通过。

- D062（2026-10-28，用户授权的会话与批量存证）：新增独立ToolAdmissionRegistry/LowRiskAuditAnchor，不修改原三合约或冻结签名。提交者不选风险，OrgB安全/本组织管理员对精确revision签ToolReview，上链记LOW/HIGH/generation，变更代际使旧授权失效。原manifest.risk保留适配器R0/R1约束，HIGH不能让查询适配器执行敏感写；mail.send仍原R2双签/reserve/二验/回执/finalize。SessionGrant绑定requester/agent/task/toolsHash/nonce/issuedAt/expiresAt/maxCalls，scopes含精确版本/资源键/代际；两独立门执行前验链/签名并在SQLite原子消耗配额、持久占用callId。过期/超额/HIGH转精确参数的不同组织双签；链不可用不放行。nonce为uint64但新增JSON限制安全整数，随机52位，原uint64十进制字符串规范不变。300秒/50条日志以域分离有序Merkle树存根，专用不可变publisher；UNKNOWN只查原调用，已签交易持久化后只恢复同字节。根确认前明确待存证，确认后只声明包含性；原始参数/结果及盐加密留本地。多副本必须共享各门的持久幂等/配额DB，不声称任意分裂数据库全局配额。审核relay的next_nonce与原签名raw/hash在同一SQLite事务分配，防多进程漏看未广播交易；只有已确认回滚才允许重新取epoch签审，pending/unknown不换字节。两独立业务进程的真实同epoch竞争与四节点receipt已验证。旧工具无自动LOW迁移，不提交Git或新增散置md。

- D061（2026-10-28，通用HTTP查询接入）：用户要求自己填API地址/Method/参数。扩展原目录而非冻结高风险协议，新增R1 http.request不可变请求profile，沿OrgB准入和Task/Agent/revision/精确键二验；独立执行服务持已审核配置，模型不能换URL或扩参。GET/POST仅查询／推理，OrgB须核实API语义，不能仅凭Method推定风险；R2/R3敏感行为仍只能走原闭环。公网DNS检查+连接IP固定、TLS、禁跳转/代理/凭据/GitHub绕行；一次请求先持久STARTED，UNKNOWN不重发。无密钥JSON API为首版，认证/浮点请求参数/二进制/未知态管理对账仍TODO；真实HTTP回显不是图片识别或链认证，不混算ASR。不新增散置md，不提交Git。

- D060（2026-10-28，对话附件与文档副本）：用户确认除读取/问答外，还需生成或修改Word/PDF。新增独立文档镜像与任务document_scope；最多4×5MiB，DOC转换/DOCX/PDF解析与作者操作都在无网络、无挂载、非root只读根容器内，模型和浏览器无Docker/链/工具密钥。正文保留untrusted tool-role；复制修改不覆盖原件，PDF明确重排文字、DOCX变化段落纯文字run。私有文件/调用结果加密，task+call MAC幂等与task下载范围；无高风险证据时只作本地文档观察，原R2双组织审批/预约/二验/签名/UNKNOWN不变。完整新网页DeepSeek实测、原件摘要及文件渲染见results/documents/20261028-attachments-02；不是ASR实验，不自动扩展OCR/复杂排版/邮件附件/历史续聊。

- D059（2026-10-28，对话主界面）：按用户要求将任务历史/对话/按需执行证据分开；默认工具、资料导入、版本注册审核和 GitHub 接入统一放入工具设置，沿原 API/范围与角色检查。仅显示原持久模型/调用记录，提议时状态不冒充最终执行；草稿跨设置页保留，每次发送仍独立建任务，不假称支持续聊。原审计只读、签名/审批/预约及 UNKNOWN 规则不变，本轮不运行新的业务任务或 LLM。

- D058（2026-10-28，GitHub首轮链上验收）：用户确认本轮新增独立仓库链策略，保留冻结协议。RepositoryReadPolicy引用原治理身份及组织去重，独立EIP-712 RepositoryRuleChange绑定仓库hash/启停/nonce/epoch/期限；不改原三合约或冒充R2 ActionIntent。仅microsoft/vscode链上启用；精确任务键与ACTIVE准入仍必需。工具node2/4、读取服务node1/3分别在HTTPS前及释放前核验，不可用UNKNOWN、不降级；链拒绝DENIED且无请求，真实模型任务与人工强制探测分别记录。正反模板刻意允许本地react键以证明独立链拒绝。R0逐次eth_call不是预约/签名结果或来源上链；治理交易有四节点receipt。部署目录必须以phase6_server.load实际根为准，禁止因路径错误放宽私有文件检查。

- D057（2026-10-28，首个真实工具）：用户选择GitHub仓库/Issue只读。沿现有custom版本审核/精确资源任务capability增加github.read可信适配器，保留dataset.lookup原manifest；新适配器的目录摘要只承诺授权资源，不承诺动态GitHub内容。经原Agent→网关→工具二验后，专属容器固定域名HTTPS GET访问公开repo/精确Issue，无GitHub密钥/写操作/私有库/任意URL；源响应保存并以fetch_id关联工具加密结果。失败明确GITHUB_*并UNKNOWN，不改冻结错误/状态。实际发现代理匿名限流而直接HTTPS200，故禁继承代理；原QBFT网络Internal=false，不能声称工具完全无外网。只增加工具内部到读取服务的网络，原工具未连接新增出口网。真实两任务/源响应/独立复核与断连负例证据见results/github/20261028-01，R0观察不冒充链认证。

- D056（2026-10-28，导入与版本管理）：CSV/JSON先在认证私有API做有界预览，CSV默认字符串保留编号，不推断数字或执行公式。新版本仅从当前最新父版本同名创建，事务内分配版本，注册幂等MAC覆盖原始输入与父revision；新版本重新准入，旧授权不迁移。父子关系和时间事件置于附加表/原加密事件，不改变manifest或冻结签名。任务快捷入口只准备明确记录键的只读授权，不自动运行模型。当前版本快照与后续实时工具集成明确分开；用户希望最终有真实工具，实际数据源尚待选择，不把样例或导入快照冒充外部接入。

- D055（2026-10-28，自定义工具第二步）：在默认库之上只开放受控R0 dataset.lookup注册，不接收可执行代码、外部地址或凭据。请求者提交不可变manifest/数据版本，OrgB安全会话核对精确revision后启用；这是R0目录准入，不是R2 ActionIntent审批或新链治理。任务及独立工具capability绑定名称/revision/记录键/Agent/期限，工具在每次实际查询重验当前启用状态与Schema；停用不可复活，修改须新版本。原TaskGrant/EIP-712及高风险双组织审批、预约和回执不改。R0只投影读取摘要，不伪装链认证。

- D054（2026-10-28，默认工具库）：用户先授权默认库，不扩展自定义注册；新增R0文档/本地邮箱读取capability和任务可选工具，保留原冻结R2授权载体与mail.send闭环。只读任务空发送范围在原网关实测拒绝直接发送；读取循环后首个高风险动作暂停人审。READ_COMPLETED与READ_ONLY_OBSERVATION分别是调度结果/只读观察，不伪造高风险状态或链认证。测试模型运行使用独立业务存储，现场用户任务不自动新增；只读浏览器验收不代替真实链与MIME证据。

录入日期：2026-10-26，Asia/Shanghai。以下是对现有规范/实现的追溯记录，未新增业务授权或重定义冻结协议。新决策应另追加编号、原因、影响、来源与验证；不抹去旧决策。

| 编号 | 已确定决策与原因 | 事实来源与影响 |
|---|---|---|
| D001 | 阶段0原21份协议文件冻结；B/C的8份规则/实现输入单独冻结，防跨模块漂移 | config/phase0-freeze.json、phase3-policy-freeze.json；正常仅检查，变更需明确审查，不能自动重冻 |
| D002 | 中央A/B与未来C共用确定性业务策略，A记录shadow判断，B强制任务权限和独立签名 | docs/phase3-design.md、policy.py/approvals.py；不弱化B制造C优势 |
| D003 | 中央API独立使用/central/v1和中央状态，冻结/v1链业务接口保持未实现 | docs/phase3-api.md、main.py；不产生伪预约、伪ExecutionReceipt或伪FINALIZED |
| D004 | 向量31337、中央B的0、实际Besu20261026分域；C还需真实合约地址 | spec/eip712.json、docs/phase3-api.md、chain/genesis-template.json；不改原向量、不复用中央签名 |
| D005 | actionId持久唯一、防重放、签名/承诺/当前权限工具重验；崩溃不明保持UNKNOWN | docs/state-machine.md、sandbox_tools/src/chainguard_sandbox/下storage.py、tools.py、central_adapter.py；跨库非原子，禁止盲目重发 |
| D006 | 敏感副作用限隔离本地工具；凭据留在可信工具/操作员一侧 | docs/phase2-design.md、sandbox_tools/README.md；无真实外部邮件或主机业务文件删除 |
| D007 | B日志为真实签名追加哈希链，需要独立保存的检查点发现合法尾部截断 | docs/phase3-api.md、audit.py；单运营方掌握所有密钥/检查点时不声称能抵抗历史重写 |
| D008 | 阶段4使用官方Besu25.10.0字节和固定摘要、四真实JVM/独立卷；同机部署仅作演示 | chain/image.lock.json、docs/phase4-runbook.md；Docker29导入ID与config摘要区别已核验，其它架构/旧Engine未验收 |
| D009 | WSL链启动维持可释放的专属隐藏会话，仅容器/tmp允许exec以加载原生库 | scripts/chain.py、chain/compose.yaml、results/phase4/failure-history.json；不改全局WSL/代理/防火墙，down保留链卷 |
| D010 | 历史验收保留，当前继续工作需重新检查源码/接口/测试和部分实现 | 用户上下文管理协议、AGENTS.md；日期分目录记录新基线，不靠口头“已完成”或压缩摘要 |
| D011 | 仓库尚无HEAD且0个跟踪文件，当前用原始文件和SHA-256清单补充核验 | results/context/2026-10-26/baseline.json；空git diff不构成未修改证明，不擅自创建初始提交 |
| D012 | 阶段5新增独立治理EIP-712结构，不改冻结ActionIntent/ExecutionReceipt；全部写变更需当前两个组织管理员，直接角色写入全部禁用，单方仅可暂停 | spec/phase5/governance.json、PolicyRegistry.sol、7项治理测试；有效治理批次提升全局epoch并永久消费nonce |
| D013 | Execution/Audit引用不可变且构造互查；用连续EOA CREATE nonce预测Audit地址，无单方初始化/更换入口 | ExecutionRegistry.sol/AuditRegistry.sol、deploy_phase5.cjs；三个真实部署receipt及代码四节点相同 |
| D014 | 预约执行审批采用不同地址角色分配搜索，业务/安全必须不同组织；scope及所有附加签名均重验 | ExecutionRegistry.sol；保持冻结B/C业务门槛，最多16份审批为明确MVP gas限制 |
| D015 | 暂停/策略撤销不阻止旧执行证据锚定；工具签名人必须当前有效；UNKNOWN只能reconcile，终态不覆盖 | AuditRegistry.sol、8项审计测试；实际receipt时间容差0秒、不增加执行到期宽限 |
| D016 | 阶段5链部署仅验证合约，REJECTED签名夹具明确无工具派发；真实C工具端/回执队列继续TODO | docs/phase5-contracts.md、results/phase5/besu-run-01；27笔真实链交易不等同27次工具动作或业务实验样本 |
| D017 | README随阶段5更新；阶段4历史源码快照/证据不重写，明确记录README预期变化 | results/phase4/source-manifest.json保留原样；阶段5完整性记录单列，不把历史快照当所有未来阶段的冻结协议 |
| D018 | 阶段6只实现R2 mail.send，复用原合约和B/C策略；工具以不同节点对独立验证真实预约、调用数据/所有签名、当前授权及参数承诺 | chain_rpc.py、chain_mail.py；冻结21+8和阶段5三个合约不改，真实run-06 |
| D019 | 本地MIME邮箱、永久claim/配额和真实签名回执同一SQLite事务提交，结果/证据独立加盐并加密 | chain_mail.py；只保证本地数据库原子性，不声称第三方SMTP exactly-once |
| D020 | 派发前持久dispatch_started但保持RESERVED；重启只转UNKNOWN查原日志；收到有效原回执后才确认工具执行转换 | chain_service.py；修复早期草稿提前标EXECUTING的语义偏差，保持冻结状态机guard |
| D021 | 交易签名字节/nonce/hash先持久化，查不到原交易且链健康/nonce未消费时只重投同字节；已知pending/receipt只查，冲突不换nonce | chain_service.py；真实run-06分别证明送达后丢响应和送达前断网跨重启恢复同hash，无二次邮件 |
| D022 | 真实mTLS证书指纹与独立服务Bearer同时强制，QA为可信本地验收签名器及故障代理，不是Agent或mock链 | chain_transport.py、phase6_lab.py；Agent token不能reserve，错证书/令牌被拒，代理仅固定内网HTTP转发 |
| D023 | 阶段7只交付固定trace/AgentDojo适配，真实模型是阶段7后续必做和阶段8前置；固定trace attack_success=null、LLM样本0 | 用户本轮明确答复；spec/agent/interfaces.json、phase7-acceptance.md |
| D024 | 所有高风险调用复用阶段6propose/GET；Agent与可信本地签名器分容器/凭据/卷；PUBLIC_DOCS读取用独立R0 capability | phase7_server/read_broker/agent lab；final-run-02真实IP隔离及权限测试，不改原TaskGrant/冻结策略 |
| D025 | AgentDojo采用官方PyPI0.1.35 wheel SHA-256及112份原文件锁，v1.2.2 workspace；判定器不改，身份映射单射到本地.invalid | evaluation锁/vendor/mapper/check；Git连接重置未虚构commit；不支持附件/CC/BCC/工具明确INCOMPATIBLE |
| D026 | LLM配置独立agent/.env.example和Backend；模型重定向禁用；非OK回执或提交后失去查询权限不能证明无副作用 | model.py/proxy.py及21项单测；175 pytest回归通过，原阶段1env加载规则不放宽 |
| D027 | 阶段8区分protocol_replay与正式LLM轨；前者只用真实原服务/沙箱/四Besu，不运行模型，ASR缺失，后者前置未完成便明确拒绝 | 用户阶段7要求仍有效；evaluation/phase8_plan.json、replay.py、run_phase8.py；不以本轮授权覆盖真实模型前置 |
| D028 | A/B/C共享相同任务/输入/身份/基础策略并配对轮换组序；A shadow原差异保留，审批/C独有故障明示适用性；UER/UBR另列shared_tool_policy相同9案例分母 | 冻结策略不改；metrics.py/verify_phase8.py拒绝失配/丢样本，避免不同分母直接比较 |
| D029 | 比例Wilson95+scenario cluster bootstrap、B/C配对差异；性能固定工作负载trial bootstrap与小样本标记；UNKNOWN保留，精确副作用判定与网关状态分开 | metrics.py自动测试、phase8-contracts.md；无总体零风险/尾延迟稳定性或模型攻击率主张 |
| D030 | 阶段8采用可信同进程服务层harness，真实磁盘/签名/RPC；不宣称Agent隔离或HTTP/mTLS/model时延；B独立checkpoint和C共同链均保留 | replay.py、phase8.Dockerfile；独立无网络readonly原工具卷mode=ro、四节点receipt/calldata和原始签名复核；不能通过削弱B制造C收益 |
| D031 | 失败运行保留，修复/统计口径更新必须新目录；已有artifact只能核验，不通过改写历史记录“通过” | run-01孤立TypeError导致FAIL，run-02独立138实际样本/93MIME/59tx复核PASS；诊断增强后未复现仍如实披露根因未定位 |

## 当前差异与冲突处理

- D037：阶段9新增独立只读公开投影/API/React，原工具卷仅由既有验证器readonly核验，审计容器不挂载私有卷、不持任何签名或LLM Key，不提供执行入口；原116源码+25个不同冻结文件摘要不变。
- D038：历史投影、当前链状态、原物理副作用及核验时间分列。旧区块eth_call不可用或验证者查询缺失必须UNAVAILABLE，不从UI推断成功；新测试进程只将缺失RPC观测变为失败，绝不补假值，核心代码不改。
- D039：clean-final为17步骤受控新源码/venv/npm/无缓存镜像重建，复用原OS/WSL/Docker/Besu/受控wheel缓存/公开卷；不声称空白机器或新创世完整部署。原失败保留，clean01缺公开catalog修复后新目录验收。
- D040：匿名Markdown/PDF报告只含合成任务/公共标签/相对证据索引，PDF Author为空；整个results/仓库/发布包可能含宿主路径，未经单独匿名审查不得视为可直接提交的匿名包。

- D032：用户已授权DeepSeek/deepseek-flash和根.env.local；真实预检05 PASS，模型AgentC前置02 PASS，再运行正式A/B/C01。密钥仅本地安全加载，模板空Key；无模拟兜底。
- D033：真实实验采用宿主模型/Runner与白名单stdio桥；工具/签名密钥留受限容器卷。作为服务层实验，不能声称替代阶段7独立容器/mTLS或机构密钥托管。所有高风险仍经原网关/原审批与C链预约/工具二验。
- D034：模型ASR按实际注入任务；UER/UBR只统计模型真实越权尝试。模型拒绝文档指令不能计入网关阻断，0越权尝试无UER/UBR分母。协议故障/伪造/重放/篡改另轨，前置和重复运行不池化。
- D035：AgentDojo原112文件/判定器保持，物理效果经只读核验后单射身份投影到官方内存环境运行原security。完整官方utility不兼容，适配目标不称排行榜得分。首轮因官方邮箱不接受.invalid身份的失败保留，修复仅限内存投影。
- D036：`run_phase8.py --track real_llm`顺序完成真实预检/C前置/模型A-B-C/协议轨；各轨独立四种输出与原卷/receipt/统计复核，顶层报告只链接不合并样本。完整一键运行未结束前不标完成。

阶段5已验证原21份/共用8份冻结文件无漂移，未发现需覆盖的冻结契约冲突。阶段4历史源码快照中的README随新阶段有明确更新，原清单保留不重生成；链配置/代码与历史证据不修改。最终摘要核验记录见results/phase5。

阶段0文档中的“设计/SPECIFIED/TODO”和阶段3文档中的“当阶段不含QBFT”描述的是其阶段边界，不能被当成当前全仓库状态。package.json的阶段1旧描述已在2026-10-27整改；默认网关health.stage=1、中央网关=3是服务功能标记。当前全项目进度以progress.md及对应实现/当轮证据核实，不修改旧冻结文本来消除这些表述差异。

原始设计文件是需求依据，其中的建议计划不自动扩大用户当前阶段指令。旧记录中的“阶段8/Agent未实现”等文字属于历史阶段边界；当前已到阶段10缺陷整改，真实模型与前端已实现，研究证据缺口见progress.md。阶段6草稿曾提前把派发记为EXECUTING，与冻结guard存在语义偏差，已按D020修复；没有覆盖原规范。历史源码快照中的README/上下文文档因阶段更新产生预期变化，旧快照仍保留。

## 阶段10追加决策（2026-10-26）

- D041：业务写入口独立为localhost `/ops/v1`，原审计实例不加写权限；动态只读源另进程/仅公开SQLite mode=ro，每次GET看到新增投影。依据用户阶段10范围，原ActionIntent/EIP-712/状态/策略/合约均不改。
- D042：复用原Runner/HTTPModelBackend/Proxy，真实DeepSeek首条工具提议后暂停，交由两组织人工审阅同一digest；签名在分组织测试容器/卷，Agent只propose/get。BFF是可信Docker操作员控制面，不能声称生产机构隔离或HSM。
- D043：业务任务、模型交互与完整参数加密存储；会话hash、同源Origin/CSRF和服务端固定角色。任务Idempotency-Key比较原请求MAC。原120秒期限不延长，中断模型不自动重跑，UNKNOWN仅查询原回执。
- D044：MIME从原工具卷readonly读取，重验真实SHA、结果/证据承诺及工具签名；链结论由原四节点verify_action产生。投影异步更新时间和核验时间分列，PENDING_ANCHOR不表示finalize。明确协议探测agent_attempted_tool=false，不算模型攻击率。
- D045：本轮恢复核验不依赖旧交接的IMPLEMENTING说法；独立新目录真实网页输入两任务、4交易/16份receipt/2邮件，重启不重调模型或多发；额外网页新任务证明无需刷新审计自动新增、单组织及越权拒绝。畸形角色/收件人先拒绝而不建会话/队列。结果与历史开发失败分别保存。

- D046（阶段10维护）：真实日志证明CHAIN_UNAVAILABLE来自Besu512历史查询限制，采用独立Compose覆盖上限1000000并保留未来trie日志，逐验证者滚动、保持原链与数据卷。原8动作本次可恢复验证；不承诺重建已缺失历史或无限归档，不改原判定器/安全协议。审批完成和请求者reserve分步明确显示，过期需新任务，绝不自动补发。

## 缺陷整改决策（2026-10-27）

- D047：实验重复实际进入调度；摘要正文由模型生成，三组共享计划和任务输入，按底层任务聚类。开发探测不混入旧正式实验，错误/未知不删除，ASR=0且越权尝试0不能当作策略拦截或C优于B的证据。
- D048：历史执行镜像缺失时，允许操作员显式指定可信只读观察镜像；仍验证原容器、原镜像ID及原卷关联，报告分别披露两镜像。观察器复核成功不等于恢复原执行环境或空白机器部署。
- D049：原21+8冻结输入保留；冗余阶段叙述逐字节归档，当前进度/交接只保留可续接状态。重复实验说明合并到evaluation/README.md；源码包保留未提交文件，不能冒充Git提交或正式许可证。
- D050：MIME的CRLF/LF与末尾换行在统计归因时按传输表示比较，原参数承诺不改。分析缺陷通过新目录重算，保存源文件及分析代码摘要，不改原模型/物理证据、不重调模型、不增加副作用；原件与派生分析只算同一批样本。

- D051（2026-10-28，界面维护）：参考Linear重组业务/审计页面，shared只负责显示，进度依据记录内签名/交易/回执是否存在，不凭FINALIZED标签生成证据；当前核验与历史状态分列。沿用原API和权限，审计不增加写入口。共用组件必须随源码包及重建复制，Vite使用各应用锁定的React；本轮只读核验现有任务，不自动创建业务任务。

- D052（2026-10-28，B/C研究）：C增量应检验跨组织治理信任根、全局状态消费和独立公共元数据恢复，而非预设ASR优于同策略B。保留原B双签/二验/检查点，B+单列。旧样本派生分析不得增加样本或把C独有故障当共同干预；回执恢复差异不直接归因区块链。原故障安全和健康检查限制如实保留，新成对实验在独立环境计划后执行。

- D053（2026-10-28，新对照实测）：按用户授权用原字节码新地址/身份/隔离卷在现有四Besu运行机制轨；最终run-02为65观测，LLM样本0。单目录根与单组织治理、存储拓扑、仅检查点与完整日志分别披露，B+log不冒充完整B+或新增样本。实测C同预约投递两份独立工具DB会产生两封邮件/两个有效签名回执但只锚定一个，故全局单副作用保证必须限定工具共享持久幂等存储；不为实验修改原协议。原run-01收尾校验失败及修复后只读复验保留，最终单命令新批次独立PASS，不合并计样本或声称统计显著/真实验证节点容错。

- D054（2026-10-29，用户确认会话分层）：业务session_id与登录cookie及逐轮TaskGrant分开；加密消息/工具批次/游标/CAS租约支持挂起恢复，只在原HIGH四链及工具证据验证后续模型，UNKNOWN不重发。LOW用独立ConversationSessionRegistry域、ConversationGrant/Binding/Close和每会话累计前缀根，不替换原签名或邮件三Registry。两门持久nonce/共用跨轮配额；关闭有无结果在途调用时不得封存最终根；包含性不代表HIGH执行。新真实19检查/协议10检查及只读原件复验见results/conversations/20261029-completion-01，不计ASR。测试签名器同机服务端托管、旧任务不合并、附件仍原本地授权均明确保留。
