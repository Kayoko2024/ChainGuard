# ChainGuard 架构与边界

2026-10-29旧会话续接/续期：legacy job保持原件，仅新增稳定session映射；失败观察与实际role持久用于后续模型。消息进队前双门实时校验LOW凭证，过期返回AUTH_EXPIRED且不受理；OrgA显式续签经持久nonce/签名、CAS及两门激活后，前端在原窗口重提原未受理message_id。schema3日志绑定grant_digest，授权周期沿累计LOW根继续；HIGH双审/逐动作交易及UNKNOWN不重发规则不改。真实验收和运行版本见progress/handoff。

2026-10-29交互性能维护：hidden_items只控制请求者列表可见性，不删除会话/任务/签名/审计。网页控制请求进入持久队列，实时核验由独立只读线程池运行；业务投影与四节点事件补读分线程，本地SQLite缓存不授予执行权。事件及游标四节点一致后原子落库；新授权仍实时查链。现有QBFT为2秒，节点资源和实测见progress/handoff。

2026-10-29可用性维护：RPC复用进程级无代理HTTP客户端，链状态与授权每次仍实时读取；网关资源有限并自动重启。业务桥失联与链核验失败分别为BACKEND_UNAVAILABLE/CHAIN_UNAVAILABLE，不改变原安全判定或UNKNOWN恢复规则。当前镜像与验证见progress/handoff。

2026-10-29邮件期限增量：用户明确要求审批/执行24小时。原PolicyRegistry与LOW治理继续保留；新MailApprovalWindowPolicy经原两组织管理员绑定新域双签启用，只把R2邮件120秒上限提升为86400秒，实时委托原身份/角色/撤销/暂停。原ExecutionRegistry/AuditRegistry字节码新部署并固定链接；旧部署按原域只读核验，不延长旧签名。新TaskGrant为24小时，动作截止取链规则、24小时和任务截止的最小值。详见phase10-contracts末节及progress最新记录。

连续对话增量：业务session_id关联独立逐轮TaskGrant、加密role历史及Runner工具批次断点；HIGH完成原链/工具核验后自动续模型，UNKNOWN只查询。默认LOW与自定义查询通过独立ConversationGrant/两门持久配额，按会话累计前缀根存证；旧任务/旧Grant保持兼容。附件上下文可跨轮保留，原文档沙箱权限及本地观察不改，尚未纳入链LOW凭证。当前上线与真实验收进度见progress/handoff最新条目。

当前是阶段10本地R2邮件原型，并已增加默认沙箱工具库；技术证据与用户验收状态见progress.md。网页能选择工具/资源、创建任务，使用真实DeepSeek、原安全网关、独立测试审批身份和四Besu；不依赖历史证据导出。

自定义查询新增OrgB链上LOW/HIGH审核、OrgA任务EIP-712会话、网关与工具各自持久nonce/配额。LOW每次只读链检查，不逐次发交易；HIGH或会话过期/超额需精确调用双组织审批。执行日志先持久化，每300秒/50条Merkle打包，由专用发布账户锚定；业务台显示待存证/真实交易，GET-only审计进程独立用四节点receipt和Merkle路径验证。敏感写行为仍只能走原R2/R3协议，现有通用HTTP并未获得任意写权限。

| 层 | 实际职责与入口 |
|---|---|
| 业务台8090 | 对话主界面 + 独立工具设置页；console + phase10_api/service/store；任务工具/资源授权、真实模型多轮读取、首个高风险动作暂停人审、确认执行；私有数据加密持久化 |
| 模型与代理 | AgentRunner + ToolExecutionProxy；模型仅提出动作，不持审批/工具/relayer私钥 |
| 任务与策略 | 原TaskGrant、policy/approvals；任务范围/风险/期限/配额；B/C共用冻结策略 |
| 跨组织审批 | OrgA业务和OrgB安全签同一ActionIntent；服务端测试签名容器，当前角色/组织/范围必需 |
| C执行 | chain_service/store；真实reserve确认、持久幂等与原交易恢复；工具端节点2/4独立核验 |
| 沙箱工具 | ChainMailTool；重算参数承诺、核验当前链授权与TaskGrant，原子本地SQLite邮件和签名回执 |
| 默认读取库 | DefaultLibrary + 原ReadBroker；doc.list/search/read、mail.list/read；工具端独立任务/Agent/资源/期限capability，真实文件与MIME，读取日志摘要持久化；无外部网络或主机路径 |
| 对话附件与文档 | DocumentLibrary + 独立不可变镜像；DOC/DOCX/文字PDF/TXT/MD上传、定位读取、生成/精确替换为新docx/pdf副本；任务固定源ID/输出权限，容器复核范围/期限/摘要，无网络/主机挂载/凭据；原件及产物加密持久化、按任务下载，非链认证 |
| 自定义读取库 | ToolRegistry + CustomLibrary；dataset.lookup版本快照、github.read与http.request实时请求；安全身份按revision准入，任务精确选键，工具独立复核启用/版本/范围/期限，资料和结果加密；不接收脚本或模型临时指定URL |
| 通用HTTP服务 | 独立非root/只读根容器、专属卷/内部Bearer/无公开端口，无链/模型/邮件密钥；仅已审核R1 HTTPS GET/POST请求配置，DNS全部公网并固定IP/TLS主机、禁重定向/代理/GitHub治理绕行；持久STARTED及加密响应，UNKNOWN不重发；非链认证 |
| GitHub读取服务 | 独立非root/只读根容器，专属卷与内部Bearer，无链/邮件/模型密钥、无公开端口；精确公开repo/Issue，固定HTTPS GET；工具node2/4和服务node1/3分别查独立RepositoryReadPolicy，HTTPS前及释放前强制核验，原始响应/策略证据持久保存 |
| 合约 | PolicyRegistry、ExecutionRegistry、AuditRegistry；治理、nonce/预约、finalize/reconcile |
| 动态审计8091 | phase10_audit + dashboard；只有GET和公开DB，只读四节点核验，无业务bridge或私有工具卷 |
| A/B对照 | central_service/central_adapter；A账号授权及任务策略shadow，B强制任务授权、独立签名、工具二验和签名追加审计 |
| 实验 | evaluation + run_live_agent/verify_live_agent；真实模型与协议轨分开，按计划重复，原卷/真实receipt与统计独立复验 |

完整路径：任务授权 → 模型提议 → 精确意图双组织审批 → 请求者确认 → 链上预约 → 工具独立二验 → 一次性本地副作用 → 工具签名回执 → 链上审计确认。审批不自动发送；终态必须有真实链及原工具证据。UNKNOWN只查原记录/回执，不盲目重发。

自定义工具管理支持CSV/JSON私有预览、不可变父子版本/差异/事件历史，以及选精确版本和记录键准备只读任务。预览不持久化，新版本不继承准入或任务权限；dataset.lookup查询导入快照，github.read经原网关及工具二验访问真实GitHub公开API。返回内容固定为不可信tool-role，既不形成链认证也不提升执行权。

新增读取服务位于独立内部服务网和专属出口网，Agent不接入该网络、工具不接入新出口网。实际核验发现原工具所连chainguard_qbft网络Internal=false，因此不宣称网络层完全阻断工具外网；固定GitHub域名/GET属于读取服务实现约束，尚非域名防火墙。本轮没有扩展现有邮件执行权限或连接新的工具默认出口。

链ID=20261026，四RPC8545–8548。节点为4个真实Besu25.10.0 JVM、不同身份及卷，同属一台WSL宿主；不声称四家机构独立运维。部署及链地址以原phase5公开report与接口文档为准。原8080是阶段9快照，现场新增记录使用8091。

可信Windows BFF是本机Docker操作员控制面，两测试组织的密钥分卷但仍同机。浏览器只有会话，Agent只走提议/查询；模型Key在Git忽略的.env.local，私钥在忽略目录和私有卷。审计进程不能批准或执行。敏感副作用只在受限本地容器，不外发邮件、不操作真实主机文件。

一次性工具副作用限定共享持久幂等存储。2026-10-28新对照已实测：同一有效预约被同时投递给两份独立工具数据库时，B/C均可各发一封，C只锚定其中一份回执；不能由单个FINALIZED_OK推定没有第二副作用。全局预约去重与工具执行去重是不同保证，原协议未因本轮实验修改，证据与适用拓扑见evaluation/README.md。

冻结入口见 [contracts.md](contracts.md)。原21份协议与8份共享策略输入只检查，不重冻；原三合约及执行权限不因实验/页面而放宽。链上只保存元数据和承诺，不存邮件原文或盐。

研究边界：真实模型越权尝试、网关拒绝、实际副作用和ASR分别统计。摘要和路由开发探测不混算；原AgentDojo判定器未改，完整官方任务仍不兼容。其他C工具/R3、外部SMTP、生产HSM/RPC准入、空白机器完整部署未完成。

[现场操作](judge-walkthrough.md)、[当前进度](progress.md)、[交接](handoff.md)、[实验说明](../evaluation/README.md)是日常入口。阶段历史叙述收敛至history.zip，逐文件摘要在history-index.json；原测试数据和失败证据仍留在results中。
