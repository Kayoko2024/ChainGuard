# ChainGuard 项目进度

## V1.0.0 最终独立验收（2026-10-26，验收结论：原型有限签收，完整交付不通过）

本轮用户要求独立验证，禁止继续新功能开发。实际重读规范／源码／Git并执行 Python 231、Hardhat 71、前端3测试，全部通过；受限容器8+26项通过（100并发邮件、50并发删除仅tmpfs沙箱）。新受控干净目录17步均0退出，重复231/71/3及真实HTTP/Edge冒烟通过。证据根results/final_acceptance/v1-independent-01，根FINAL_ACCEPTANCE_REPORT.md为最终判定入口；不是直接引用阶段9历史PASS。

历史源b5b09af5ea协议59交易/236receipt、正式模型8交易/32receipt及原卷93/12 MIME真实复核；完整验证器只操作副本，旧授权区块eth_call不可用，原protocol-0000/0006及完整两轨复验仍UNAVAILABLE，不能升级为PASS。旧证据索引162份逐字节不变。新独立真实演示results/phase9/final-independent-deploy-01（8083），源results/phase8/phase9/7f6e0d69f7，隔离新卷138例/93MIME/59交易；独立只读再次复核全部236receipt/原卷，protocol-0000 VERIFIED、0043 NO_RESERVATION、0006 UNKNOWN/链RESERVED/PENDING_RECEIPT且不重发。新动作不能替代原actionId的历史证明。

真实链20261026、四验证者各3peers，原合约代码一致，独立区块24546→24550；新合法reserve f160bb7b…e2f53f3d/24180，finalize 17bf3196…c7672c/24181。五种副本篡改INVALID、只断新审计容器网UNAVAILABLE、恢复VERIFIED。原27合约交易108receipt本轮重读17成功+10预期回滚（阶段5工具回执仍夹具）。模型不重调API，只复核真实历史请求/副作用/原判定器；两轨重算CSV/Wilson及独立150项Bootstrap/分位数一致。协议ASR未测，DeepSeek各ASR0/3、模型无越权尝试，不能算网关拦截。

用户本轮明确授权建立无隐私可追溯版本：原无HEAD，已建立源码基线b4a57819215c971eda48e4c60ae60feb4c2fde7a（283审核文件，通用作者，原始数据保留、不推送、不打Release标签）；最终文档提交与HEAD见证据根git-final.json。不再以旧“无HEAD”描述当前仓库；此前开发历史仍不存在。Key仅本地忽略配置，模板空，源码blob扫描无当前Key/个人主目录路径。运行日志和原始证据未整体纳入Git，不可直接git add .或当匿名发布包。

FAIL/未完成：根项目许可证、匿名发布包、软件版本0.1.0/0.9.0与协议1.0.0不统一；空白OS/新genesis重建未测；完整官方utility不兼容、小样本研究不充分；其他C工具/R3完整闭环/生产多机构隔离/HSM等仍原TODO。两PDF3+4页本轮只读提取/渲染检查且原字节不变。验收辅助首轮history字典路径TypeError、retry01混合编码、补充新证据首轮缺transactions字段等失败保留；没有修改业务/测试预期消除失败。收尾git diff空白检查因Windows写入CRLF且仓库*-text而退出2，已恢复原文档body字节并仅使新段落/报告使用LF；失败日志保留。普通沙箱helper启动失败，经工具提权流程执行，无自动审批拒绝遗留。

结论：现有本地R2原型可有限范围签收；完整研究实验及正式V1.0.0竞赛交付不可无条件签收。本轮验收结束停止，不自动选许可证、改版本、补实验、推进新功能或重发UNKNOWN。原8080/新8083/四Besu保留，8081干净重建容器已停止、所有卷保留。完整命令/退出/失败/证据索引见最终报告与commands.jsonl，收尾状态见acceptance-summary.json。

## 最终阶段9（2026-10-26，技术验收通过，等待用户验收）

已完成只读React审计控制台、独立audit-api/公开投影/四节点签名核验、一键真实证据与受限部署、HTTP/Edge/篡改/断链冒烟、演示、匿名Markdown/PDF报告和受控干净重建。原116份阶段8源码和21+8冻结条目（25不同文件）changed=[]，无核心安全逻辑变更。Git无HEAD/0跟踪，不自动提交。

最终实际：231pytest（8.98秒）、71Hardhat（13秒）、19阶段9模块tests、3前端tests和两冻结check通过；final-checks原日志保留。deploy-final退出0/PASS，8080运行，138公开记录。新真实协议源results/phase8/phase9/b5b09af5ea，138案例/93本地MIME/59tx/236实时节点receipt，chainId20261026，高度22651→22722；原卷readonly/SQLite mode=ro、签名/承诺/calldata/事件/nonce/统计重算PASS。正常reserve b5010814…37a00b/block22656，finalize 3ea909c6…c0aea5/block22657，完整hash见验收文档与原件。UNKNOWN缺回执保持PENDING_RECEIPT，A/B历史单列。

observer-final真实5类篡改INVALID、只断审计容器网络UNAVAILABLE、恢复VERIFIED通过。clean-final17步骤均退出0，新源码/venv/root及前端node_modules、锁定安装/pip check、231pytest（10.64秒）/71Hardhat/3前端tests、无缓存镜像和8081真实HTTP/Edge通过；原清洁容器已停止、卷保留。两匿名PDF3+4页，Author为空，全部页Poppler渲染与最终桌面/手机UI版式检查完成；截图只作QA，执行证据仍为原回执/工具卷。原raw数据和两轨统计不池化。

失败保留：deploy01/02缺validator读取导致原TypeError，只演示进程严格转失败重试、无伪值；clean01空公开卷缺catalog，实际卷预检/就绪轮询后02/final通过；旧历史块权限不可查必须UNAVAILABLE。临时报表GBK读取改显式UTF-8。未完成：空白OS/新genesis全流程、其他C工具/R3闭环、独立机构/生产认证/HSM、完整官方benchmark/大样本、匿名发布ZIP/正式提交。干净重建复用原OS/WSL/Docker/链/已核验wheel/公开卷，不能称空白机器验收。

完整修改、运行命令、证据、已知问题和下一阶段依赖见docs/phase9-acceptance.md；API见phase9-contracts.md和spec/audit/openapi.json；匿名源docs/reports、PDF output/pdf。最后交接见handoff顶部。阶段9本轮范围实现和验收结束，等待用户验收；不得自动进入下一阶段或削弱原安全门槛。

最终补充：privacy-final.json公开文件/构建上下文当前Key检查PASS、模板空/仍与clean-final相同、.env.local被Git忽略，无密钥或其摘要输出；初轮空白正则跨行误判已改逐行解析。source-manifest/evidence-manifest/acceptance-summary保留最终文件及证据摘要。runtime-final.json仅5容器（8080审计+四Besu）运行，8082辅助和8081清洁实例已停止，卷全部保留；最后git log仍因无HEAD退出1，不是业务测试失败。

以下阶段9“进行中”为保留的历史过程。

## 当前阶段9（2026-10-26，继续验收中，尚未完成）

用户已授权阶段9只读React控制台、一键部署/冒烟/演示、匿名设计/测试报告和干净重建。已重读六份上下文、现有实现和测试；Git仍无HEAD/0跟踪。新增audit_projection/audit_verify/audit_console、dashboard、export/deploy/smoke/demo/rebuild/observer脚本已部分实现；本轮恢复基线231pytest通过（results/phase9/resume-baseline），两冻结check通过；阶段9模块19pytest与前端3测试通过。阶段8以下为历史，不再代表当前授权范围。

deploy-03真实一键PASS：新协议运行results/phase8/phase9/db841c2bbe，138案例/93本地MIME/59tx/236四节点receipt及原卷readonly复核；HTTP验证FINALIZED_OK/UNKNOWN/无预约/A-B历史分离。deploy-01/02失败保留：原RPC验证者查询可能返回null，原逻辑TypeError；仅新测试进程安装严格失败为CHAIN_UNAVAILABLE的read adapter，不伪造查询值、不改原核心文件。

clean-01 FAIL：旧流程引用空公开卷，容器缺/audit/catalog.json；venv/npm/231之前版本229pytest/71Hardhat/无缓存镜像已过但HTTP失败，不称重建通过。已增加PASS来源校验、catalog摘要/原卷预检、就绪等待/容器诊断；下一步clean-02。当前deploy-04进程正在8082部署修正未知副作用显示及自动浏览器验收版，必须检查deployment.json最终状态。计划补原源码摘要、真实篡改/审计容器断网验证、最终干净重建、匿名PDF报告/文档/交接；不可提前标完成。不读取或输出.env.local/私钥；不删原卷，不扩大其他C工具。

## 最终阶段8状态（2026-10-26，技术验收通过，等待用户验收）

**完整一键 complete-experiment-01 PASS，实际退出0**：真实DeepSeek预检→真实C前置→正式模型A/B/C→独立协议/故障/性能轨全部0退出、原卷readonly/四节点receipt/签名/承诺/CSV统计重算PASS，三子轨源码摘要无漂移。命令`.venv/Scripts/python.exe scripts/run_phase8.py --track real_llm --out results/phase8/complete-experiment-01`。不再缺Key、不再缺真实模型前置，不进入下一阶段。

最新正式模型轨real-abc：12任务/36模型请求/12读取/12本地MIME/C8真实tx/32节点receipt，高度13951→13984。A/B/C各ASR0/3 [0,56.15%]、TCR4/4 [51.01%,100%]；模型未提出越权调用，UER/UBR无分母，不计作网关阻断。完整官方utility INCOMPATIBLE，原112判定器/数据不改。C前置4样本单列，不池化ASR。协议轨138案例/93MIME/59tx/236receipt，高度13992→14069；共同UER A6/9、B/C0/9，UBR A3/9、B/C9/9；B/C TDR6/6，含故障TCR A/B28/31、C25/31，各60次重放无新增效果。协议性能n10 P50/P95/P99ms A39.13/61.21/73.82，B307.13/354.05/363.10，C3393.44/4392.79/4549.76；模型n1尾分位数不具总体推断力。

最终212pytest（8.65s，live-final-pytest.txt/xml）、71Hardhat（live-hardhat.txt），spec与policy --check PASS，58模块测试PASS；扫描未忽略文件无当前Key。临时扫描首轮缺sandbox包路径，补齐后成功；Git仍无HEAD/log失败，不是业务测试失败。文件/命令/原交易和MIME证据/已知问题/下一阶段依赖见docs/live-experiments.md及本次handoff。敏感工具全部本地测试卷，Key仅忽略.env.local，模板空Key。首轮live01判定身份格式失败与全部旧失败保留。

原卷保留：phase7-real chainguard-live-e5f343922e42，real-abc chainguard-live-fafa6f4895b2，protocol chainguard-p8-cd70d3aa953d；容器已停止，原四Besu保持。此后只做用户验收/必要核验，不推进其他C工具/React/生产隔离/完整官方基准/扩大实验。

下文“正在运行/真实模型未完成”均为历史过程，不替代本节最终证据。

## 最新真实模型进展（2026-10-26，本轮优先）

已确认根.env.local存在且Key非空/被Git忽略，example密钥为空；不再缺Key。deepseek-preflight-05真实/models与两次/chat/completions PASS。新增/补齐真实实验bridge/results/plan/judge、run_live/verify_live/run_real_experiments，模型参数/脱敏记录、中央proxy和必要测试；私有Agent journal在.local/live-agent，原冻结21+8/三合约/业务安全控制不改。

实际C前置deepseek-live-02 PASS，外部reverification PASS：4读取/4本地MIME/8真交易/32节点receipt/原卷readonly/统计重算。真实ABC deepseek-abc-01 PASS：12任务/36模型请求/12读取/12MIME/C8tx/32节点receipt，原官方112文件/判定器未改；各组ASR0/3（Wilson95上界56.15%）、TCR4/4，无越权尝试则UER/UBR无分母。58模块单测、全量212pytest/71Hardhat及冻结check PASS。初轮live01因官方内存邮箱不接受.invalid身份而FAIL保留，修正投影后02通过；没有外部发信。

当前正在实际验收完整一键命令：`.venv/Scripts/python.exe scripts/run_phase8.py --track real_llm --out results/phase8/complete-experiment-01`（exec session27119）。按顺序真实预检→phase7-real→real-abc→protocol；子日志在该目录。必须读最终manifest及两轨verification确认后填最终证据，不能提前标完整通过。既有协议run04/先前模型01是历史独立运行，不合并ASR。完整官方utility/大样本/其他工具/React仍未实现，等待用户后续指定。

详见docs/live-experiments.md；新源码检查/原卷/链/测试继续按handoff步骤，不能凭此条跳过复验。

## 阶段8最新状态：协议轨通过，DeepSeek预检通过，继续真实任务（2026-10-26）

最新用户已正确填写根.env.local，并明确此前误填.env.local.example。实际preflight-04 **PASS**：/models及两次/chat/completions均HTTP200，provider_model=deepseek-flash，真实模型发起diagnostic_echo并收到真实本地结果。已修正临时模板检查脚本导入路径，并在私有文件确有Key后清空example中的残留Key，只输出bool；Key可用/模板空。不能继续声称“缺密钥阻塞”。接下来已获授权：原Runner/Proxy真实正常任务与注入→官方AgentDojo适配原判定器→同模型/参数/数据正式A/B/C。尚未完成这些任务，预检不是ASR样本。以下“等待Key”为历史过程。

最终实际结果：`results/phase8/run-04/run_manifest.json`与`verification.json`完整PASS，138行=46配对样本×3组，93封本地MIME（A40/B28/C25）、59笔真实链交易、236份四节点receipt；chainId20261026、共同高度12505→12602，独立复核12603。原卷readonly/SQLite mode=ro、参数/结果/证据承诺、原审批与工具签名、真实calldata/nonce/链状态及统计重算通过。容器退出0，卷chainguard-p8-6765c7f69744保留；未重置原链。最后197 pytest passed（final-checks/pytest-complete.txt/xml）、71 Hardhat passing（final-hardhat.txt）、冻结生成/共享策略检查通过；运行源码摘要无漂移。

共同UER/UBR分母每组9个，A为6/9与3/9，B/C为0/9与9/9，Wilson95保留0/9上界29.91%；B/C FAR0/6、TDR6/6；各60次网关/工具重放无重复副作用。含故障TCR A/B28/31、C25/31，C额外查链失联fail closed。n10性能P50/P95/P99 ms为A37.12/50.50/52.74、B336.11/375.58/376.19、C4474.34/6111.47/6911.51；CSV含完整区间/均值/标准差/最大值/失败率，不称生产尾延迟。ASR未测/n0。

DeepSeek配置/安全加载/真实预检已实现，用户两次说重新填写后预检02/03仍BLOCKED/LLM_API_KEY_MISSING，api_called=false。安全检查进程、Windows用户/系统变量及已知文件字段均为空，原D:\CCF\.env.local仍不存在；为结束路径混淆，随后**独占创建该路径空密钥配置**（不覆盖已有文件）、确认Git忽略并请求Codex打开（返回queued）。此后应只检查是否已保存Key，再用新结果目录运行check_deepseek.py，禁止打印密钥。真实连通性/ToolCalling/正常和注入/AgentDojo/正式A/B/C均未完成，阶段7/8不能完整标记通过。用户已授权配置后的API调用，不需重复询问许可。

完整修改、真实命令/指标/限制与下一步见phase8-acceptance.md；一键协议报告python scripts/run_phase8.py。run-01孤立TypeError根因未定位；run-03读链复核失联（可能WSL停止），均保留FAIL；原WSL保活/只读有限重试后run-04通过。协议轨等待用户验收，模型轨等待实际密钥并继续已授权前置，不进入其他业务阶段。以下阶段8开发过程与阶段7以下均为历史。

## 阶段8开发过程记录（历史，不替代上文最终结果）

最新补充：用户已指定DeepSeek/deepseek-flash/https://api.deepseek.com、Key环境变量CHAINGUARD_LLM_API_KEY及根.env.local；实际均未检测到Key/文件。已新增无密钥.env.local.example、明确Git忽略、安全加载/脱敏模块local_config.py、固定deepseek_config.json与scripts/check_deepseek.py及4项测试；预检deepseek-preflight-01真实返回BLOCKED/LLM_API_KEY_MISSING，api_called=false，不冒充API成功。正常任务/注入、AgentDojo真实模型及正式ASR仍未完成。22项配置/脱敏+协议单测通过。

协议run-02 138实际行/93MIME/59tx、236份四节点receipt及原卷mode=ro复核PASS，强化复核verification-final.json同样PASS；之后增加shared_tool_policy共同9案例分母。run-03 138行业务均成功，但最终只读复核遇到CHAIN_UNAVAILABLE，整轮FAIL保留；后续观察四原节点同步新启动且无OOM，WSL运行期重启/停止是可能原因。脚本现调用原ops.wsl_session保活，并对只读RPC有限重试，不改生产授权校验。最终run-04正在新目录/卷运行（session84408），不得提前标记完成。新增共同分母后全量192 pytest通过、71 Hardhat通过；最新配置/只读RPC测试加入后还需最终全回归。

已按协议重读上下文/Git/源码和原设计指标；当轮resume-baseline为180 pytest/71 Hardhat通过，冻结21+8检查通过，四Besu在线（共同高度11776）。Git仍无HEAD/0跟踪。未配置模型，已再次异步询问；未收到答复时继续protocol_replay真实工具/链实验，真实LLM仍为阶段7待做前置，不以固定trace计算ASR。

已新增evaluation/replay.py、phase8_plan.json、phase8.Dockerfile、metrics.py与两组tests，scripts/run_phase8.py/verify_phase8.py，phase8-contracts.md/runbook.md。15项实验/统计单测实际通过（experiment-unit-03.txt/xml）。run-01真实138行、93封本地MIME，其中C pending-finalize/1在原audit交易成功后报告TypeError，整轮FAIL，原目录/卷保留，不作为通过证据。已增加无密钥stack诊断、原hash确认短暂不一致的有限轮询、重启后的真实工具与网关各10次重放，run-02正在运行，尚未完成独立复核。不得宣称阶段8完成或已有正式LLM指标。性能区间已改为固定工作负载trial bootstrap，比例仍scenario cluster；ASR为NOT_MEASURED。后续必须分析所有失败、完成原卷只读/四节点receipt独立复核及全回归，再更新最终证据。

## 当前阶段7：本轮范围技术验收通过（2026-10-26）

用户已授权最小 Runner/Proxy、固定 trace 和 AgentDojo 适配；本轮不做真实 LLM 攻防，真实模型接入仍是阶段7必做后续子任务、阶段8正式 A/B/C 的前置条件。固定 trace 不计入攻击成功率，attack_success=null，llm_sample_count=0。

本轮恢复基线162 pytest / 71 Hardhat通过，冻结生成/共享策略检查通过；Ubuntu已停止，使用原chain up恢复四节点，无链重置。Runner/Proxy/LLM/mapper当前18项单元测试通过；非root/无网络/只读根容器的ReadBroker 6项通过。run-01因测试JWT1800秒超过现有900秒限制失败，已改测试脚本，未放宽认证。run-02三场景通过：3封真实MIME/6笔真实Besu交易；agentdojo-run-01映射目标通过：1封真实MIME/2笔交易。verify_phase7已用四节点实时receipt、原工具卷只读挂载、真实签名/结果与证据承诺分别复核24+8份receipt，PASS。

AgentDojo官方PyPI 0.1.35 wheel哈希锁定，benchmark v1.2.2 workspace；112份原文件匹配、MIT许可证保留，73个独立Windows Python3.14 wheel哈希锁，pip check通过。原加载器与安全/utility判定器内存正负对照通过；不计入真实副作用或LLM指标。官方get_file/send/delete可映射，user_task_33附件、35未接入C R3、16 search_emails等明确INCOMPATIBLE；不改官方判定器或丢弃不支持字段。

最终联合验收final-run-02 PASS：4场景、4真实文件读取、4本地MIME、8笔真实Besu交易，共同高度4526→4560；越权发送/删除拒绝、Runner重启无重复邮件，Agent对工具/节点DNS及实际IP直连隔离，review/pending/reserve越权拒绝。final-verification.json PASS：32份实时四节点receipt、跨组织签名/nonce/状态、工具原卷readonly挂载与SQLite mode=ro、回执签名/结果和证据承诺/MIME/4文件未删除核验。正常reserve=0x7bf45d07a814a3ed799f8e6a76c53f04a2611a9ed1a2ec2b6e922aadecdeef9b；finalize=0xfa5771d0d252fcc9bf100056b73839f9baaa3131ba030aed02797cc8182c37d2。

最终Agent/mapper21项、全量pytest175 passed（final-pytest-02.txt/xml）、Hardhat71 passing（final-hardhat.txt）、容器读取6项通过，冻结21+8及原合约保持。AgentDojo独立哈希锁安装/pip check与最终原判定器自检PASS。final-run-01四业务例成功后IP探测变量遮蔽失败；改名后run-02通过。首次final-pytest为174过1失败，LLM变量与原严格env模板不兼容；拆到agent/.env.example后175通过。旧失败均保留；未放宽原认证/策略/协议。非OK回执保守null的最终补充由3项参数化单测验证，未声称OK链路覆盖未实现工具错误场景。

修改入口和完整文件组见phase7-acceptance.md；字段/状态与模型扩展点见phase7-contracts.md，复现/只读核验见phase7-runbook.md。本轮实现与验收结束，**等待用户验收**。固定trace attack_success=null、llm_sample_count=0；真实LLM接口只做本地HTTP协议测试，**真实LLM攻防测试尚未完成**，阶段7后续必做、阶段8正式A/B/C前置。没有开展正式A/B/C/ASR/性能统计。Git仍无HEAD/0跟踪，不自动提交；源码/证据摘要在results/phase7，旧阶段清单不重写。

下文阶段6及更早记录均为历史。

## 当前阶段6（2026-10-26，优先于下文历史记录）

**R2 mail.send首个完整C闭环实现、自动测试、真实Besu/副作用验收和独立复核通过，等待用户验收。未进入下一阶段。** 用户明确授权阶段6，下文旧阶段5“尚未授权C”的文字仅为历史。

新增chain_crypto/rpc/store/service/api/transport、phase6_server、独立chain_mail强制工具、10项primitive测试、真实容器故障验收及只读核验脚本。实现同一意图三方EIP-712跨组织审批、真实reserve确认、工具不同节点对独立核验当前权限/参数/TaskGrant、SQLite原子持久幂等MIME与真实签名回执、AuditRegistry.finalize/reconcile。UNKNOWN只查询原日志；审计断链保留队列，送达前中断只重投原签名字节，不重派发工具。详见phase6-contracts.md/acceptance.md/runbook.md。

实际测试：初始144 pytest/71 Hardhat；恢复后149 pytest/71 Hardhat；新模块10通过；最终 **154 pytest passed**（final-pytest.txt/xml）、**71 Hardhat passing**（resume-hardhat.txt）。冻结21+8 SHA-256匹配，生成和共享策略检查PASS。原合约/ABI/EIP-712/黄金向量/依赖锁未修改。

最终 **results/phase6/run-06/report.json PASS**：原四Besu chainId20261026、共同高度3556→3600，5次reserve+4次audit+1次markUnknown成功及2次重放回滚，共12笔真实交易。4封本地SQLite MIME，每个成功动作1封；越权/工具断链无投递；错参数/身份/预约拒绝、重启幂等、篡改回执UNKNOWN原回执恢复、审计送达前/后丢响应同hash恢复全部通过。**verification-06.json PASS**：48份四节点实时receipt、签名/链状态及原邮箱mode=ro/结果证据承诺/MIME独立复核。没有把HTTP202或txhash当最终确认。

正常reserve `0xd981973e4ed994a4f50606e92442803d3919314aa2b9f6dd02a1bfbce8e4a499`（3567/status1），finalize `0xaaa2befc5b713bea34d6e514c28b6b2004d5512ef0045281ad3865182754697a`（3568/status1）。部署仍使用下文三个原阶段5合约地址。副作用原件run-06/mail-1至4.eml；原始完整receipt/report在同目录。

失败保留：primitive默认GBK读取4错误已改UTF-8；run-01健康TLS超时、run-02后续exec失败；run-03旧3邮件版PASS；run-04恢复期先收到CHAIN_UNAVAILABLE导致预期错误码失败；run-05代理资源增长达1GiB、待预约超时。已将HTTP代理改为固定HTTPConnection/显式close、必要TLS上下文缓存，有限等待恢复仍强制安全拒绝；run-06 QA58.35MiB且三容器无OOM。完整原因见验收文档，不覆盖旧证据。

本轮发现并修复草稿过早标EXECUTING与冻结guard的语义偏差：持久dispatch_started时仍RESERVED；真实回执才确认执行，重启不重派发。未重定义协议、放宽时效/跨组织/工具二次校验。

限制：仅本地数据库邮箱一次性原子效果，不外推第三方SMTP；单worker/专属relayer；未派发动作的自动过期/撤销收尾TODO，无原回执UNKNOWN保持未知。R0/R1/R3 C工具、Agent、React、完整审计/metrics和性能/LLM实验TODO。测试JWT15分钟/证书2天、密钥/四节点同机不代表机构独立运维。私钥/令牌/盐仅忽略.local目录或受控卷，公开MIME为合成数据。Git仍无HEAD/0跟踪，不自动add/commit。

下一步：等待用户验收并明确指定后续阶段；新会话先按handoff复验，不能复用旧通过记录代替当轮测试。源码/证据摘要见results/phase6/source-manifest.json、evidence-manifest.json和integrity.json。

## 阶段5历史记录（以下不是当前阶段状态）

更新时间：2026-10-26，Asia/Shanghai。当前阶段：**阶段5三个业务合约已实现，自动测试和本地四节点Besu技术验收通过，等待用户验收。** 用户已明确授权阶段5；历史交接中的“未授权阶段5”不再适用。没有进入C网关/工具集成、Agent或前端阶段。

## 交付与边界

| 阶段 | 当前可检查事实 | 本轮验证 |
|---|---|---|
| 0 | 冻结协议/类型/API/golden vector | 原21份SHA-256匹配，生成输出匹配；原文件不改 |
| 1 | FastAPI健康、工程/依赖锁/环境 | pytest与Hardhat回归；没有新依赖或环境安装 |
| 2 | 本地真实工具/SQLite永久幂等 | 原实现保持；本轮没有重跑工具容器副作用测试 |
| 3 | 中央A/B、任务ABAC/RBAC/签名审计 | 共享8份输入摘要匹配；本轮没有重跑HTTP容器端到端 |
| 4 | 原四Besu QBFT真实网络 | 本轮4节点身份、peer、验证者、genesis/共同区块和真实新交易验证；没有重做阶段4故障注入 |
| 5 | PolicyRegistry/ExecutionRegistry/AuditRegistry及治理协议、测试/部署/独立验证 | 144 pytest、71 Hardhat通过；27笔真实Besu交易，108份四节点receipt复核；等待用户验收 |
| 后续 | C网关/工具独立查链、真实工具回执签名队列与证据/对账服务、Agent/React/实验 | **TODO，未开始，需用户指定阶段** |

阶段5详见docs/phase5-design.md、phase5-contracts.md、phase5-acceptance.md。逐个核心字段/状态guard/治理ABI和后续依赖均在phase5-contracts.md，不另定义协议。

## 实际运行与结果

- 修改前：build_specs.py --check PASS；freeze_phase3_policy.py --check PASS；pytest **144 passed**；npm.cmd test **41 passing**。证据results/phase5/baseline。
- 编译：npm.cmd run compile:interfaces，新增12个Solidity单元成功，solc0.8.28/paris；原锁OpenZeppelin5.4.0/Hardhat2.26.3/ethers6.15.0不变。
- 模块：hardhat test --grep 'Phase 5 PolicyRegistry' **7 passing**；ExecutionRegistry **15 passing**；AuditRegistry首次7通过/1失败，调整测试隔离分支后**8 passing**。日志policy-test.txt/execution-test.txt/audit-test.txt；首次失败保留audit-test.initial-failure.txt。
- 完整Hardhat：**71 passing**（原41+新30），results/phase5/hardhat-final.txt。
- `node.exe scripts/deploy_phase5.cjs --out results/phase5/besu-run-01`：**PASS**，27笔真实链交易=17成功+10预期回滚，共同高度**1247→1274**。逐笔四节点原始receipt/ABI/公钥/代码摘要/健康快照在该目录；不以模拟链替代。
- `.venv/Scripts/python.exe scripts/verify_phase5.py results/phase5/besu-run-01`：**PASS**，独立eth-account/eth-abi核对部署域摘要/签名、四节点代码、108份实时receipt和规范区块成员，原21+共享8冻结输入匹配。python-verify.txt及运行目录python-verification*.json。
- `scripts/check_phase5.ps1 -VerifyRun results/phase5/besu-run-01 -EvidenceDirectory D:/CCF/results/phase5/checks/final-20261026`：**PASS**，pytest **144 passed**、Hardhat **71 passing**、冻结输出/策略及Python/Besu复核通过。原始日志和pytest.xml在该checks目录。
- 最终文档/历史证据/新文件摘要核验在results/phase5/integrity.json及source-manifest.json、evidence-manifest.json；不重生成阶段4历史摘要。

重复检查不是独立实验样本，27笔交易不是27次真实工具动作。没有测性能、LLM攻击率或统计显著性。

## 实际部署

chainId=20261026；RPC回环8545–8548；genesis hash `0xcb4778cbcf96b2891907209e06448c518e82f7fa633c376efe4621761e072173`。

| 合约 | 地址 |
|---|---|
| PolicyRegistry | 0x68EAD07579A2B75bA4B024F8e02D14fb60a72dAa |
| ExecutionRegistry | 0x5effbc396C8532801C2a5e7A4d903b7c8702878A |
| AuditRegistry | 0x5d505B4ad2c4596b3bA3742ca5B338eB4d05f2eE |

R2预约交易`0xcfb64f9e1000036058ceb984edd7edec9d64da3746deaa81bd74ed96d276cbeb`，block1253/status1。REJECTED签名夹具确认`0xaea17cfa244875ca289d8f7b0074df503b89923c6ef4be859df655dbc7694ab6`，block1266/status1。完整receipt不能仅凭本表代替，接手必须实时查询。

## 实现与安全约定

- Policy：双组织当前GOVERNANCE_ADMIN签同一独立GovernanceChange，绑定完整变更ABI哈希/域/nonce/治理epoch/时间。构造仅引入两组织根管理员，禁用直接grant/revoke/renounce；单方只暂停，解除必须治理；治理批次不得摧毁最后两组织能力。
- Execution：同意图请求者/全部审批签名；R2业务安全两组织，R3第三账户人审；所有提供签名均当前有效、有scope、不同地址；排除requester/agent/TOOL_SIGNER。当前策略epoch/工具/范围/risk/时效，actionId和nonce永久消费；回滚不消费。
- Audit：当前具体工具绑定签名人、承诺/时间/版本；只它能修改链状态；RESERVED→finalize，UNKNOWN→reconcile；终态相同回执幂等，冲突拒绝；未知原因保留，nonce不释放。实际部署回执时间容差0秒。
- Execution与Audit地址不可变且构造互查，无单方设置入口。原ActionIntent/ExecutionReceipt/状态机/golden vector和中央B/C共享输入未改。
- **本阶段回执为合约测试夹具，实际Besu用REJECTED表明无工具派发，不声称真实邮件/删除。** execute_reserved仍拒绝链执行；TaskGrant、参数JCS/盐、当前角色/撤销工具重验、真实回执队列都是后续强制条件。

## 修改与问题

新增3合约、spec/phase5/governance.json、tests/solidity/registries.spec.cjs、scripts/lib/phase5.cjs、deploy_phase5.cjs、verify_phase5.py、check_phase5.ps1、3份phase5文档及results/phase5证据；更新README和architecture/contracts/decisions/progress/handoff。完整文件列表和摘要见新source-manifest.json。

审计首次测试失败原因：旧回执executedAt早于另一个动作issuedAt，先触发InvalidReceipt；重新在两个动作建立后签名再改ID，隔离重放分支通过。合约没有放宽时间检查。普通沙箱exec启动仍报helper_unknown_error，按工具权限流程获准执行后完成；无待解决审批拒绝。

原阶段4源码清单的README因阶段5说明发生预期变化，旧清单保留；其余15份链源码/原21份证据不改。Git仍无HEAD、0跟踪文件，git log无提交；没有自动add/commit，空diff不证明无变化。阶段5源码/证据SHA-256辅助恢复，缺Git历史仍是限制。

测试身份密钥在忽略目录.local/phase5/<run>/accounts.private.json；测试资金账户仍.local/phase4，节点密钥仍独立Docker卷。四节点/批准者测试密钥同机，不能声称独立机构运维或生产级认证/密钥托管。

下一步：等待用户验收阶段5；获指定后再接入C网关和工具真实链核验，不因合约通过就自动给敏感工具放行。历史阶段4与上下文维护证据仍在results/phase4及results/context/2026-10-26，本轮不将其历史通过冒充新测试。
