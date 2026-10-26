# ChainGuard 决策记录

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

阶段0文档中的“设计/SPECIFIED/TODO”和阶段3文档中的“当阶段不含QBFT”描述的是其阶段边界，不能被当成当前全仓库状态。package.json的description仍写阶段1，仅是陈旧项目描述；默认网关health.stage=1、中央网关=3是服务功能标记。当前全项目进度以progress.md及对应实现/当轮证据核实，不修改旧冻结文本来消除这些表述差异。

原始设计文件是需求依据，其中的建议计划不自动扩大用户当前阶段指令。用户当前已授权阶段8实验/统计；过去阶段6“Agent未实现”等文字属于历史阶段边界。其他C工具、真实LLM攻防、前端与正式模型统计评测未完成，协议轨已实现且与正式LLM轨分开。阶段6草稿曾提前把派发记为EXECUTING，与冻结guard存在语义偏差，已按D020修复；没有覆盖原规范。历史源码快照中的README/上下文文档因阶段更新产生预期变化，旧快照仍保留。
