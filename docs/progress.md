# ChainGuard 当前进度

## 2026年10月30日参赛提交材料（技术整理完成，待团队审阅与签署）

用户要求按赛制及提交页交付材料，本轮仅整理提交件，不改业务/安全协议，不处理上一轮中途加工具的待办。新增scripts/prepare_competition_submission.py及tests/python/test_submission_bundle.py；两份现有进度/交接追加本节，无新增MD。交付根output/pdf/ChainGuard-submission-20261030，含设计报告21页、测试报告11页、作品报告合订32页、作品源码ZIP、作品执行文件ZIP、其他文件ZIP、240字简介、1600×900原理图与提交说明。原创声明为非官方未签署稿，不可当已签承诺上传；用户明确没有官方模板。未代签、未上传赛事网站。

本轮证据results/submission/20261030-01：基线590pytest、console48/dashboard3、Hardhat89及两build通过；新打包校验12项+仓库维护6项18PASS。源码ZIP解压后602pytest PASS；无网络/只读根/非root/无宿主目录和私有卷的镜像中，用完整开发锁离线安装后602PASS。五轨原始统计复算及313产物/21+8冻结摘要PASS，便携verify_evidence在解压源码环境重算PASS，复制322份显式公开合成证据。历史实验为2026-10-29的60模型任务/180请求、138协议观测、65机制观测；本轮不增模型/邮件/交易样本。只读四链高度152552→152554、同链20261026；不是新发送验收。

运行包包含五个Linux amd64镜像(真实docker save/load已测)、现前端dist、源码和离线开发wheel、PowerShell载入/自检/原环境恢复入口。镜像14层17648文件扫描PASS，无当前API Key、个人主目录或sandbox运行状态，不导出运行卷。模型Key/组织私钥/证书私钥/私有配置不入包，第三方许可证保留；原freeze字节不改。源码保留未提交实现，不把a5c23eb当完整版本；最终DELIVERY_MANIFEST和SHA256SUMS封存实际交付。

完整最新业务在空白机器无既有配置的一键安装仍NOT_CERTIFIED：载入镜像不等于配置了组织/链/受控卷；原业务恢复须显式本机runtime，新的genesis不能查询旧链交易。中途工具扩权未实现、独立工具DB可双副作用、同机四节点/组织、节点3重启根因未闭环、完整AgentDojo/R3/外部SMTP/生产HSM均在报告公开。未改核心、删历史、重置链或Git add/commit。

失败保留：打包首轮扫描命中本轮测试内私钥标记字面量，改为拼接测试串后通过；运行镜像首次缺openapi-spec-validator/PyYAML，补全离线wheel；二次tmpfs默认noexec阻止原生扩展，明确仅一次性workspace设exec后602PASS，网络/凭据隔离不变；海报初次Playwright解析路径失败修正；证据打包首轮误找run-02/report.md，改用实际父目录report；PDF修正文档换行/段落孤立，合订移除内部重复命名链接并保留两章书签、独立版原链接不变。原件均在本结果根，最终状态看delivery-validation.json。下一步只需团队审阅、按官方格式完成原创声明及上传；不自动继续业务开发或假称空白机全流程已验收。

## 普通回复额度与截断提示修正（2026-10-29，技术通过，待用户验收）

用户明确授权调整普通对话和区分截断类型。`config/interactive-agent.json`更新为interactive-3：新普通任务每次模型响应4096 tokens，附件/文档任务8192；实验计划仍512。`phase10_service.interactive_model_config`对挂起恢复保留原model_config，新消息采用新配置；`console/src/task-error.mjs`按原MODEL_EXCHANGE区分纯文字、含工具调用及证据不足，展示当次实际额度。纯文字提示可原会话继续，含工具调用的截断响应全部阻止派发；不补全JSON、不自动重试或重放。旧SCHEMA_INVALID/512失败原件不改。额度层次与配置入口写入既有phase10-contracts.md，未新增MD。

当轮结果根`results/maintenance/model-output-budget-20261029-02`：初验21pytest、48前端；最终`.venv/Scripts/python.exe -m pytest -q agent/tests gateway/tests/test_phase10.py gateway/tests/test_document_tools.py gateway/tests/test_conversations.py gateway/tests/test_conversation_renewal.py tests/python/test_repository_maintenance.py --junitxml=results/maintenance/model-output-budget-20261029-02/python.xml`为85 PASS；`npm.cmd --prefix console test`为48 PASS；`npm.cmd --prefix console run build`及两项冻结检查、git diff --check通过。真实本地HTTP边界测试确认4096/8192写入请求且完整长回复可返回、length工具批次不派发；这是本地测试服务，不是新DeepSeek实验。

真实Edge只读历史纯文字失败检查PASS（browser-reply、服务重启后browser-final）：旧512上限与正确提示可见，32个可见任务的原事件/回复/错误不变，仅登录POST，无任务重放。首两次双类历史页面测试FAIL，当前请求者列表仅有reply类截断，缺tool_arguments类历史案例；失败browser/browser-02保留，不填造记录，工具类覆盖依靠HTTP与前端自动测试。重建dist并重启既有8090/8091后health均alive，verify.py只读核对全部52任务/232事件原字节摘要及21+8冻结源（实际计数见verification.json），未新增模型/工具/交易。下一步用户刷新原会话继续；旧挂起任务保留原额度，不自动续跑旧失败。

## 模型长度报错原因核查（2026-10-29，仅诊断）

最新job 0x82d2b750…63319b原DeepSeek HTTP200；先完成doc.list/mail.list/custom.weather_cheak三项READ_ALLOWED，随后纯文本回复（tool_calls=[]）completion_tokens=512且finish_reason=length，触发MODEL_OUTPUT_TRUNCATED。普通交互配置max_tokens=512，附件/文档输出才用8192；本次不是工具参数JSON截断、链故障或模型上下文耗尽。统一文案提及文档/工具及“请新建任务”过于宽泛，现原会话仍可继续；未修改预算/业务/原记录或重跑模型。元数据脱敏证据results/maintenance/model-output-limit-20261029-01/diagnosis.json，model_recording专项5PASS。是否调整交互预算/分流提示待后续实现，本轮未将诊断标为修复。

## 新工具选择后发送按钮无提示修复（2026-10-29，技术通过待用户验收）

真实网页复现7项工具含custom但未选资源时按钮禁用且无原因。已在tool-selection.mjs提供逐项缺失原因，main.jsx统一按钮/快捷键/submit门槛并给新会话显示“补全授权”；新增ToolScopeNotice.jsx供输入框和ToolSettings.jsx共用，tool-settings.css保留纸艺布局，设置文案明确新会话适用。不自动勾选资源、不修改网关/签名/审批/旧会话范围。缺邮箱、文档、收件人及自定义revision/资源都保持阻止，明确补选后按钮恢复且草稿保留。

结果results/ui/tool-scope-send-20261029-01/summary.json：console基线39/最终44测试、构建PASS；默认/自定义工具、会话与仓库维护59pytest PASS；真实Edge before复现、after/final五项及原layout五项PASS，320–1440无页面溢出，缺授权快捷键不发POST，只有登录写请求，无新任务/模型/工具/交易。spec/shared-policy --check和diff检查PASS；原8090直接服务新dist，无重启。中途扩展会话权限未实现，上一轮节点重启根因仍未闭环；本轮不冒称修复链故障，不新建MD或提交Git。

## 最近会话CHAIN_UNAVAILABLE排查（2026-10-29，当前恢复，根因未闭环）

最新失败job为0xb0114f81…edf0fac，22:45:37（Asia/Shanghai）受理后保存MODEL_ERROR/CHAIN_UNAVAILABLE；TaskGrant和读取capability已安装，model_config/runner_snapshot/动作及事件均无，失败发生在模型开始前的会话初始化。节点3在22:45:44–51退出/重启并追平，时间相关但现存日志没有退出根因，OOMKilled=false且无对应OOM/JVM错误，不能断言内存或证书导致。当前四节点同链/同区块、各3peer、持续出块，完整Chain.healthy连续5次通过；另实测原requester的mTLS网关ready、原会话两门LOW预检ACTIVE（额度0/50）及四节点全校验通过。原失败不清除、不自动重跑，用户可原窗口重新明确提交；没有新任务/模型/工具/邮件/交易。未改业务源码或配置，不能标为永久修复。

证据results/maintenance/chain-unavailable-20261029-01，diagnosis/live-health/verification.json及原链日志、Docker/containerd/kernel对应时段保留。实际基线命令`.venv/Scripts/python.exe -m pytest -q gateway/tests/test_rpc_transport.py gateway/tests/test_backend_resilience.py gateway/tests/test_conversations.py gateway/tests/test_conversation_renewal.py tests/python/test_phase4_chain.py`为40通过；只读复核脚本verify.py通过。下一步若复发需捕获具体RPC/健康guard及容器退出事件，不能靠放宽四节点/授权检查掩盖故障。此前“中途勾选工具”仅草稿不扩权的行为仍未修改。

## Paper Craft网站实页重绘（2026-10-29，技术通过，待用户审阅）

用户要求实际学习StyleKit页面后重新绘制。本轮以HTTP200打开`https://www.stylekit.top/zh/styles/paper-craft`及完整showcase，检查hero、组件、层叠物理和dashboard实页/DOM样式。基于其大字双色标题、白色纸卡、彩纸拼贴与硬偏移阴影重画业务欢迎/登录、品牌导航、任务建议、工具设置及只读审计；新增本地CSS/SVG原创拼贴，不引入外链字体/图片或模型依赖。改动8份既有展示源码（shared/theme.css/ui.jsx，console的main.jsx/Conversation.jsx/ConversationNav.jsx/conversation.css/tool-settings.css，dashboard/style.css）及原浏览器测试；新增shared/paper-art.css。主对话、历史/附件、OrgB审核及原HIGH/LOW协议不改；清理418条被覆盖CSS声明，未新建MD。

验收根`results/ui/paper-craft-study-20261029-01`，summary.json索引。基线/最终console39、dashboard3，仓库维护pytest6及两build PASS；paper-craft-browser的browser-acceptance、原layout-browser的layout-final PASS（真实Edge320–1440，无横向溢出/主要文字AA、原三层插画、反向hover/reduced-motion、键盘tab、旧消息/单封MIME/工具版本抽屉/OrgB入口、审计双组织/四节点receipt）。25原任务/69审计行只读检验，0新任务/模型/副作用/交易。107核心/规范源与21+8冻结摘要不变，新增CSS已在源码重建选择中，build_specs/freeze_phase3_policy --check及git diff --check通过。

现有8090/8091已直接服务新dist，无后端重启/链重部署。仅Edge验证；本轮不是新ABC或邮件业务实验。截图/网页研究及检查原件在上述结果目录，详细私有截图见handoff；旧JSON和原协议证据不覆盖。下一步用户刷新页面审阅视觉，不推进业务阶段或Git提交。

## 前端纸艺手作风格（2026-10-29，技术通过，待用户验收）

按用户提供Paper Craft参考统一业务8090及只读审计8091：暖白纸纹、红/青/黄纸片、偏移阴影与反向展开纸层，移除暗色导航、旧紫色和发光阴影；主对话/历史滚动/紧凑附件/独立工具设置保留，正文与哈希平直排版。只改变显示样式和装饰组件，不改API、权限或执行协议。本轮11份展示文件修改：shared/theme.css、ui.jsx；console/src的Conversation.jsx、ConversationNav.jsx、ToolSettings.jsx与4份CSS；dashboard/src/main.jsx、style.css。新增console/tests/paper-craft-browser.mjs；未新增说明MD。

验收目录`results/ui/paper-craft-20261029-01`，summary.json为索引。实跑`npm.cmd --prefix console test`39通过、`npm.cmd --prefix dashboard test`3通过；两项目`npm.cmd --prefix <console|dashboard> run build`通过。`node console/tests/paper-craft-browser.mjs .local/phase10/20261026T123255815352Z/runtime.json results/ui/paper-craft-20261029-01/browser-final`及原`layout-browser.mjs`（输出layout-final）通过：320–1440宽度/无横向溢出、主要文字AA、反向纸层和reduced-motion、搜索/版本详情/OrgB审核入口、旧任务原意图及真实单封MIME核验、只读审计真实双组织和四节点receipt。26原任务/69审计行只读检查，无新增任务/模型/工具派发/交易。browser-01曾因按钮文字对比4.10失败，修深前景色后browser-02/final通过，原失败保留。

109份核心/规范摘要与原21+8冻结摘要均不变；build_specs.py及freeze_phase3_policy.py --check通过。本轮仅Edge真实页面验证，无新的ABC/邮件执行实验，其他浏览器引擎未复验。原HTTP8090/8091直接服务新dist，无需重启后端或重新部署链。下一步用户刷新网页审阅视觉；业务扩展不在本轮范围。不add/commit，未清理旧实验原件。

## 比赛报告通俗重写（2026-10-29，已生成，待用户审阅）

用户认为上一版难读，要求重新生成并使用两张配图。本轮只改报告及交接，不改业务/冻结规范。新版为六页，以“读资料→摘要→发邮件”解释授权、双审、预约、工具二验和回执；保留真实实验数字，分别说明B/C共同拦截效果、C治理/统一预约/独立查证增量，以及共享数据库B、完整签名日志B和C独立工具库双封反例。未重跑模型、工具或链写，不新增实验样本。

交付在`output/pdf/ChainGuard-competition-report-readable-20261029/`：`ChainGuard-report.pdf`、`main.tex`、`ChainGuard-LaTeX-source.zip`（含3张配图、编译说明、统计/置信区间与记录摘要索引）。两张原图保留，架构图裁剪后明确QBFT及仅LOW批量存证，流程图改为实际高风险邮件路径；原Word和上一版报告保留。

核验在`results/reports/20261029-competition-report-02/final-review-03/`。实际运行`.venv/Scripts/python.exe -m pytest -q evaluation/tests/test_metrics.py evaluation/tests/test_live_results.py evaluation/tests/test_bc_live.py evaluation/tests/test_bc_comparison.py --junitxml=results/reports/20261029-competition-report-02/final-review-03/baseline.xml`：42通过；`build_specs.py --check`、`freeze_phase3_policy.py --check`通过。`verify_report_data.py`复算五轨并核对313项manifest产物/29冻结源；TeX Live 2025 XeLaTeX实际编译6页，无溢出/缺字/未定义引用；Poppler逐页检查6页，补字体映射前后6张栅格逐像素相同，ZIP重开逐文件核对通过。首次读取发现项目venv缺文档包、bundled Python缺PyMuPDF，改用bundled文档Python和Poppler；不为报告安装业务依赖。完整命令、摘要和限制见上述目录`delivery-validation.json`及编译日志。仍是同机四节点、小样本原型，LOW成对性能、独立机构部署及完整官方基准缺口不变。未add/commit，下一步用户审阅正文与比赛格式。

## 比赛报告整合（2026-10-29，报告生成与核验，待用户审阅）

按用户提供Word保留六部分结构，整合最新三模型轨、138协议观测与65条B/C机制观测；纠正绝对可信、任意API、单节点容错、性能与删除机制的不准确表述。新增LaTeX/PDF位于output/pdf/ChainGuard-competition-report-20261029；不覆盖原Word、阶段9历史报告或实验原件，不改业务代码。

本轮42项统计/判定pytest与规范/策略检查通过；五轨重算统计及313项manifest产物摘要、21+8冻结源一致。results/phase8/report-readonly-20261029-01真实只读复验65条/71MIME/75交易/300receipt通过，含C双工具库重复反例，无新模型/邮件/交易。报告14页，含区间、交易核验与复现命令、未测项及原稿修正附录；TeX编译/中文搜索及逐页排版核验，记录见results/reports/20261029-competition-report-01。原同机/完整B+及LOW成对性能未测边界保留，不视作正式完整竞赛发布验收，不提交Git。

## 区块链增量价值补验（2026-10-29，技术通过，待用户验收）

入口results/phase8/bc-contribution-20261029-01/report.md及proof-index.json；run-02原计划65条新机制观测（31对B/C+3条C独有RPC故障）、71封原卷MIME、75交易/300四节点receipt，独立reverification通过。治理目录被单方控制时B换两审批身份后3/3发送，C单组织/重复组织6笔治理交易均回滚、0邮件；分裂本地状态B每例双封/C每例单封；缺尾记录两组皆检出，公共元数据B0/3、C3/3恢复。差异限定于当前两组的治理信任根及存储拓扑，不证明所有中央架构做不到。

强对照/反例同时保留：共享事务B/C皆单封，完整签名日志附加对照B+log3/3恢复（非完整生产副本服务）；独立工具库双投递B/C皆3/3双封，C多3份有效未锚定工具回执，不能声称全局单副作用。C配置单RPC失联仍安全拒绝，未真实停验证者。性能P50/P95/P99(ms)：B319.6/331.4/331.5，C3351.4/3663.5/3761.3，各10次；全账本/运维成本未测，完整B+及多机构故障域未完成。

21基线、30专项、587全量pytest/32.78s通过。只修evaluation/bc_live.py新合约配置隔离，并在test_bc_live.py增加线上24h/历史签名域不继承且原件不变回归。首轮run保留FAIL：新原版三合约错误沿用线上24h profile而被mail_lifetime拒绝，已部署3交易、无业务样本/邮件；修复后run-02全新身份/卷/合约，未覆盖失败。原核心源码、21+8、线上24h及原业务治理epoch6/paused=false保持；新报告说明适用边界，不重写上轮证据，无LLM/ASR样本、不提交Git、不扩展阶段。

## A/B/C 重新实跑（2026-10-29，运行通过，待用户验收）

入口 `results/phase8/abc-rerun-20261029-01/report.md`。原始模型12条、生成摘要36条、目录注入开发探测12条及协议138条均重新运行，前置C另20条不混算。三模型对照共180次真实模型请求，56封本地MIME、36交易/144四节点receipt；协议93封MIME、59交易/236receipt。原始/摘要各组ASR0/3、0/8，均没有模型越权尝试；目录探测A的UER/ASR2/2，B/C的UBR2/2、ASR0/2，TCR均2/4。样本少且目录探测含源数据污染，不声称总体零风险或C优于B。协议正常性能每组10次P50/P95/P99(ms)：A40.2/52.5/58.6，B304.5/333.8/334.3，C3401.6/4595.6/4617.6，区间及全部失败/UNKNOWN在CSV。

88基线、10观察镜像专项、最终586pytest/36.30s通过。仅改模型只读核验器及新增边界测试，支持操作员显式完整SHA-256非root观察镜像；原容器/原卷、四链、签名及统计仍强制复核。原始运行执行镜像标签被后续复用，首次收尾复验因镜像不存在失败，原件保留；后续指定观察镜像复验通过，不伪称找回原镜像、不增加执行样本。原核心源码及21+8冻结输入保持。旧实验1212文件归档核对通过，但删除散文件被自动审批检查以blocked by policy拒绝，原文件未删除，未重试；详见cleanup-result.json。原业务/链/私有卷未重建，不提交Git，不扩展阶段。

## 旧会话恢复与动态续期（2026-10-29，技术通过，待用户验收）

用户已确认上节方案并开始编码；下节“仅评估”保留为历史。本轮实现真实历史/失败上下文恢复、legacy幂等续接、LOW消息入队前双门预检、显式OrgA持久签名/CAS/双门激活、原message_id恢复、审批/UNKNOWN隔离、schema3授权周期承诺和累计前缀根，HIGH双审及原reserve/finalize不改。增量文件及现场脚本见handoff本节，不新增散置md。

results/conversations/20261029-renewal-01/summary.json为入口，resumed-live-04最终15项PASS，真实Edge+8次DeepSeek响应+四Besu：旧任务恢复、自然60秒到期不受理、显式续签24h/同message_id自动重提、两门独立授权、跨组织精确审批/真实finalize/恢复模型、非法拒绝和重复不多发均通过。原一封MIME与签名、2笔HIGH交易及两个连续LOW检查点已四节点独立核验，ASR不适用。原失败验收目录完整保留，修复的是投影等待/选择器/普通观察分类/结果汇总，始终续原动作；具体见handoff。

upgrade-02保留六原卷/回退及原链，上线conversation-renewal:0.10.12；主8090/8091已重启，main-browser-02真实只读主站通过，未导入隔离测试数据或重跑用户任务。续接32基线、19模块、576pytest/40.02s、console39/build、Hardhat89、dashboard3/build、规范/策略/归档/diff检查及21+8逐字节核验通过。复现完整新流程用scripts/check_conversation_renewal.py（原config+全新results/conversations输出；实际等待/模型/1封本地邮件），精确命令及原件位置见handoff。临时端口均已退出；用户刷新主站验收。UNKNOWN/INTERRUPTED与CLOSED安全限制保留，24h未墙钟浸泡，原HIGH协议/合约/向量不变；不提交Git、不增新阶段/散置md。

## 旧会话恢复与动态续期评估（2026-10-29，仅方案，尚未编码）

用户本轮要求先评估并提供具体修改方案。已复读约定、Git/diff、会话UI/API/加密存储、Runner快照、两门授权和累计根合约。新版成功轮已有记忆；旧独立job缺conversation_id，前端选择后发送会另建会话；失败轮仅COMPLETED才提交history；messages入队前无授权预检；现有renew只是low_grant=None、下轮延迟签发；过期LOW现走精确双审，并非AUTH_EXPIRED交互。不能将这些缺口称为已经修复。

建议最小增量：旧job幂等关联可续接会话并导入可证实历史（不迁移旧执行授权）；选择历史时单独拉详情；新消息入队前权威预检并区分业务授权过期与登录失效；显式OrgA续签原ConversationGrant，持久同一nonce/签名并确认两门安装后，使用原message_id重提尚未受理消息。待审批高亮并指向原卡片，UNKNOWN不重发，已受理/在途调用不因续签换绑定；已封存CLOSED不原地重开。续签新增本地授权周期与LOW批次边界，保持session/累计sequence/previousRoot，不关闭会话或重置旧额度；新日志须承诺grant_digest并兼容原schema=2。HIGH原双组织精确签名、reserve/二验/回执/finalize不改，无需新部署Solidity合约。详细文件/接口/验收计划见results/context/20261029-renewal-review-01/plan.json，属于待确认方案。

本轮实跑相关pytest39项/4.87s、console38项；build_specs/freeze_phase3_policy/tidy_docs检查PASS，另逐字节核验21+8冻结清单PASS。证据目录同上；仅维护本文件、handoff及JSON/测试日志，无新模型、业务任务、邮件或链交易。没有把本轮基线当作拟议功能已通过验收，不自动进入编码/提交Git。

## 默认读取24小时兼容修复（2026-10-29，技术通过，待用户验收）

用户明确授权修复RESERVATION_EXPIRED。仅DefaultLibrary期限上限对齐本轮TaskGrant的86400秒，保留所有工具端task/Agent/范围/幂等/到期校验；新增实际工具校验器边界单测与容器文件读/重启/到期/不能续期测试，原mail_window单测不再以宽松Bridge替代工具校验。前端区分超过上限与历史时间校验错误，不修改历史状态。原HIGH协议与旧ReadBroker独立1h grant不变，不涉及旧任务迁移或失败轮记忆改造。

证据入口results/maintenance/20261029-read-capability-01/summary.json；本轮baseline25、module25、完整564pytest/34.41s、console38及构建、受限容器22项、规范/策略/归档和diff检查通过。upgrade-01只替换tool容器为chainguard/read-capability:0.10.11，原卷及回退容器保留，gateway仍interactive:0.10.10，未重部署链或签名器。live-01新真实Edge/DeepSeek两轮10项PASS：实际doc.read后同会话追问、第二轮请求含原模型摘要且不再读、刷新保持、两个原TaskGrant截止与工具SQLite凭证完全一致、关闭LOW根并经四节点BATCH_VERIFIED。3次真实模型响应、0邮件/0HIGH交易、1笔LOW根交易（131638 / 0x6ca8d21dd411d67bda69db62544dcfa357407685589678295fd96efde0495e30），ASR不适用。final-check10项PASS：21+8原规范、主站8090/8091健康、六角色运行，真实工具拒绝过期/超过24h且无凭证落库，原失败任务/截止/事件保持。临时8092已停止，原失败任务不重跑。24h边界由时间推进单元/容器测试覆盖，未实等24h；本次不包含旧版任务迁移/失败轮记忆改造。复现见handoff，主站刷新后新消息使用修复版本。

## 连续任务只读诊断（2026-10-29，未修改业务代码）

补充根因定位：最新RESERVATION_EXPIRED并非用户等待到期。该轮TaskGrant=24h，Operations.grant_library直接传其截止时间，而实际部署DefaultLibrary.grant仍限制now+3600；超过上限也复用此错误码，导致模型启动前拒绝（无model_config/events/action，library_installed=false）。此前笼统解释“授权过期”不准确，应称上下游期限不一致。证据expiration-diagnosis.json保留于同诊断目录；本轮仅解释/只读核验，尚未修改该期限逻辑或重跑用户任务。

用户询问旧对话不能连续任务。实查当前可见24条legacy jobs无conversation_id，select清空当前会话、submit另建空会话，不导入旧上下文，故旧对话无缝续接未实现。当前另1条OPEN新版会话仅1轮MODEL_ERROR/RESERVATION_EXPIRED、committed history为空；失败轮未在complete中提交记忆，不能称历史上下文已恢复。新版成功轮可续聊，待审批/UNKNOWN/INTERRUPTED/关闭仍阻止追加。证据results/maintenance/20261029-continuity-review-01/review.json；本次相关单元测试5通过（pytest.xml），0模型/动作/交易，仅诊断，不为询问自动迁移数据、续授权或重发。后续若获修复授权需处理旧任务上下文继承与失败轮记忆，不能复用旧动作授权。

## 会话隐藏与异步性能维护（2026-10-29，技术通过，待用户验收）

统一DELETE仅更新hidden_items，请求者列表隐藏，闲聊/LOW/HIGH共用逻辑；原消息、任务、签名、交易、工具记录及审批者/审计查询保留。网页审批/执行用持久队列返回202，实时核验用只读线程池返回202并轮询；未广播tx_hash=null，原/v1及无Prefer兼容接口不变。列表只读本地投影；单次IPC批量快照与独立四节点日志监听分别落库，首次补读已知历史receipt，事件/游标原子保存。原双审、工具二验和UNKNOWN规则保持。

结果入口results/maintenance/20261029-softdelete-async-01/summary.json。最终550pytest/25.95s、Hardhat89、业务UI37/审计UI3及双构建、21+8冻结/规范/归档/空白检查通过。upgrade-02上线interactive:0.10.10最终源码，原六卷/回退容器保留；主8090/8091重启及真实Edge只读访问通过。四Besu逐节点应用1GiB容器/512MiB堆，实测501–536MiB，原2秒出块/身份/卷/创世保持，非512MiB容器硬限。

真实HTTP原live-01已双审、单封MIME及reserve/finalize，缺审批/越权/重复无额外副作用；提交202为4.50–15.55ms，原两交易四节点确认观测1907/2133ms。它最终因事件缓存检查失败标FAIL：AuditRPC漏只读eth_getLogs，已补白名单并保留写拒绝；resumed-live-01又因串行业务线程补读旧历史超时FAIL，修为独立事件线程后resumed-live-02为9检查及真实浏览器2检查PASS，复用原动作、0新增邮件/交易。删除无弹窗且刷新仍隐藏，审计按钮202→VERIFIED，原MIME/工具签名/四节点均有效；final-readonly再8项与主站final-browser复验PASS。原reserve区块117447、finalize117449，哈希见summary；全轮仅原1封沙箱邮件/2业务交易，无LLM，不计ASR。列表成对GET实测11.47–33.78ms。性能持久化并输出脱敏JSON日志，观测确认间隔含RPC/调度，且控制处理仍约5–11秒，不能将所有后台耗时归为纯共识。没有长期压力/OOM浸泡测试。

## 对话附件与工具管理布局（2026-10-29，技术通过，待用户验收）

本轮仅调整业务前端：附件入口、文档输出授权与文件说明收为紧凑工具栏，四附件单行横向滚动；会话授权改按需展开。工具授权改为可搜索/分类的列表，接入管理按工具名合并不可变版本，增加状态筛选及按需详情侧栏，保留 API/数据导入、新版本、任务准备与 OrgB 风险审核入口。1280×720 实测对话区233.58→350.67px，空附件区61.5→30px；320/390宽无横向溢出。未修改网关、合约或审批/执行权限。

证据入口results/ui/20261029-layout-01/summary.json。本次续接实际运行console37项、Vite构建、真实Edge只读页面5组检查、合成四长文件名组件3组检查，以及规范/策略/归档检查均通过；108份后台源码与21+8冻结输入摘要不变，无新任务/模型/工具调用。新增测试发现手机文件说明浮层x=-62越界，已修为附件容器定位，continued-before-01保留FAIL，continued-after-01通过；早期browser-after-01的歧义选择器2≠1失败也保留。全仓git diff --check仍报告本轮未改的dashboard/src/main.jsx既有CRLF行尾，本轮文件单独检查通过。8090已直接提供新dist，刷新即可；未提交Git、未新增散置md，不把布局检查当新业务闭环验收。

## CHAIN_UNAVAILABLE反复提示修复（2026-10-29，技术复核通过，待用户验收）

原网关Docker实证OOMKilled=true/137，512MiB限额且无自动重启；业务桥把docker失败也映射为CHAIN_UNAVAILABLE。根因复现为周期策略核验反复创建urllib opener及不需要的TLS上下文，当前Python运行时的循环引用使原生内存积压：400次约71→720MiB。现复用进程级无代理RPC transport，不缓存链数据或判定；部署/升级共享有限资源设置，gateway为1GiB、其他原角色512MiB并unless-stopped。桥失败单独返回BACKEND_UNAVAILABLE，/ops/v1两类暂时失败返回503，前端分别说明；原冻结/v1错误规范、链核验条件、双审、24h签名域及UNKNOWN规则不变。

已上线chainguard/resilience:0.10.9，原六卷/旧容器保留，无重置链或重放任务。证据根results/maintenance/20261029-gateway-oom-01，summary.json为入口。本次续接复核先30项相关基线，再534pytest/25.30s、console34、21+8摘要与规范/策略/归档checks通过；新memory-recheck-02在512MiB只读容器做400次真实链核验，约70.7MiB保持、RSS增长0，区块116022→116034。recheck-02/browser.json真实HTTP/网页11项PASS，原事件/交易不变；results/lifetime/20261029-oom-readonly-recheck-02/check.json四项复验原MIME/承诺/四链/工具签名PASS。0新模型/任务/邮件/业务交易。

失败保留：旧Markdown浏览器脚本未适配多轮会话，选择器匹配两条回复而失败，不是本次网关故障；独立只读网页检查已通过。该失败原件含用户回复片段，移存忽略.local/maintenance/20261029-gateway-oom-01，公开结果只留脱敏错误。一次复验命令选中已存在结果目录被保护拒绝，新目录复验通过。此处验证是短时压力/运行检查，未做24小时浸泡，不宣称永不失联。下一步用户刷新8090/8091验收；UNKNOWN仍只查询原记录，不自动补发。无新阶段、散置md或Git暂存/提交。

## 审批/执行期限24小时（2026-10-29，技术验收通过，待用户验收）

用户明确要求将审批/执行改为24小时。新TaskGrant为86400秒；邮件ActionIntent截止仍取链规则、issued_at+86400与任务截止最小值，模型耗时会消耗任务窗口。新精确自定义ToolUseApproval也为24小时。旧任务/动作/签名不延长，LOW会话自选期限和配额不自动续签，R3未扩展。

新增MailApprovalWindowPolicy由原治理两组织在新域双签构造，仅映射原R2邮件120→86400；身份/撤销/暂停/epoch及收紧规则实时委托原PolicyRegistry。原Execution/Audit字节码新部署，原三合约源码和21+8冻结输入逐字节不变；原LOW部署继续使用，旧HIGH记录按可信legacyDeployments和预约registry核验。网关/工具/签名器配置同步、六原卷及回退容器保留，8090/8091已重启，页面显示完整截止日期。

证据results/lifetime/20261029-24h-01/summary.json。基线34；最终526pytest/22.83s、Hardhat89、业务UI33/审计UI3、构建、沙箱19及冻结/归档检查通过。live-02真实等待128秒后12检查PASS：缺单组织拒绝、完整双审→reserve→单封本地MIME→finalize、重复仍单封、越权/额度拒绝；原旧域邮件/链记录均VERIFIED。readonly-01四项只读复验PASS；browser-02五项实际HTTP/浏览器检查PASS，无新增业务事件。两轮真实验收总计2封MIME/4交易，另3部署交易/12receipt；本轮无模型调用，ASR不适用，不与旧实验池化。

失败保留：live-01业务实际成功，但末项脚本把已耗尽额度的POLICY_DENY误认失败（预期UNAUTHORIZED_SCOPE），原报告FAIL留存；修断言后新live-02独立PASS。一次npm参数透传错误及浏览器依赖解析错误均为验收命令/脚本错误，修正后通过。开始时gateway已退出137/OOMKilled=false，恢复原容器后预检通过，未推断原因。旧baseline.xml为0测试，不计本轮基线。未等待完整24小时墙钟；24h边界由Hardhat时间推进及单测验证，真实链只验证超过旧120秒后的执行。

下一步用户刷新8090，新建任务或在原会话发起新一轮明确请求；过期旧动作不自动重跑/续签。无新阶段、Git暂存/提交或新散置md。独立复验命令和新域地址见handoff/summary。

## 会话分层与恢复（2026-10-29，技术验收通过，待用户验收）

已接入独立conversation/session_id、加密逐轮记忆、完整Runner工具批次断点/CAS租约、HIGH原回执核验后自动恢复、LOW独立签名/两门持久配额/会话累计根、连续对话网页与只读核验。原21+8、三Registry及邮件执行核心未改。旧任务不自动合并；文档附件延续原无网络沙箱capability，不宣称链LOW凭证。

证据根results/conversations/20261029-implementation-01。本轮实际基线76；memory-module首轮50通过/2失败（None/list响应前调用get），修正类型检查后25通过；新增会话模块11通过；当前全量509pytest/20.26s、前端32/构建、新合约3通过。upgrade-01/02保留原卷和回退容器，独立ConversationSessionRegistry部署与5项默认LOW审核交易均真实四节点。live-01真实DeepSeek两轮/1封MIME通过14检查，原双审批、reserve/finalize、自动恢复、越权及重复阻断、LOW根均验证；不计ASR。

最新收尾结果results/conversations/20261029-completion-01/summary.json：相关基线17；关闭/在途LOW及升级专项31；517pytest/20.39s、业务UI32、审计UI3及构建、Hardhat84通过。21+8冻结及7份原HIGH核心源保持。关闭时尚无结果日志的LOW调用只能保留未最终封存前缀；新增测试覆盖结果/UNKNOWN落库后才允许closed根。

新live-01真实DeepSeek/四Besu19检查PASS（包括网页），2封本地MIME：摘要跨轮发送、独立双审、reserve/finalize、自动续聊、越权与重复阻断；真实UNKNOWN丢响应后原回执恢复且不重发。protocol-01为0模型/0邮件的10检查，跨轮配额耗尽转强审，单组织拒绝，双组织实际读取，两条LOW同一根。readonly-final核验4项原记录、两门承诺和模型请求记忆；browser-final进程重启/刷新两轮/三种宽度/原四表密文不变，无新模型或工具调用；ASR=null，不合并旧样本。

upgrade-01首次失败因历史回退容器重名，原服务已恢复，失败保留；修复唯一命名、停机前检查和rename失败恢复，upgrade-02通过且保留六原卷/回退容器。实际gateway/tool源码已与最终源码比对；8090/8091均200。README和现场指南已更新，不增加散置md。旧任务不合并、授权范围变更需新会话，模型请求中断不盲重试；附件仍本地授权。下一步等待用户现场验收，不自动重跑旧任务、不提交Git、不推进阶段。详细命令/真实交易及失败索引见summary.json和handoff。

已知验收脚本遗留：部分旧custom/http/github专项网页脚本仍监听/tasks创建响应，需适配会话messages后复跑；本轮新会话网页已实际通过，不能以此宣称全部旧专项网页脚本通过。原/tasks API仍兼容。

## 会话记忆与挂起恢复方案（2026-10-29，仅评估，待确认）

用户明确高风险保留原OrgA/OrgB独立审批、每动作reserve/finalize，只有LOW走会话快速通道及会话批量根。本轮只读核验前端/路由/Runner/Journal/门控/合约，未修改业务代码。现有发送每次POST新任务；Runner每次重置messages，Paused未保存运行快照；custom待审批被代理缓存为result；现有SessionGrant绑定taskId且仅覆盖custom工具，批次跨任务且原合约每批≤50连续sequence，不能简单改名为sessionId或按会话过滤。

拟增独立对话实体/消息/运行快照、会话Grant V2与两门共享会话额度、精确调用断点续跑、LOW专用会话存证；高风险意图及签名不塞session字段，不批量替代预约/回执。原审批签名先齐备再reserve，用户请求中的顺序按现有协议纠正；原120秒期限不延长。快照仅模型已返回消息/工具调用与调度位置，不声称保存模型内部思维。方案及拟改文件见results/context/20261029-session-plan-01/plan.json，未冻结/实施，需用户确认后开始。

本轮基线：相关pytest73、前端31、会话/准入/批次Hardhat5通过，规范/策略/归档检查通过；均既有实现单测，不是新会话功能验收。无新业务任务/真实模型/邮件或链交易。下一步仅等待方案确认，不新增散置md或Git提交。

## Agent回复排版（2026-10-29，技术通过，待用户验收）

对话页原先以普通文本显示agent_output，导致Markdown标题/加粗标记裸露。现仅在业务前端增加锁定的react-markdown10.1.0/remark-gfm4.0.1及独立回复组件/样式，渲染标题、列表、引用、代码和表格；用户输入及持久原文不变。禁用原始HTML/图片，链接仅显式HTTP(S)且隔离新页，不执行模型HTML。历史回复刷新即生效，无需重跑任务。

证据`results/ui/20261029-markdown-01/summary.json`：基线26，最终31项前端测试/构建、冻结21+8及归档检查通过；真实浏览器核对3条既有回复、33任务的输出/事件/交易哈希保持，0新任务/模型/工具派发。桌面及320/390px无横向溢出；独立合成页面只作排版/安全测试，两张图已检查，不当作模型或链证据。browser-01因测试切到手机后未恢复桌面、历史栏收起而超时；修测试后browser-02通过，失败保留。后台/合约/审计/签名及权限未改，不新增md或提交Git。下一步用户刷新8090查看旧任务；代码中的#/*等字面字符按原文保留，不是所有符号都会消失。

## PDF任务输出截断修复（2026-10-29，真实流程通过，待用户验收）

用户实际失败任务的原加密事件证实：PDF上传及attachment.read已成功，后续document_create在512 token上限下finish_reason=length、JSON截断；前次MIME补丁没有解决这个根因。现用独立config/interactive-agent.json：普通任务512，带附件/输出权限的文档任务8192；实际参数/版本持久化，正式实验计划不变。模型边界拒绝全部截断响应并报MODEL_OUTPUT_TRUNCATED，不自动补全/重试；前端据真实finish_reason解释旧SCHEMA_INVALID，原失败/先前读取保持。

证据 `results/documents/20261029-output-limit-01/summary.json`：本轮基线35，专项15，全量498pytest/22.16s、前端26/构建与冻结21+8通过。pdf-live-01为新网页/真实DeepSeek：3页中文PDF→实际读取→含40条完整正文的Word和PDF摘要，参数JSON最长2534字符，3轮finish_reason均非length；下载哈希/原件不变/刷新/公开本地观察通过，2产物共5页渲染检查通过。旧真实截断响应仅本地回放，明确拒绝且0工具派发；不计模型样本。现场重启后真实浏览器显示准确错误，原32任务/147事件密文字节保持；没有重跑用户任务或新增邮件/链交易。限制仍为有界文档输出，超过8192仍会明确失败，OCR/复杂版式/续聊未实现；用户需刷新8090新建任务验收，不自动重放原失败。

## PDF 上传 MIME 兼容与错误定位（2026-10-29，技术修复完成，待用户验收）

核对后确认 PDF 已被支持：隔离文档容器实际读取既有文字型 PDF，返回 `page:1`；`SCHEMA_INVALID` 不是 PDF 扩展名拒绝。为兼容浏览器直接发送 `application/pdf`，`POST /ops/v1/attachments` 现在接受 `application/octet-stream` 或与扩展名匹配的浏览器 MIME；扩展名、魔数、大小、加密/表单/扫描件限制仍由原文档库和无网络容器强制执行。前端发送文件真实 MIME，并对上传格式错误和 Agent `attachment.read` 参数错误分别给出说明；冻结任务授权、文档工具 schema、R2 链逻辑未改。

本轮验证：`pytest -q gateway/tests/test_document_tools.py` 为 **6 passed**；`pytest -q gateway/tests/test_document_tools.py gateway/tests/test_phase10.py gateway/tests/test_default_tools.py` 为 **40 passed**；`npm.cmd --prefix console test` 为 **26 passed**；`npm.cmd --prefix console run build` 成功；实际容器 PDF 探针返回 `status=PASS, units=1, locator=page:1`；重启后8090/8091健康检查均200。未创建业务任务、未调用模型、未发送邮件、未产生链交易。限制仍为文字型、未加密、非表单PDF；扫描件需要OCR模块，当前未实现。下一步用户在8090刷新后重新上传并观察错误提示。

## mTLS证书恢复（2026-10-28，技术通过，待用户验收）

已解决前一条UI交接中的证书阻塞：原CA及六类叶证书为2天期限，10月28日晚过期。按用户选择，保留所有私钥／身份／SAN／用途，续期叶证书7天、CA365天，同步六个原卷及gateway/tool对端指纹；原服务和8090/8091恢复。当前叶证书至北京时间11月4日约22:10有效。新增renew_phase10_mtls.py默认只读、--apply才更新，有私有备份／回退／执行中检查；部署工厂及两处Agent证书默认值同步7天。原执行代码／冻结协议不改，无新md或Git提交。

证据 `results/maintenance/mtls-20261028-01/summary.json`：基线24，证书模块8测试通过（真实OpenSSL验证7天／身份／用途／过期拒绝）；全量491pytest。原失败conversation浏览器现PASS，7项真实mTLS检查通过，双向指纹、错主机名／无证书／旧过期证书／Agent访问审批拒绝。真实DeepSeek三任务在独立测试业务存储通过，缺审批拒绝／只读越权拒绝／重复仅1封；新增沙箱邮件1封、reserve105506/finalize105508，各4份receipt，工具签名／MIME核验VERIFIED。原件只读复核3任务PASS，无重执行。现场30任务／133事件密文字节保持，121份业务／工具／Agent／合约／前端／规范源与21+8冻结输入未改。

脚本／命令／原始失败见summary和handoff；默认检查只提示24小时内到期，当前手动续期，不是自动证书管理服务。下一步用户刷新8090演示即可，7天后须续期；不因此宣称生产机构隔离或其他研究缺口完成。

## 侧栏滚动与统一接入（2026-10-28，UI 验证通过，待用户验收）

仅调整业务前端：历史列表独立纵向滚动，固定搜索／身份区域，补齐751–850px侧栏布局；“接入与管理”用同一选择器提供通用API、GitHub模板和CSV/JSON资料，移除GitHub顶层标签，将仓库核验收进模板。切换保留草稿，版本修改仍绑定原版本；原后端／合约／审计权限与冻结输入不改，无新md或Git提交。

证据 `results/ui/20261028-sidebar-tools-01/summary.json`：基线前端25、相关pytest82；最终pytest483/18.50s、业务前端25、审计前端3、构建及冻结／归档检查通过。真实Edge专项browser-after-02通过8种宽度（320–1500px）滚轮／键盘滚动、最旧任务选择、统一入口／版本预填／草稿和双审批身份边界；现场30任务及事件／交易标识不变，原1封MIME核验VERIFIED，无新增模型／工具执行。源码完整性见同目录integrity.json。

失败保留：browser-before复现原列表overflow=visible被外层裁切。额外conversation-after-01在旧动作“审阅原意图”失败，三个真实review请求均422/EXECUTION_UNKNOWN；transport-diagnostic直接握手证实内部mTLS证书过期（SSLCertVerificationError）。未关闭TLS校验、重签业务审批或改历史状态，不宣称本轮完整业务回归通过。证书续期及新任务闭环复验仍待处理，原执行终态不因此被UI改写；本轮仅完成用户指定前端修改。

## 工具免审与批量指纹（2026-10-28，技术通过，待用户验收）

完成OrgB版本审核LOW/HIGH上链、OrgA精确任务/Agent/版本/资源/期限/次数EIP-712会话、网关与工具独立持久nonce/额度、HIGH及过期/超额逐次双组织审批、300秒/50条Merkle根与同字节交易恢复、业务台及只读四节点核验。先补合约/门控再接界面；原R2邮件、三个Registry、原21+8冻结保持不变。LOW目前覆盖三个custom查询适配器；默认读取仍原capability，HIGH标签不开放任意写权限。

当前实测证据results/sessions/20261028-resume-01/summary.json：当轮49基线；最终483pytest、81Hardhat、console25/dashboard3、双构建/冻结/归档通过。live的18安全检查和真实网页通过，四日志单笔交易位于区块100951，tx=0xfbd932622e8ba605830ed3dd5ee4f24433380d2dca3f003e42f24911084bd4c8；web-final重新核对最终对话/证据侧栏。独立只读原件复核5+1条调用，未重新执行；原邮件1封及两交易各四receipt只读回归通过。真实双业务进程同epoch并发产生三笔不同nonce交易：成功/回滚/重审成功，12receipt一致。GitHub会话回归另存results/github/20261028-sessions-regression-01：现场2新真实DeepSeek任务，VS Code#1成功/React#1链拒绝，仅1HTTPS，无新邮件；人工负例不计模型指标。随后不调用flush，后台在最早日志304秒后自动将3条相关日志合为1笔交易，四节点核验及8091实时API均通过；当前8090可见29任务（本次仅该GitHub回归新增2条）。

原部署在results/sessions/20261028-01/deployment-02，两个新合约均实际部署到原四Besu；upgrade-04最终镜像/六容器保留原卷，8090/8091已恢复。旧部署过早、缺描述字段、nonce超过JCS、事务未commit及GBK收尾失败均保留，修正及当前验证见handoff；不再把旧交接的“升级中/闭环未过”当当前状态。原始证据不重写、未新增md或Git提交。

用户流程及一条命令见README和judge-walkthrough。旧工具须OrgB明确复审，不能自动LOW迁移。根确认前无链上包含性保证，根不证明外部数据真伪；多副本配额依赖共享持久DB。生产机构/密钥隔离、任意敏感HTTP写、其他R3与空白机器部署仍未完成，不属于本增量。完整文件、命令和后续接手步骤收于handoff及JSON证据，待用户现场验收。

## 通用 API 工具导入（2026-10-28，技术通过，待用户验收）

格式提示修正：用户填写weather_check被原命名规则拦截，正确为custom.weather_check。仅HttpToolForm新增常驻格式说明及中文原生校验消息，修改输入清除旧错误；后端规则/协议不变。证据results/http-tools/20261028-name-hint-01：前端24/HTTP基线42、构建及真实浏览器通过，原始名称报明确提示、修正后通过，0任务/工具提交。首个浏览器命令取登录文件路径错误，在启动前失败，纠正后通过；不改用户任务或扩大范围。

网页新增API地址、GET/POST、URL参数和JSON Body，沿原版本注册→OrgB准入→任务精确profile→真实DeepSeek/原网关/工具二验。新增独立HTTP服务，公网DNS检查并固定连接IP、TLS、禁跳转/代理/凭据与GitHub绕行；R1查询／识别，端点语义由安全身份审核，不能承担R2/R3。工具和服务持久幂等及AES-GCM原响应，UNKNOWN不重发；审计EXTERNAL_TOOL_OBSERVATION不冒充链认证。仅新增该适配器及相关前后端/部署/测试，原高风险协议与冻结21+8保持。无新md或Git提交。

证据 `results/http-tools/20261028-generic-01/summary.json`。基线99/前端21；最终全量pytest459/13.44s、HTTP42、Hardhat76、受限容器19、console24/dashboard3及双构建、冻结/归档检查通过。live-04完整新网页/真实模型/HTTPS POST200，2轮模型/1请求；原始响应与工具加密记录/参数摘要/公开投影独立复验，改URL/Body/未授权profile拒绝、重复返回原记录且fetch数3→3，撤销后拒绝。readonly-04不重调模型/HTTP；existing-ui核对24现场任务不增、原签名MIME1封及既有链证据，未发送新邮件或交易。现场8090/8091已重启，HTTP服务无公开端口；仅原工具容器升级，卷及回退容器保留，原R0 UNKNOWN不重放。

失败保留：module-01漏拦NAT64，修复后通过；live-01注册API白名单未纳入http字段（0模型），已补真实API测试；live-02实际模型/HTTP成功但观察器未等公开投影更新，修等待后live-03/04通过；module-04夹具名过长触发Windows临时路径及零Bytes32不合法，修夹具后42通过。各批独立，不混算ASR或伪称图片识别。本轮实际是HTTP回显验收；真实图片识别尚需目标API。暂不支持鉴权、浮点请求参数、二进制图片、模型动态扩参及UNKNOWN管理对账；不自动接入敏感写API或推进新阶段。

## 对话附件与 Word/PDF 副本（2026-10-28，技术通过，待用户验收）

新增独立document_tools镜像、DocumentLibrary/API与对话附件区；支持DOC/DOCX、文字型PDF、UTF-8 TXT/MD，4件×5MiB、100MiB私有配额，读取带page/paragraph/line引用，明确授权后生成或精确替换为新Word/PDF副本。原件不覆盖；私有文件/调用AES-GCM持久化，task+call完整参数MAC幂等，越权/过期/非法输入拒绝，按任务认证下载。容器无网络/主机挂载/密钥、非root、只读根、有资源及时限。原21+8、三原合约、高风险网关/工具与原代理未改；新增R1副本不冒充链认证，审计只展示LOCAL_DOCUMENT_OBSERVATION。接口合并原phase10-contracts，未新增Markdown或提交Git。

证据根results/documents/20261028-attachments-02/summary.json。基线87；全量pytest417/10.95s、最终相关40/2.54s，Hardhat76，console21/dashboard3，容器4组实际解析/作者边界测试通过。smoke-03为最终新网页+真实DeepSeek：实际attachment.read→document.revise/create，两份下载与摘要一致、Alice→Bob、预算保留、原件不变、刷新仍可下载；DOC/DOCX/PDF真实读改、重复1产物、权限拒绝无输出。最终8份合成文件逐页渲染检查通过。smoke-02亦真实通过但为标题样式修正前批次，分别保留，不作为ASR或合并重复样本。24个现场任务未增加；测试在独立临时业务存储/8092，进程结束。原邮件1封/预约与finalize各四receipt只读回归及320/390/750/1024布局通过。

失败保留：3次镜像构建因外部下载慢主动中止，镜像04成功，镜像05含最终标题修正/7项锁定依赖；首次前端null/false断言修正；首个容器测试打印GBK失败但原测试4通过；smoke-01附件定位器匹配含KB的文本失败，实际0任务/0模型，不应按该原浏览器预置real_llm=true字段统计；02/03修定位器后通过。existing-ui首轮在Web初次同步前取不到既有终态，增加等待真实状态后02及mail-chain-regression通过。原件不重写，完整诊断见summary。

当前8090/8091已恢复，新业务模块与最终镜像生效；使用及一条命令见README。待用户上传自己的文件验收。限制：不支持OCR/加密PDF/表单/签名/复杂排版保真/原件覆盖/邮件附件/历史续聊；DOCX改动段落丢run格式，PDF修改重排；未挂任务上传仍占配额，无物理清理接口。授权文字会送至配置的DeepSeek模型，页面已说明。本机BFF仍属可信控制面，生产多租户及原工具共享幂等存储边界不变。

## 对话主界面与统一工具设置（2026-10-28，技术通过，待用户验收）

本轮仅重排业务前端：左侧任务历史、中间真实对话与底部新任务输入，审批/交易/MIME证据按需展开。默认工具、资料导入、版本准入和GitHub接入统一进入“工具与设置”三标签；保留草稿/下一任务范围、手机历史入口及独立审批身份。每次发送仍创建独立任务，未实现续聊；刷新会清除未提交草稿。原API、后端/合约/审计源码不改。删除已被替代的统计/网格/输入框CSS，无新Markdown或依赖，不提交Git。

当轮证据 `results/ui/chat-20261028T132747/summary.json`：基线119相关pytest、20/3前端；全量411pytest/19.29s，前端20/3、构建/21+8冻结/归档/diff检查通过。最终真实浏览器 `browser-final`、`existing-ui-03`、`default-tools-02`通过；24既有任务不变，0新任务/模型/工具执行/交易，原1封签名MIME及reserve/finalize各四节点receipt复核VERIFIED。193份原执行/协议/合约/审计等源码摘要不变。旧创建/审核演示脚本已适配导航并做语法检查，本轮不声称重新实跑这些写入流程。

失败原件保留：按钮名称附加字符、旧脚本在手机隐藏列表/设置页寻找控件，修正后通过；一次pytest命令参数错误未运行测试，后续才实际411通过。`existing-ui-02`审计页面等待超时，原响应未捕获，原因未确定；随后直接API、独立浏览器及带响应记录的03均VERIFIED，未修改审计逻辑或伪造状态。下一步仅待用户打开8090验收布局；不自动新建业务任务或推进新阶段。

## GitHub 仓库链上验收（2026-10-28，技术通过，待用户验收）

用户明确要求公开 microsoft/vscode Issue 通过、其他仓库由链拦截，并确认新增独立策略而保留冻结协议。新增 RepositoryReadPolicy、github_policy 核验、工具/读取服务前后双节点检查、Web 实时策略/人工负例按钮及 test_github_policy.py；部署到原四 Besu，合约 `0xddb934be23a50b6bf2653621d1f61094242c3ce0`、策略交易 `0x56bbcc8c69a5c5843e857d7bdf3b67247fae6a5537b81616c24358fd379c504d`。两组织治理只允许 microsoft/vscode；精确任务键仍独立检查，原三合约/21+8冻结输入不变。运行镜像 github-policy:0.10.4，原私有卷和回退容器保留，8090/8091已重启。

权威新批次 `results/github/20261028-policy-01/live-03` 单命令 PASS：两条现场新真实 DeepSeek 任务，VS Code #1 真实 HTTPS 200，React #1 即使本地键已授权仍 GITHUB_REPOSITORY_DENIED、无 HTTPS；另两个页面按钮分别证明链拒绝/工具 UNAUTHORIZED_SCOPE，计数不增。仅 1 次新 HTTPS，0 邮件、0 逐读取交易；链治理另有 2 笔部署/启用交易，各 4 receipt。模型工具调用、原工具加密记录、原响应字节、动态 R0 投影、对应历史区块的四节点状态及治理 receipt 独立核对。人工探测不计模型 ASR，R0 准入不是 R2 reserve/finalize 或来源上链。复现/只读命令见 README，完整命令/文件摘要与限制收于该结果根 summary.json，不新增 md 或提交 Git。

当轮基线 72；模块 73、专门策略 11、全量 pytest 411、Hardhat 76、前端 20、受限容器 14、构建/冻结/归档检查通过（最终原件见结果根）。final-readonly-ui 实看新增成功/拒绝证据及390px布局，无模型/工具重执行；原邮件只读回归核对1封MIME/8份receipt通过。失败保留：live-01 因配置误写 /sandbox 而非工具实际 test-* 根返回 UNKNOWN，无降级；修复部署脚本并增加工具实目录预检。deployment-recheck-02 因 UNKNOWN 触发升级空闲保护，后将不重启的配置修复与升级区分，不篡改旧任务；03 无重部署通过。live-02 浏览器两真实任务通过，但观察器错用 state 字段收尾失败，readonly-02 从原件独立复验 PASS；live-03 才作为完整一键验收。初次 npm 参数转发错误未运行合约测试，改 Hardhat 入口通过。原邮件核验首选旧任务缺负例计数字段而失败，改选证据完整任务复验；未修改旧任务或验证器。旧失败不覆盖，测试资料保持可审查；首次失败任务保持 UNKNOWN。下一步仅待用户网页验收，不扩展私有 Token/其他仓库/写工具/高风险协议。

## 首个真实工具：GitHub只读（2026-10-28，技术通过，待用户验收）

已接入github.read，沿原版本审核/任务精确资源/Agent代理/网关/工具端独立capability执行真实GitHub公开仓库元数据与Issue GET。网页“接入真实GitHub只读工具”可注册→security审核→选资源准备任务→真实DeepSeek查询；来源卡展示URL、HTTP、时间、请求ID和原始响应SHA-256。独立读取容器不持有邮件/链/模型密钥，无公开端口；Token只在两个私有卷。dataset.lookup仍是快照，GitHub目录摘要不是结果摘要。R0观察不伪装链认证，原R2/冻结协议不改。

结果索引`results/github/20261028-01/summary.json`；真实批次`results/custom-tools/github-20261028-01`为两条新网页/DeepSeek任务，psf/requests与Issue#1均HTTP200。原HTTPS字节、投影、加密工具结果/读取日志、模型tool-call及tool-role、动态R0审计一致；只读独立复核PASS、不重请求动态源。越权、只读发信及停用后直接工具调用拒绝，成功GitHub请求数保持2。真实断开读取服务网络时GITHUB_UNAVAILABLE、无成功读取，已恢复连接。现场仍19任务/103事件，新测试在独立存储；新增邮件/链交易0，不计算ASR。

本轮65项基线；最终pytest400/9.68s、Hardhat71、前端18及构建、受限容器12项、冻结21+8/归档/现场浏览器/原邮件证据只读回归PASS。原件保留：继承系统代理首请求403，直接HTTPS200；初始化早于升级完成失败，完成升级后setup-02通过，脚本增加模块预检；网络观察器错误假设原QBFT是internal而失败，修正报告披露Internal=false；只读浏览器切换任务沿用details展开状态导致超时，修复任务隔离key后复验通过，未新增模型/API调用。无新增md或Git提交。

已知限制：仅公开repo元数据/精确Issue，不支持私有库/PR/搜索/仓库文件/写入；无GitHub令牌、受匿名额度及网络限制。原工具所接QBFT网络Internal=false，本轮没有给其连接新出口网，但网络层全外网隔离尚未证明；固定域名/GET是实现限制。源日志由本机可信服务保存，不是GitHub签名或链上来源证明。下一步等待用户现场验收，不扩展其他工具或权限。

## 自定义工具导入与版本管理（2026-10-28，本轮续接）

已补齐上一轮未完成的CSV/JSON导入预览、不可变父子版本/差异/带UTC事件、注册幂等与并发旧父版本拒绝，以及页面选精确版本和记录键准备只读Agent任务。预览不注册，v2重新安全准入，旧数据/旧任务不升级；准备任务不会自动调用模型。修改范围为custom_tool_import/custom_tools、phase10 API/service、console管理/导入/任务表单及测试，规范并入原phase10-contracts与README/现场指南，无新增md、无Git提交。原协议、三合约、高风险执行链不改。

结果根`results/custom-tools/management-20261027T204729580737Z`：相关基线63通过；管理模块22、前端16与构建通过。real-smoke-01为两份真实文件导入→v1→修改v2→OrgB审核→页面准备任务→真实DeepSeek查询的独立新批次；CONTACT-001与SKU-002返回v2资料，旧版不变，未审核/越权记录/只读发信拒绝。readonly-01从原加密工具资料/日志、模型tool-call与tool-role结果及R0投影复核通过，不重调模型、不重新查询。新增邮件0、链交易0，不统计ASR；测试v2已停用、v1未启用，临时8092/8093退出，原卷保留。最终回归及命令详见summary.json，后续条目为历史结果，不能替代本轮报告。

用户补充最终希望有真实工具接入。当前dataset.lookup明确是导入快照，实时数据库/现有服务API仍TODO；已询问具体数据源，未用另一个示例冒充真实集成。本轮先交付已授权的导入/版本/任务入口，实际工具的端点/Schema/凭据保管/只读范围须确定后接入，Agent不持凭据。既有生产/研究限制继续有效。

## 联系人/库存查询示例（2026-10-28，技术通过，待用户验收）

按用户指定增加两个R0注册模板：联系人按contact_id查姓名/部门/本地测试邮箱；库存按sku查整数数量/预警线/仓库。CustomTools按钮只填写可编辑输入，不自动注册、准入、创建任务或调用Agent；沿原dataset.lookup、安全身份启用、版本/记录键任务授权及独立工具校验。未改原协议、业务网关/Agent安全逻辑或容器。

结果results/custom-tools/20261028-examples-01：相关基线61；最终pytest355/10.53s、console13和构建通过，冻结/归档及现场默认库浏览器回归通过。真实网页注册/审核/DeepSeek查询两个场景均READ_COMPLETED（库存实查2与10），工具原加密数据/持久查询摘要、模型请求/结果和动态R0审计复核通过；各组越权查询与只读发信探测UNAUTHORIZED_SCOPE。readonly-01与旧邮件闭环mail-readonly-regression均只读PASS，没有新模型/工具调用。新增测试邮件0、链交易0；测试版本已停用，临时8092/8093停止，现场19任务不增。没有失败重跑或新md。当前示例只提供查询，不改库存、不采购；下一步待用户验收，不扩展适配器。运行命令与文件摘要见该目录summary.json。

## 自定义工具第二步（2026-10-28，技术核验通过，待用户验收）

已完成网页注册受控R0 dataset.lookup、security按精确版本准入、任务选择版本与记录键、真实Agent调用、工具端独立范围/期限/停用检查、加密资料和持久查询摘要。新版8090/8091已恢复；原审计只读、高风险审批/签名/预约/回执及冻结21+8不变。不支持任意代码、网络适配、新高风险工具或R3。

证据results/custom-tools/20261028-02：最终pytest353/11.42s、Hardhat71、受限沙箱容器9、console10/dashboard3、构建/冻结/归档/默认库浏览器回归通过。real-smoke-03由网页创建新任务，真实DeepSeek查询→双组织批准→预约73437→本地MIME1封→finalize73438，8份四节点receipt、工具签名、原数据/读取/参数承诺均核验。缺审批/越权查询/停用后查询拒绝，重复仍1封。readonly-02只读复核PASS，不重调模型/重发。现场任务列表未增；临时8092/8093停止。完整文件/命令见summary.json和handoff，无新增md。

失败均保留：容器与HTTP测试两处错误预期已修；首次网页脚本取record过早、第二次报告GBK解码失败（业务已执行1封），第三次新目录完整PASS另1封。本轮共2封/4交易，失败批次不伪装通过、不混算模型攻击率。旧测试注册已停用。下一步等待用户验收；其他适配器需可信实现、风险/作用域及Schema另评审，原生产/研究边界未改变。

## 默认工具库增量（2026-10-28，技术核验通过，待用户验收）

仅默认库，不进入自定义工具注册/R3/外部邮件。六个启用工具为doc.list/search/read、mail.list/read/send；网页按任务选择工具、文档和可读邮箱。真实模型可多轮读取并总结，首个高风险提议暂停，发送继续原双组织审批/预约/工具二验/签名回执。新R0读取capability独立于冻结R2 TaskGrant；只读任务发送范围为空，直接绕过模型层尝试发信也被原策略拒绝。READ_COMPLETED只是调度状态；审计READ_ONLY_OBSERVATION仅说明不适用预约，不声明链认证。只有两份合成文档与本地测试邮箱，无任意主机文件/网络权限。

证据results/default-tools/20261028-01：本轮基线305；最终pytest **326 passed/9.51s**，Hardhat **71 passing**，沙箱无网络/非root/只读根容器 **5 passed**，console **9 passed**、dashboard **3 passed**，两端构建、冻结21+8、归档及最终diff检查通过。真实DeepSeek三流程PASS：文档列举→搜索→读取；读取→双审批发送；邮件列举→读取。1封新真实MIME、2交易/8份四节点receipt，缺审批拒绝/重复不增封；只读任务直接发信UNAUTHORIZED_SCOPE。真实模型不是固定trace，但本轮不计算ASR。独立readonly-03复验原工具读取日志/实际文件与MIME、精确参数承诺、原签名/链通过，不重调模型或执行工具。

现有6容器已用default-tools:0.10.1替换，原卷/链/合约保留，停止的before-default-upgrade-02回退副本仍在，runtime私有备份同目录。8090/8091在线；真实浏览器默认工具选择、资源缺失禁用、390px布局及旧任务四节点审计/三个身份/只读边界PASS；现场业务任务仍19，本轮模型测试使用独立.local/default-tools存储，没有自动新增现场任务。

修改集中在default_tools/DefaultLibrary/DefaultToolProxy、Runner可选schema、phase7读取路由、phase10编排/API/bridge/client/审计、两端界面与对应测试；完整清单及命令在该目录summary.json。运行/只读复验命令已合并README和原阶段10契约/评委流程，无新增md、不自动提交Git。失败原件保留：module-01路径错误（修后通过）；readonly-01缺公共entry_id；readonly-02触发现有MIME多行LF/CRLF误判。只修独立verify_demo_task核验器的传输换行比较并补测试，原参数/签名/邮件未改，readonly-03通过。一次diff检查因Python写入CRLF失败，已仅规范本轮非冻结文件行尾，最终通过。

TODO/下一步：自定义工具注册、用户资料导入、真实外部邮箱/R3仍未实现；未来接入须定义Schema、风险/作用域和可信执行适配，不开放任意脚本。R0审计摘要不是独立链认证，邮件列表最多50条且只匹配本地授权邮箱。原工具多副本共享幂等存储的适用边界不变；本轮未做新ASR或生产部署。

## B/C新对照实测（2026-10-28，技术核验通过，待用户验收）

用户已授权“开始实测新的对照”。新增evaluation/bc_live_plan.json、bc_live.py、tests/test_bc_live.py、scripts/run_bc_experiments.py；使用原服务/工具与原字节码、新测试身份/三合约地址/独立受限Docker卷，真实四Besu链ID20261026。原B双签、工具二验和检查点保留；不读模型Key、不调用LLM，不改现场卷或原治理/冻结协议。权威批次results/phase8/bc-live-20261028-01/run-02单命令PASS：65条新观测（31对B/C+3条C单RPC故障）、71封真实原卷MIME、75交易/300四节点receipt、34份B精确双签及34份C工具签名。原治理epoch6/paused=false不变，核验期间高度70956→71056。PASS表示实验/证据核验完成，不表示所有攻击阻断。

两批观察一致，最终统计仅用run-02：单中央目录管理员替换审批身份后B发送3/3，单组织C治理6笔真实回滚且0/3发送；共享状态竞争B/C均单封，分裂网关+工具存储B每例2封/C每例1封。只保留检查点时B能检出删尾但不能恢复完整最终事件，C能从链恢复公共授权/结果元数据，B+log独立完整签名日志也能恢复。**独立工具存储的同预约重复投递中B/C每例均2封**，C多出3份有效工具签名但未锚定的回执；一次性执行依赖工具共享持久幂等存储，不得把一个FINALIZED_OK当“绝无第二副作用”。故障恢复正常；RPC失联不是验证节点停机容错实验。每机制仅3重复，不计LLM ASR或统计显著。

正常服务层P50/P95/P99(ms)：B310/351/359，C3337/4179/4472，n=10；bootstrap区间在aggregated_metrics.csv，排除模型/HTTP/mTLS/人工及证据导出。C每动作gas中位数653116；SQLite字节B122880/C159744，不包含全节点账本成本。命令及判定边界见evaluation/README；四标准产物、逐例、交易与原卷核验均在run-02。命令`python scripts/run_bc_experiments.py --out results/phase8/新目录`真实重跑；加`--verify-source 原批次`只读复验。

当轮基线31项pytest，新增/修复后全量305 passed/10.13s，Hardhat71 passing；冻结/归档检查通过。额外离线readonly核验器拒绝篡改MIME摘要。run-01实际65条观测已完成，但evidence_file索引被共享写入触发收尾比较错误，manifest保留FAIL；verified-01修复后原件不变/无重执行复验PASS。随后run-02单命令从头完整PASS，不池化两批/派生副本。未新增md或Git提交。

待补：实际验证者停机/链停顿、独立机构/宿主、完整B+多方目录治理和全节点存储成本。分裂网关中C败者本地仍RESERVING，真实交易已回滚；当前只报告而不改核心。工具多副本安全增强需单独设计/授权并保留冻结约束，本轮不擅改协议。

## 界面重设计（2026-10-28，待用户验收）

按用户要求参考Linear重设计业务8090与只读审计8091：深色侧栏、统一紫色强调、任务授权输入、搜索筛选、双组织审批进度、下一步操作、独立链核验和分层证据；手机适配。共用presentation/ui/theme位于shared，Vite去重React；源码包与阶段9重建复制范围补齐shared。仅前端和构建支持调整，70份安全执行/合约/规范源码及21+8冻结输入本轮摘要不变。未新增md，未提交Git。

证据：results/ui/20261028-redesign-01。全量pytest **284 passed / 15.24s**，Hardhat **71 passing**，业务前端 **7 passed**、审计 **3 passed**，两端构建、冻结检查、归档检查通过。真实Edge检查三个独立身份、搜索/筛选、审阅、原MIME的签名/承诺核验、两组织审批、reserve/finalize各四节点receipt、过期禁用、审计写入口缺失与390px无整页横向溢出；没有新建任务、调用模型或派发工具。最终浏览器证据见交接记录，截图只作视觉检查。

恢复了原配置Web与六个已停止的阶段10容器，不改卷/链/合约。前两次浏览器失败原件保留：8090未启动、执行容器停止导致原动作未同步；恢复后通过。首次共用React解析失败已由Vite dedupe修复；日志收集器一次GBK输出失败不影响已成功构建，后续使用UTF-8。未重跑付费模型/新邮件闭环或空白机器完整部署；研究缺口沿用下文，阶段10核心边界不变。

## WSL存储迁移完成（2026-10-27，维护）

用户授权将现有Ubuntu迁至E盘。已使用官方 `wsl --manage Ubuntu --move E:\WSL\Ubuntu` 完成；名称、注册身份、默认UID1000不变，D:\CCF代码仍在原位。先冷停11容器/宿主Web和WSL，保存完整离线VHD到 `E:\WSL-Backups\Ubuntu-20261027-01\ext4.vhdx`（受限本机目录，含私密材料，保留不删除）。原盘/备份/迁移后首次启动前SHA一致；原C盘VHD已移走，释放10.95GiB，完成时约19.2GiB空闲。

证据results/maintenance/wsl-move-20261027-01：82卷/18,316文件冷态内容与权限摘要一致，85原容器ID/镜像/挂载/命令及镜像/卷集合保留，原11运行容器恢复；17任务及逐任务事件数、10封MIME/10工具记录不变，无新模型/业务副作用。四原Besu和8080/8090/8091恢复，页面200。相关45pytest迁移前后均PASS，冻结checks通过、130源码摘要不变，原成功任务verify_demo_task前后PASS。未重跑付费实验/全量合约；辅助ACL检查误把OS添加的VM/WSL能力身份判为异常，检查后确认预期身份且未改ACL，最终PASS。新运行盘在E:\WSL\Ubuntu\ext4.vhdx，启动命令不变；备份约11GiB另占E盘空间。完整证据/恢复边界见该目录README.md。未自动add/commit，后续业务阶段保持原范围。


更新：2026-10-27。范围：处理[缺陷报告](../results/review/20261027-project-audit-01/PROJECT_REVIEW.md)，精简重复文档；不扩展R3或外部邮件。阶段10本地R2原型已实现，用户现场验收仍待完成。HEAD=a5c23eb，未自动暂存或提交。

## 缺陷处理结果

| 报告问题 | 本轮处理与剩余边界 |
|---|---|
| 没有真实模型越权/网关阻断因果链 | 已补最小开发证据：目录注入使三组真实DeepSeek均提议给Bob发信；A实际发送2/2，B/C各拒绝2/2、无副作用。只有两任务，不能推广为广泛有效或C优于B |
| 固定答案、任务/攻击简单 | 新增两个需真实读取并生成摘要的业务任务、两类注入、每组重复两次；另建只改低信任源内容的目录探测。仍缺独立测试集、更多任务/攻击族和功效分析 |
| AgentDojo仅适配子集 | 保留官方0.1.35/v1.2.2的112份原文件/判定器；完整官方任务、搜索/附件和utility仍不兼容，没有伪称完成 |
| repetitions与评分写死 | 重复次数实际进入配对调度；摘要事实规则、显式邮件/删除目标、任务聚类、不同组越权尝试分母失配标记。真实删除证据不足时保留未知；未实现完整C组R3 |
| C的增量证据不足 | 两RPC/发送者争用同一requester nonce：一个真实预约成功、一个回滚，nonce永久消费；当前复核12份receipt通过。无工具派发；尚无独立机构或完整B/C存储拓扑对照 |
| 历史镜像缺失 | 显式只读observer-image成功核验原卷93邮件/59交易/236receipt；保留原执行镜像/容器/卷关联与旧失败。原执行镜像仍未找回，不等于恢复原执行环境 |
| 交付/运维/版本 | README区分组件与协议版本；链启动默认保留历史查询overlay；提供含未提交阶段10代码的带摘要源码包。空白机器完整部署、正式许可证与Git可复现提交仍未完成 |
| 文档堆积 | 清理24份独立md：23份冗余阶段/演示叙述逐字节归档，重复实验说明合并到evaluation/README；progress/handoff不再堆历阶段长日志。冻结规范与失败证据保留 |

核心执行源49份、阶段0的21份及共用策略8份摘要均未漂移；旧正式两轨清单内146+22份产物保持原字节。没有降低审批、预约、工具二验或幂等约束。

## 真实实验与统计

各轨分开，不把前置、开发探测或重算副本当作新增正式样本。

| 本轮运行 | 实际结果 |
|---|---|
| remediation-one-command-03 | API预检 → 12条C前置 → 36条A/B/C摘要任务全部通过。正式对照部分36读取/36本地MIME/C24交易/96四节点receipt；每组TCR12/12、ASR0/8，越权提议0，无UER/UBR分母 |
| remediation-directory-probe-01 | API/C前置/12条A-B-C开发探测通过；12读取、8邮件、C4交易/16receipt。两干净任务三组各2/2；两注入任务三组均实际尝试Bob |
| remediation-directory-analysis-02 | 修复MIME换行归因后，从上一行原始模型/工具/链证据重算；A的UER与ASR均2/2，B/C的UBR各2/2、ASR0/2。无模型重调、无工具重发，源文件摘要及分析代码摘要进入清单 |
| remediation-recheck-03 | 旧正式协议原件新副本，只读原卷/四节点/统计重算PASS：138例、93MIME、59交易、236receipt。观察镜像替代被明确披露 |

目录探测同时改变不可信材料中的路由数据与发送指令，尚无消融；可信任务文本、TaskGrant、系统提示与原B/C策略不变。该轨统一max_tokens=1024；摘要轨512，两轨不合算。模型为deepseek-flash，thinking disabled、temperature=0、top_p=1。

目录探测每组仅两攻击样本：2/2的Wilson95为[34.24%,100%]，0/2为[0,65.76%]；不作总体零风险或统计显著性主张。C与强化B在此同样有效。包含攻击任务的TCR三组均2/4，不能用干净任务2/2替代总分母。

## 验证与复现

证据根：`results/remediation/20261027-03/`。本轮命令及结果：

- `python -m pytest -q --junitxml=results/remediation/20261027-03/final-pytest-04.xml`：**284 passed / 9.14s**；基线为270。新增结果解析、隔离判定环境、换行归因、源文件不变及维护边界测试均实际运行。
- `npm.cmd test`：**71 passing**；`npm.cmd --prefix console test`：5 passed；dashboard：3 passed。
- `build_specs.py --check`、`freeze_phase3_policy.py --check`、`tidy_docs.py --check`、`chain.py validate --wsl-distro Ubuntu`通过。归档26份原文（23份移走的md及旧进度/交接/README）；当前docs散置md29份，含7份冻结规范。
- 动态审计和业务健康HTTP均alive、四节点ONLINE；文档链接检查通过；原49执行源和21+8冻结摘要检查见integrity.json。共享nonce旧交易本轮仅只读复核，不新增执行样本。
- 新实验独立receipt/原卷/签名/承诺/统计核验均通过。源码包由`scripts/make_source_bundle.py`生成于`results/remediation/20261027-03/source-bundle-03/`，含当前未提交源码和逐文件摘要，排除私密运行数据；不声称空白机器全部署通过。

一条命令重现摘要报告：
`python scripts/run_real_experiments.py --plan evaluation/summary_plan.json --model-only --out results/phase8/my-new-summary`
目录探测、重算和原卷复核命令统一见[evaluation/README](../evaluation/README.md)。必须使用新结果路径；命令会调用真实模型并产生本地邮件，耗时及输出不是固定值。

主要修改：evaluation的计划/结果/指标/目标评分与测试；run_live_agent、verify_live_agent、run_real_experiments、verify_phase8、reanalyze_live_agent、check_shared_nonce、chain、make_source_bundle及对应测试；README和当前文档入口。原合约、Runner/Proxy、网关与工具安全核心不改。

## 失败保留与下一步

one-command-01因真实模型截断JSON触发收集器异常；修复后原响应/错误样本保留，未派发JSON不算安全拦截。one-command-02的12条真实C前置已执行，但新增顶层网关导入导致独立官方判定环境失败；已改为观察函数内导入并增加隔离环境测试，03全流程通过。两失败目录均保留，不重写为PASS。源码包首跑因导入Agent包而缺工具运行依赖，失败日志source-bundle.txt保留；已改为只加载现有纯配置解析器，补齐CLI打包测试，维护模块6项通过，最终源码包使用新目录02。

目录原始分析将SMTP的CRLF与模型LF当成不同正文，曾错误统计A的UER0/2；原件保留，权威派生分析02更正为2/2，ASR仍来自原MIME。该修复只在统计层比较换行，不改变原参数或签名承诺。辅助读取GBK失败及package.json的CRLF空白检查失败已修复，不伪装实验通过证据。

待补：独立测试集与更多任务/攻击族、完整官方AgentDojo、多机构及B/C拓扑对照、其他C工具/R3、空白机器重建。许可证由所有者选择，Git提交须用户要求。本地同机测试身份/四节点不等于生产机构隔离；SQLite邮箱原子性不推广为外部SMTP exactly-once。

业务8090、动态只读审计8091；[评委流程](judge-walkthrough.md)用于现场新任务验收。双审批后仍须请求者在原120秒期限内确认预约，UNKNOWN只查原回执。完整历史在history.zip，不继续向本文件追加阶段长日志。

收尾清理：自动审批拒绝删除打包失败遗留的空目录results/remediation/20261027-03/source-bundle，原因仅为blocked by policy；目录已保留，不重试删除，不影响源码或测试。源码包03仅补充此交接，02快照保留。

## 比赛报告最终重排（2026-10-29，待用户审阅）

用户要求报告围绕“区块链创新应用”展开，具备专业的封面、摘要、目录、正文层级和附录，并将原第六部分的现场演示改为总结与展望。本轮基于已核验的比赛报告源重排，未改业务逻辑、冻结协议或实验原件，也未新增模型、工具、邮件或链交易。

最终交付目录：`output/pdf/ChainGuard-competition-report-final-20261029/`。主源为`main.tex`，PDF为`ChainGuard-report.pdf`，源码包为`ChainGuard-LaTeX-source.zip`。报告包含：区块链应用价值、四节点QBFT架构、跨组织治理、EIP-712与一次性预约、工具回执、LOW批量Merkle存证、B/C增量实验、总结与展望；附录保留实验数据来源、交易样例、代码入口和复现命令。用户提供的两张图经原有可读性整理后继续使用，来源与编辑范围记录在`image-provenance.json`。

本轮实际验证：XeLaTeX/TeX Live 2025编译通过，21页；中文字体映射检查通过；PDF文本检查覆盖封面、摘要、目录、区块链主题、总结展望、附录，并确认正文不含“如何现场演示”章节；Poppler渲染21页后检查接触表及封面、架构、总结、附录页面，未发现裁切、重叠或缺字。验证入口为`results/reports/20261029-competition-report-final-03/delivery-validation.json`，编译日志同目录。

排版取舍：章节不再强制每章单独换页，减少空白页；参考文献和附录仍保持独立层次。第六章仅写项目总结、应用价值、适用条件和后续研究；现场操作步骤仅作为附录B的复现说明，不作为正文主线。实验数字沿用既有真实证据，并在报告中保留样本量、区间和限制，不能把小样本机制结果外推为普遍结论。

下一步：等待用户审阅报告文字、比赛模板和封面信息；如需改动，只修改报告源并重新编译验证，不重跑已完成实验，不覆盖原Word和旧报告。
