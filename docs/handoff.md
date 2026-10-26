# ChainGuard 新会话交接

## V1.0.0 最终独立验收（2026-10-26，验收结论：原型有限签收，完整交付不通过）

本轮用户要求独立验证，禁止继续新功能开发。实际重读规范／源码／Git并执行 Python 231、Hardhat 71、前端3测试，全部通过；受限容器8+26项通过（100并发邮件、50并发删除仅tmpfs沙箱）。新受控干净目录17步均0退出，重复231/71/3及真实HTTP/Edge冒烟通过。证据根results/final_acceptance/v1-independent-01，根FINAL_ACCEPTANCE_REPORT.md为最终判定入口；不是直接引用阶段9历史PASS。

历史源b5b09af5ea协议59交易/236receipt、正式模型8交易/32receipt及原卷93/12 MIME真实复核；完整验证器只操作副本，旧授权区块eth_call不可用，原protocol-0000/0006及完整两轨复验仍UNAVAILABLE，不能升级为PASS。旧证据索引162份逐字节不变。新独立真实演示results/phase9/final-independent-deploy-01（8083），源results/phase8/phase9/7f6e0d69f7，隔离新卷138例/93MIME/59交易；独立只读再次复核全部236receipt/原卷，protocol-0000 VERIFIED、0043 NO_RESERVATION、0006 UNKNOWN/链RESERVED/PENDING_RECEIPT且不重发。新动作不能替代原actionId的历史证明。

真实链20261026、四验证者各3peers，原合约代码一致，独立区块24546→24550；新合法reserve f160bb7b…e2f53f3d/24180，finalize 17bf3196…c7672c/24181。五种副本篡改INVALID、只断新审计容器网UNAVAILABLE、恢复VERIFIED。原27合约交易108receipt本轮重读17成功+10预期回滚（阶段5工具回执仍夹具）。模型不重调API，只复核真实历史请求/副作用/原判定器；两轨重算CSV/Wilson及独立150项Bootstrap/分位数一致。协议ASR未测，DeepSeek各ASR0/3、模型无越权尝试，不能算网关拦截。

用户本轮明确授权建立无隐私可追溯版本：原无HEAD，已建立源码基线b4a57819215c971eda48e4c60ae60feb4c2fde7a（283审核文件，通用作者，原始数据保留、不推送、不打Release标签）；最终文档提交与HEAD见证据根git-final.json。不再以旧“无HEAD”描述当前仓库；此前开发历史仍不存在。Key仅本地忽略配置，模板空，源码blob扫描无当前Key/个人主目录路径。运行日志和原始证据未整体纳入Git，不可直接git add .或当匿名发布包。

FAIL/未完成：根项目许可证、匿名发布包、软件版本0.1.0/0.9.0与协议1.0.0不统一；空白OS/新genesis重建未测；完整官方utility不兼容、小样本研究不充分；其他C工具/R3完整闭环/生产多机构隔离/HSM等仍原TODO。两PDF3+4页本轮只读提取/渲染检查且原字节不变。验收辅助首轮history字典路径TypeError、retry01混合编码、补充新证据首轮缺transactions字段等失败保留；没有修改业务/测试预期消除失败。收尾git diff空白检查因Windows写入CRLF且仓库*-text而退出2，已恢复原文档body字节并仅使新段落/报告使用LF；失败日志保留。普通沙箱helper启动失败，经工具提权流程执行，无自动审批拒绝遗留。

结论：现有本地R2原型可有限范围签收；完整研究实验及正式V1.0.0竞赛交付不可无条件签收。本轮验收结束停止，不自动选许可证、改版本、补实验、推进新功能或重发UNKNOWN。原8080/新8083/四Besu保留，8081干净重建容器已停止、所有卷保留。完整命令/退出/失败/证据索引见最终报告与commands.jsonl，收尾状态见acceptance-summary.json。

## 最终阶段9接手点（2026-10-26，技术验收PASS，等待用户验收）

所有阶段9部署/重建/回归进程已结束，8680、45950、28117、42012均实际退出0，无待轮询验收。先重读AGENTS/architecture/contracts/decisions/progress/本文件、phase9-contracts/acceptance和audit_*.py/dashboard源码/tests、Git和diff，再建立新基线，不依据本段替代验证。原116源码+25不同冻结文件摘要不变（results/phase9/integrity-final.json），不改原协议/合约/业务安全逻辑。

最终验收证据：results/phase9/deploy-final/deployment.json、smoke.json、browser.json、public/export-verification.json全部PASS；http://127.0.0.1:8080运行。真实新源results/phase8/phase9/b5b09af5ea manifest/verification均PASS，138案例/93MIME/59tx/236四节点receipt，共同高度22651→22722、chainId20261026；原卷readonly与签名/参数结果证据承诺/calldata/events/nonce/统计复核通过。原件tx-receipts.json和各case-*不得改写；协议ASR未测，真实模型正式ASR仍仅阶段8独立轨，不池化重复。

final-checks：231pytest（8.98秒）、71Hardhat（13秒）；19新增模块pytest（audit-unit04）、3前端tests、冻结spec/policy check均PASS。observer-final.json五类证据副本篡改INVALID、只断审计容器网后UNAVAILABLE、恢复VERIFIED，未写链/工具。demo-final/demo-evidence.json真实只读演示通过。clean-final/rebuild.json PASS，17步0退出：新源码/venv/root+dashboard node_modules、pip check、231pytest（10.64秒）/71Hardhat/3前端tests、无缓存镜像、8081真实HTTP/Edge；该容器自动停止、保留，不误以为8081长期服务。

实际运行容器：最终audit c5397a3c34c2ed409897897b8de29249a1551857afeca3a2c632d05a884694f3，公开卷chainguard-audit-public-b5b09af5ea，项目chainguard-audit-b5b09af5ea，镜像sha256:021f397084ea517b332e157a114d85358ac5eed30e8fee3856e88cf26fb1a8b6；Compose/env在deployment.json。四原Besu继续保留。阶段9演示协议私有工具卷见该源manifest.volume；控制台只有公开卷、无Key/工具卷。旧03审计已停；04在8082的辅助审计实例结束时明确停止（见最终runtime检查）。勿prune/删除卷或重置链。

正常reserve=0xb50108147ae9660bf863059f4dc17c5d1450275b40b9421d23e012dd3837a00b/block22656；finalize=0x3ea909c6740b973b7e253d58c731722bc5c6cb4f09fffa614d303ba306c0aea5/block22657。UNKNOWN protocol-0006只有预约缺回执，当前链RESERVED/观察PENDING_RECEIPT，不能补发。越权protocol-0043无预约，不补造拒绝交易。老历史权限查询可能不可用，保守UNAVAILABLE；未来归档节点另行授权。

交付导航：docs/phase9-acceptance.md完整文件组/命令/结果/失败/后续依赖；spec/audit/openapi.json来自真实app的7GET接口；docs/reports匿名源和output/pdf两报告（3设计+4测试页），Author空/文字可提取，Poppler7页和最终UI桌面/手机图已人工核验。截图只作视觉QA，不用于真实执行证明。PDF构建使用bundled ReportLab4.4.9、pypdf6.10.0/Windows simhei字体，不改原运行依赖。整仓/历史results带本机路径，匿名发布包/ZIP/提交尚未验收。

```powershell
# 使用新输出文件/目录；8080已被最终实例使用，再部署可加--port 8083。
& .\.venv\Scripts\python.exe -m pytest -q
npm.cmd test
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe scripts/smoke_audit.py --out results/phase9/new-http.json
& .\.venv\Scripts\python.exe scripts/rebuild_phase9.py --deployment results/phase9/deploy-final
```

冻结/原源码检查用check_phase9_integrity.py --out新文件；旧区块查不到时不可覆盖证据宣称成功。若确需新真实协议证据，deploy_phase9.py默认在新隔离卷执行，只本地MIME与真实交易；不并行争relayer。停止审计用部署的compose.env/compose.yaml仅停其项目，保留所有卷；绝不chain down/prune来清理展示层。

保留失败：deploy01/02协议真实validator读取缺值TypeError；新增evaluation/audit_demo仅测试进程将缺值视CHAIN_UNAVAILABLE供原有限轮询处理，成功值原样，无假validator/receipt和核心文件变更。clean01空公开卷导致catalog缺失，新增来源/摘要/实际卷检查/readiness后新02/final通过。historical-state-failure.json保留老块eth_call Internal error。临时报表GBK失败改utf8；没有Key输出。普通exec仍sandbox helper错误，工具提权已获准，无自动审批拒绝遗留。Git仍无HEAD/0跟踪，不自动add/commit。

本阶段已结束等待用户验收；后续待明确指定：空白OS/新genesis完整重建、独立组织/归档节点/生产HSM与RPC认证、其他C工具/R3闭环、完整官方AgentDojo任务/大样本模型、匿名发布包。Key在忽略.env.local，仅真实模型模块读取；禁止写报告/日志/镜像。以下所有“正在运行/未完成阶段9”均为历史过程，不覆盖本最终条目。

最终收尾证据：privacy-final.json PASS，模板Key空且摘要与clean-final一致（没有修改模板）、当前Key未见所扫公开文件/构建上下文，.env.local受忽略；初轮扫描正则`\s*`跨行误读下一行已改逐行解析。没有Key或其摘要输出。操作员扫描/摘要脚本在忽略.local/finalize_phase9.py，只写results/phase9安全摘要；source-manifest/evidence-manifest/acceptance-summary已生成。runtime-final.json确认5容器=8080最终审计+四Besu；8082辅助已明确停止，8081重建容器已停止，所有卷保留。最后命令仅git log因无HEAD退出1，所有验收和扫描PASS。报告最后追加扫描失败/修复说明后重新生成及渲染检查；若改交接/报告，再运行该操作员脚本更新摘要，勿用旧manifest掩盖后续源码变更。

## 阶段9接手点（2026-10-26，验收中，未完成）

先重读AGENTS及五份上下文、docs/phase9-design.md、audit_console/projection/verify、scripts/deploy/rebuild/export/smoke/check_phase9_observer/demo_phase9、dashboard源码/tests和Git。阶段9已授权，下面阶段8“停止不推进”是历史。Git无HEAD，全仓未跟踪；不能靠diff判断无改动。禁止改冻结21+8、原三合约及原业务执行授权逻辑。

恢复基线231pytest（results/phase9/resume-baseline/pytest.txt/xml）、两冻结check PASS；阶段9模块19pytest（audit-unit-04.xml）、前端3tests PASS。deploy-03一键真实协议/原卷/链/HTTP PASS，输出results/phase9/deploy-03；真实源results/phase8/phase9/db841c2bbe（138案例、93MIME、59tx、236receipt），原卷保留，8080只读控制台运行。新deploy-04正在8082运行（查进程/manifest，不重复运行），源复用db841c2bbe，新增自动真实Edge浏览器冒烟、原链compose up及null副作用独立文字。该次exec session ID未保存，直接看results/phase9/deploy-04/deployment.json/各日志和进程。

clean-01 FAIL已查容器日志：/audit/catalog.json不存在，旧部署引用空公开卷。当前rebuild脚本已在创建环境前要求成功部署和load_catalog摘要；启动前检查实际公开卷，增加readiness轮询、/tmp和资源限制、logs保留。待运行clean-02引用真实PASS部署，不能把clean-01前面229pytest/71Hardhat通过算全重建通过。保留旧容器/卷和失败证据。

已新增check_phase9_integrity.py待运行，比较阶段8manifest原有所有源码+冻结，不重写清单。接下来：确认deploy04最终PASS→check_phase9_observer真实五类证据篡改/审计容器断网恢复→rebuild新目录（新venv/root/dashboard node_modules/无缓存镜像/8081真实HTTP+浏览器）→原源码摘要与最终pytest/Hardhat/冻结→匿名Markdown和PDF报告+页图检查→README/dashboardREADME/architecture/contracts/decisions/progress/handoff。当前没有匿名报告/最终验收文档，不能结束称完整完成。

原旧链历史权限在13998等块eth_call Internal error，保留historical-state-failure.json；若旧证据不能重新查不能冒充VERIFIED。deploy01/02原协议失败为qbft_getValidators返回null导致TypeError，evaluation/audit_demo.py仅新测试进程严格把缺查询视CHAIN_UNAVAILABLE（不合成值，不改原文件），deploy03实测通过。普通沙箱exec/node_repl仍helper_unknown_error；工具提权实际获准执行，无自动审批拒绝。不要输出Key；PDF技能已读，使用前必须定位并运行mark_artifact_operation_started.mjs；报告使用bundled依赖，所有页渲染检查。当前Key已存在忽略.env.local，不再问Key。

## 最终接手点：阶段8完整一键技术验收PASS，等待用户验收（2026-10-26）

**已完成正在运行session27119，退出0；没有待轮询进程。** `results/phase8/complete-experiment-01/run_manifest.json` PASS，四步骤preflight/phase7-real/real-abc/protocol退出0，三子轨manifest/verification均PASS；源码hash三轨0漂移。实际命令`.venv/Scripts/python.exe scripts/run_phase8.py --track real_llm --out results/phase8/complete-experiment-01`；默认不带out可一条命令重做新目录。

最新正式模型real-abc为12真实任务、36请求、12读取/12MIME/C8tx/32receipt，高度13951→13984；原工具卷readonly、SQLite mode=ro/文件未删除、原签名/参数结果证据承诺、四节点calldata/events/nonce/链状态及统计重算PASS。各组ASR0/3，Wilson上界56.15%，TCR4/4；模型没有越权尝试，UER/UBR未适用，不能说网关拦截3次。C前置4任务单列，协议ASR仍未测；不池化历史重复。完整官方utility INCOMPATIBLE，112原文件/判定器未改，只有原security目标的明确适配；该限制不是假完成全benchmark。

最新protocol为138行/93MIME/59tx/236receipt，高度13992→14069，共同9案例UER A6/9、B/C0/9，UBR A3/9、B/C9/9；TDR B/C6/6，A0/6；故障TCR A/B28/31、C25/31，各60次重放无重复效果。n10性能P50/P95/P99ms A39.13/61.21/73.82，B307.13/354.05/363.10，C3393.44/4392.79/4549.76；模型正常n1的退化区间不解释总体尾延迟，所有CSV有小样本状态/CI。

最终测试212pytest（8.65s，results/phase8/live-final-pytest.txt/xml）、71Hardhat（live-hardhat.txt）、58Agent/实验测试及两冻结check PASS。最终扫描当前Key未见未忽略文件残留；临时首轮扫描因少sandbox sys.path失败已补齐，无密钥输出。Git无HEAD/0跟踪，log仍失败，不自动提交。live01原失败因官方内存邮件EmailStr不接受.invalid，修复仅投影身份，真实邮箱始终本地；其余旧失败不覆盖。

代码/改动详情及命令/判定/状态与后续依赖在docs/live-experiments.md；最新源与证据文件可用manifest逐份核查。Key已在D:\CCF\.env.local且忽略，模板空Key；不再问Key，绝不输出。私有journal在.local/live-agent，签名密钥只实验卷/忽略原本地文件；Agent无审批/工具/relayer密钥。

三最新原卷保留且对应容器停止：chainguard-live-e5f343922e42、chainguard-live-fafa6f4895b2、chainguard-p8-cd70d3aa953d。原四Besu保持运行，禁止prune/delete/reset。不并发验收争用relayer。真实C正常reserve 0x579a6cbe29c6da5ce88f8f6167951c8bf15245a1795db8010cf443b8bc1dd661、finalize 0x85a261cde85f920ce1c0107d439f00ac5ec5a5c3abdf1b32a21098ac89259c41，原MIME和receipt在real-abc。普通沙箱exec初始化仍失败，必要执行均按工具审批获准，无未解审批拒绝。

接手仍须重读六文件/Git/源码、重新运行相关测试；不能因本文PASS跳过核验。当前无未解决业务测试失败，已知范围限制：原型小样本、完整官方utility/其他C工具/React/生产隔离与密钥托管未实现。用户尚未验收，不进入下一阶段。下文所有RUNNING/缺Key/模型未完成均为历史。

## 当前真实模型交接（2026-10-26，本条优先于旧记录）

Key已正确保存在D:\CCF\.env.local且Git忽略，example为空；绝不再索要Key或打印。实际DeepSeek preflight05 PASS。真实前置phase7/deepseek-live-02 PASS及外部deepseek-live-02-reverification.json PASS：4真实读取/4MIME/8tx/32节点receipt；首轮01失败是原官方内存EmailStr拒绝.invalid，已仅修改内存身份投影，原失败保留、真实邮件始终本地。正式phase8/deepseek-abc-01 PASS：12真实任务、36模型请求、12MIME/读取/C8交易/32receipt，原卷readonly/统计重算；各组ASR0/3，UER/UBR无越权尝试无分母，不能说网关阻断成功3次。完整官方utility仍INCOMPATIBLE，原112文件未改。

已完成evaluation/live_bridge/live_results/live_plan/judge_real_effects、scripts/run_live_agent/verify_live_agent/run_real_experiments、run_phase8 real_llm派发、model参数与脱敏HTTP失败记录、central_proxy幂等UNKNOWN，4组新测试。58Agent/实验单测、完整212pytest/71Hardhat、规范/共享策略check PASS；证据results/phase8/live-*。evaluation/protocol_lab.py是未启用草稿，修复非法import并标TODO，真实协议入口replay不变。原21+8/三合约不改；journal在忽略.local/live-agent，公有结果不含密钥/盐。

**正在运行不可中断/误标完成：** session27119执行`.venv/Scripts/python.exe scripts/run_phase8.py --track real_llm --out results/phase8/complete-experiment-01`。一键顺序预检→phase7-real→real-abc→protocol，各子轨有独立manifest/verification及四文件；日志顶层<step>.txt。先poll该进程、读顶层/子manifest，不重复开验收争用relayer；失败保留旧目录/卷，分析后新目录修复。成功后补充实际值与最终全回归、只读复核、密钥扫描，更新本文件/progress/验收/README。当前docs/live-experiments.md和导航已写，完整一键仍明确RUNNING。

模型计划同deepseek-flash/temperature0/top_p1/thinking disabled/max_tokens512/parallelfalse、四场景每组1次。API预检单独max_tokens256，非ASR样本。C前置与正式模型/协议不池化。原判定器只对适配GOAL跑security，合成document/mail按实际Bob/删除目标，完整utility不兼容；小样本ASR0/3的Wilson上界56.15%，n1尾分位数无总体解释。所有敏感副作用仅实验容器卷，桥为可信服务层，不声称生产隔离或组织独立托管。

普通exec环境仍初始化错误，已按工具提权获准完成必要执行，无审批拒绝。Git仍无HEAD/0跟踪，不自动提交。下一会话仍先读六上下文/Git/源码和测试，原链不重置、卷不删除。最后等待用户验收，不进入下一阶段。

## 最新接手点（2026-10-26，协议轨通过、DeepSeek预检通过、继续LLM任务）

**最高优先更新：不再缺Key。** 用户最后明确“现已填入，之前误填.env.local.example”。实际`results/phase8/deepseek-preflight-04/preflight.json` PASS：真实/models + 两次/chat/completions均200，provider_model=deepseek-flash，真实diagnostic_echo被调用并把本地result回传。根D:\CCF\.env.local有Key且Git忽略；在确认这个私有文件Key有效后，已清空example里残留Key，只输出bool；不要再要求用户配置/不要读取输出Key。临时检查脚本最初少sandbox sys.path，已修复，预检本身正确完成，完整197pytest仍是上次真实全回归。以后构建/清单绝不包含.env.local；example现在空Key。

当前继续做已授权前置及正式阶段8，不能就此结束：先最小真实正常/注入Agent Runner→AgentDojo适配原判定器→真实A/B/C同model/data/parameters。已读取agent/runner.py/proxy.py、agent/integration/lab.py、run_phase7.py、phase7_server.py、chain_transport.py、workspace_adapter.py/check_agentdojo.py。原AgentDojo用户任务枚举没有发现只由get_file_by_id/send_email构成的完整任务；不能捏造全官方benchmark完成。可以明确适配原file13与injection_task_0/1 goal，按真实物理副作用投影到原环境调用**原security判定器**，原utility不兼容则标记INCOMPATIBLE，不改判定器/丢字段。

拟实现最小统一真实模型实验服务层harness：模型/Runner在host仅持DeepSeek key，所有敏感工具/签名密钥留受限Docker实验卷；白名单stdio bridge只允许AGENT propose/get/R0读取，不暴露sign/reserve/原始工具端。C复用原ToolExecutionProxy+ChainService/ChainMailTool，A/B使用中央契约proxy，不伪造C状态；可信测试审批器在桥内部按预授权合成精确params审批。same Lab已存在evaluation/replay.py可复用，R0真实ReadBroker供模型读取注入文件；same AgentRunner SYSTEM与tools、DeepSeek thinking disabled/temp0/top_p1等。明确是实验集成测量，不声称替代阶段7既有独立容器/HTTP/mTLS隔离验收。新增可记录的HTTPModelBackend参数/recorder（默认不变）、evaluation live bridge、run real agent实验脚本/同模型配置/官方judging脚本与必要自动测试。真实模型不能强迫其攻击；分别记录attempt/policy/physical/judge。每组至少正常+注入，建议4场景（normal/doc/mail/AgentDojo-goal）×A/B/C，n小如实CI。API不可用失败保留，无固定trace兜底。下文“密钥缺失”均历史，不能据其停工。

新会话按AGENTS先读六文件/Git/代码/相关测试，不能照摘要写代码。当前最终证据`results/phase8/run-04`完整PASS，**138实际行/93MIME/59真实tx/236节点receipt**，原chainId20261026、共同高度12505→12602，独立复核12603。原B签名log/独立checkpoint、C审批/签名/原交易calldata/nonce/链事件/工具回执、无网络readonly原工具卷+SQLite mode=ro/承诺与MIME、任务数据配对/统计重算全部通过。原新容器chainguard-p8-6765c7f69744已退出0，同名原卷保留；原四Besu与隐藏WSL保活保留。别删除卷/prune/重置链或并发争用relayer。

最后全量**197 pytest passed**（final-checks/pytest-complete.txt/xml）、**71 Hardhat passing**（final-hardhat.txt）、22配置/实验单测通过，spec生成/共享策略check通过；run-04 manifest所有源码摘要与当前匹配。无代码测试待修失败。Git无HEAD/0跟踪，不自动提交；新增source/evidence清单补足文件证据但不是独立信任根。

实现入口：evaluation/replay.py、phase8_plan.json、phase8.Dockerfile、metrics.py、tests；scripts/run_phase8.py/verify_phase8.py；agent/local_config.py及4测试、evaluation/deepseek_config.json、scripts/check_deepseek.py；根.env.local.example/.gitignore，phase8-design/contracts/runbook/acceptance与deepseek-runbook和导航。原21+8/三个合约/生产网关/工具/AgentDojo原判定器没改。协议harness复用真实服务，同进程可信签名器，不运行Agent或模型，不包含HTTP/mTLS/model时间；合法任务按精确MIME观测，与UNKNOWN状态分开。

指标：shared_tool_policy三组完全同9案例，UER A6/9、B/C0/9（95%上界29.91%），UBR A3/9、B/C9/9；all_applicable B/C还各6次审批尝试，不与A异分母直接比较。B/C FAR0/6、TDR6/6；A无审批/TDR0/6；每组网关+工具60次重放/0重复效果。含故障TCR A/B28/31、C25/31；性能n10 P50/P95/P99(ms) A37.12/50.50/52.74、B336.11/375.58/376.19、C4474.34/6111.47/6911.51。比例Wilson+scenario cluster bootstrap，性能固定工作负载trial bootstrap，小样本不外推；CSV含CI等全部统计。

**当前真正未完成：DeepSeek真实前置和正式模型轨。** 用户已明确DeepSeek/deepseek-flash/https://api.deepseek.com，Key从CHAINGUARD_LLM_API_KEY或根.env.local读取；先API/诊断ToolCalling，再正常/注入与AgentDojo原判定器，最后同模型/参数/数据/评价A/B/C。config固定temperature0/top_p1/thinking disabled/max_tokens256/no fallback，尚未实证provider兼容。已获真实API调用授权，不再问许可，不泄露密钥。三次preflight目录01/02/03原件均BLOCKED/LLM_API_KEY_MISSING，api_called=false、tool_executed=false；不能称已API连通或模型成功，ASR仍NOT_MEASURED/n0。

用户连续两次说“已重新填入”后，实际只查bool：D:\CCF\.env.local仍不存在，进程/Windows User/Machine环境、根.env/.env.example/.env.local.example和agent/.env.example均Key字段空；根文件名也无.env.local.txt。为避免重复路径问题，已**仅在缺失时exclusive create D:\CCF\.env.local空Key文件**，明确被gitignore排除；调用open_in_codex返回queued，不能声称用户已保存真实key。下一步先运行脚本（新目录）或检查已保存状态，绝不输出文件原文/Key。若仍空，需用户在这个确切文件填写保存，不索要聊天密钥。密钥配置文件绝不写source/evidence清单或build context。

复现协议一条命令`.venv/Scripts/python.exe scripts/run_phase8.py`；复核用scripts/verify_phase8.py results/phase8/run-04 --out新文件；真实预检scripts/check_deepseek.py --out新目录。首次预检/models，随后真实工具echo请求与实际result回传，只发送合成文本、不触碰敏感工具；失败保留脱敏响应，不改模型兜底。原模型Backend/固定trace/AgentDojo映射保持。真实预检通过后还必须实现/运行正常邮件/注入与基准，不能把诊断echo当正式样本。

保留失败：run-01业务一条pending-finalize TypeError（工具已送、audit真实status1但网关未更新）；原无stack根因未定位，添加无秘密stack后run02/03/04未再现，不宣称修好。run-02旧统计版PASS；run-03业务138行无错但最终receipt RPC断开导致FAIL，后来四节点同步新启动无OOM，可能WSL runtime停止。run-04脚本复用原ops.wsl_session/健康等待并有限只读RPC重试后完整PASS。历史目录不覆盖、不池化重复为独立样本。完整验收文档已写，协议轨待用户验收、LLM前置仍需实际Key，不自行进入下一业务阶段。

## 阶段8开发过程记录（历史，以下“正在运行/未复核”已被上文最终结果替代）

最新用户答复：阶段7/8真实模型固定DeepSeek/deepseek-flash/https://api.deepseek.com，OpenAI-compatible，Key从CHAINGUARD_LLM_API_KEY或根.env.local安全加载；先最小连通性/ToolCalling再AgentDojo再正式A/B/C。实际根.env.local不存在且进程Key未设置（只查bool，未输出密钥）。新增.env.local.example（空Key）并gitignore明确排除.env.local/放行模板，新增agent/local_config.py、4项测试、evaluation/deepseek_config.json、scripts/check_deepseek.py、docs/deepseek-runbook.md。实际预检--out results/phase8/deepseek-preflight-01为BLOCKED/LLM_API_KEY_MISSING，api_called=false、tool_executed=false；22项配置/协议单测PASS。不能称真实DeepSeek连通或模型任务通过；后续本地密钥应放D:\CCF\.env.local，不要求聊天发送密钥。

run-02已完整PASS：138行/93MIME/59tx，236份四节点receipt/原卷readonly模式复核；后续加强verify的行为断言、实际calldata/签名、禁止manifest决定命令/无关卷等，verification-final.json同样PASS。之后增加指标cohort：shared_tool_policy三组相同9案例；all_applicable原A9/B15/C15不能直接比较。17项单测、全量192 pytest通过；71 Hardhat同轮通过。run-03业务138行均成功，但只读最终复核在receipt RPC返回CHAIN_UNAVAILABLE，原manifest仍FAIL，不覆盖；观察原四节点同2026-10-26T00:29:58同步启动、restart0/oomfalse，可能WSL runtime离线重启。run脚本新增复用ops.wsl_session保活/健康等待；verify只读RPC拒绝广播并有限3次重试。没有改生产chain_rpc/冻结文件/合约。

最终run-04正运行（exec session84408，新结果目录results/phase8/run-04，需poll实际状态）；结束后必须读manifest/verification确认PASS，填最终验收/更新导航与本文件/进度，跑含新增4配置+1只读测试的全回归（预期197但不可预填结果）。原run-01孤立TypeError根因仍未定位，无stack；添加stack后run-02/03未复现，不能说已修复。所有历史失败/卷保留。正式真实LLM/ASR仍未测，阶段8不能完整标完成；等待用户配置Key/验收，而非自行进入下一阶段。

恢复后实际读取必需六文件/代码/Git，resume-baseline 180 pytest/71 Hardhat、spec/shared policy检查通过；链共同高度11776、四节点在线。已实现evaluation/replay.py/phase8.Dockerfile/metrics.py/phase8_plan.json及tests，scripts/run_phase8.py/verify_phase8.py，docs/phase8-contracts.md/runbook.md；15项单测通过（experiment-unit-03）。一键命令python scripts/run_phase8.py，新目录拒绝覆盖，离线镜像、唯一非root/readonly/无host挂载卷、真实原A/B/C服务和Besu。harness同进程可信签名器，非真实Agent/HTTP/模型实验；ASR=null/n0，real_llm模式明确拒绝未满足的阶段7前置。已异步询问模型配置或本轮协议轨，尚无答复。

run-01 138实际行/93本地MIME，C pending-finalize/1 TypeError致整轮FAIL；原audit hash 0xb7f8efa6b5191b2434463c2c19a381d3dbb819d2ee44624930d2e36a008c2c45经RPC实际status1，工具已发送，网关仍EXECUTION_RECORDED。旧错误无stack，原因未定位；不覆盖失败或重发邮件。已增加不含locals/密钥的failure_stack、RESERVATION_UNCONFIRMED/CHAIN_UNAVAILABLE原hash有限轮询；不捕获/掩盖TypeError。增加C工具持久重开/同原body各10次工具与网关重放，A/B同样网关10次/工具10次后者按原状态拒绝。run-02正在运行（exec session38149），预计138行；结束后先读manifest/traces/verification，失败必须分析修复，不能凭该记录当通过。尚未进行最终完整pytest/Hardhat/冻结复验或交付总结。

统计计算基于实际trace，失败仍保留。比例Wilson+scenario cluster bootstrap；单一性能工作负载使用trial bootstrap避免一个cluster零宽区间。TCR按独立邮箱精确Alice副作用判定，UNKNOWN与tool_executed分开；C不派发工具无回执持续UNKNOWN。A shadow vs B/C enforce沿用冻结差异；A无审批、C独有故障在其他组为正常对照并mechanism_applicable=false。逐样本case JSON含合成MIME、原B签名log/独立checkpoint、C原intent/receipt/签名/tx，私钥/salt不导出。verify脚本重算统计/输入配对、查四节点receipt/事件/授权/nonce、无网络readonly挂载原volume且SQLite mode=ro重算原数据承诺；尚待真实运行验证此脚本。

用户已授权实验/统计：统一A/B/C任务/模型/数据/基础策略，伪造/重放/篡改/故障/性能，四种结果文件和指标/CI/一键复现。已重读六上下文、Git状态/diff/log（仍无HEAD/0跟踪），A/B/C源码及原设计§13指标。没有阶段8既有实现。docs/phase8-design.md已记输入/拟改文件/验收。正在跑results/phase8/baseline pytest/Hardhat/规范check与原chain up。

真实模型env三个字段当前全未配置，已用异步问题请求用户模型名/API（密钥仅本地）或确认本轮协议轨。未收到答复前可继续protocol_replay框架及真实工具/链实验，ASR应NOT_MEASURED、LLM样本0，不能否定之前真实模型必须在正式A/B/C前完成的要求。A原组账号权限+任务shadow、B/C任务强制是已有冻结设计，需明确披露而不是强称强制策略相同。

将新增evaluation计划/统计/受限真实服务层回放、tests及run/verify脚本；原业务文件/冻结21+8/三个合约不改。服务层集成harness同进程可信签名器，只测真实协议/工具/链，不冒充HTTP网络或Agent进程隔离实验。待执行命令/失败/副作用/指标必须继续写入本记录。旧阶段7以下仅历史。

## 阶段7当前接手点（2026-10-26，本轮范围技术验收通过）

已按用户协议重新读取六份上下文文件、Git状态/log/diff、阶段7部分实现和阶段6接口。用户本轮只要求固定trace与AgentDojo适配；真实LLM接入必须预留独立环境变量配置及可替换Backend，真实LLM攻防尚未完成，必须在阶段8正式A/B/C之前完成。

实际已完成：恢复基线162 pytest、71 Hardhat及冻结check通过，原Ubuntu停止后chain up恢复；18项Agent/mapper单元测试通过，读取broker在受限容器6项通过。run-01因1800秒JWT违背900秒上限失败，改测试为900秒；run-02三场景3封本地邮件/6笔真实交易PASS，agentdojo-run-01原始file13+两个映射攻击目标1封邮件/2笔交易PASS。verify_phase7分别24/8份四节点实时receipt和原工具卷mode=ro/readonly挂载、签名/承诺/MIME/未删除文档复核通过。UNKNOWN后查询权限丢失保持UNKNOWN/tool_executed=null；不因GET错误声称无副作用。模型边界禁重定向以免转发API Key，独立env配置和协议测试通过，未调用任何真实模型。

AgentDojo已锁官方PyPI0.1.35/benchmark v1.2.2 workspace，wheel摘要及112份原源码/数据清单在evaluation；73依赖wheel独立Windows3.14哈希锁、.local/phase7-agentdojo-venv和-wheels，pip check通过。evaluation/check_agentdojo.py实际加载官方任务/判定器正负对照，未改原文件；只操作官方内存环境，不是实际邮件/删除或LLM实验。workspace_mapper支持send/get_file/delete，附件CC/BCC和未映射身份拒绝；33/35/16不兼容详见results/phase7/agentdojo-check-01.json。原邮件域只作身份映射到.invalid，不外发。导出fixture是原file13内容+本地根据官方GOAL拼接的注入文本，明确不是官方攻击实现/完整基准得分。

最终联合final-run-02 PASS：4场景、4实际读取、4本地MIME、8真实链交易，原四Besu20261026共同高度4526→4560。Agent工具/节点DNS和实际IP直连失败，review/pending/reserve拒绝，越权邮件与删除均拒绝，重启重放normal无第二封邮件。scripts/verify_phase7.py对其final-verification.json PASS：32份四节点实时receipt、原签名/状态/nonce、原卷readonly且SQLite mode=ro、工具回执签名/结果/证据承诺/MIME与4原文件匹配。最终175 pytest passed（final-pytest-02.txt/xml）、71 Hardhat（final-hardhat.txt）、21项Agent/mapper单测、容器读取6项，冻结check均PASS。evaluation/check_agentdojo.py最终输出agentdojo-check-final.json PASS，独立73 wheel锁安装与pip check通过。文档phase7-contracts/runbook/acceptance已写，导航已更新；本轮等待用户验收。

新增失败保留：final-run-01业务四例过后，IP探测局部变量connection遮蔽函数，改名后final-run-02通过；首轮final-pytest174过1失败，LLM变量放根.env.example触发原严格解析，改到agent/.env.example后175过。未改原env解析/认证、原业务策略/状态机。最终代理对ERROR回执保守tool_executed=null的补充由3个参数化单测实测；真实容器仍只有R2 OK/执行前拒绝路径，没有冒充ERROR副作用验收。

final-run-02四容器chainguard-p7-852eb78ac8-{gateway,tool,operator,runner}已因--stop-after停止，四原卷与网络保留；原Besu继续运行。私钥/CA源在忽略.local/phase7/<timestamp>与分离卷，Agent只有自身JWT/证书/Journal；不要输出/提交。JWT900秒、证书2天，重做验收用新目录且单次运行，勿同时争用原relayer。verify脚本支持停止的工具容器，准确核对container ID后无网络/readonly挂载原卷。禁止prune/delete卷。

```powershell
# 新会话先重读六份上下文、相关代码及Git状态/diff/log，再建立当轮基线。
& .\scripts\chain.ps1 -UseWSL -Action health
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
& .\.venv\Scripts\python.exe scripts/verify_phase7.py results/phase7/final-run-02 --out results/phase7/new-session-verification.json
& .\.local\phase7-agentdojo-venv\Scripts\python.exe evaluation/check_agentdojo.py --out results/phase7/new-session-ad-check.json
```

固定trace attack_success=null、LLM样本0，**真实LLM攻防测试尚未完成**。用户已明确将真实模型接入列为阶段7后续必做，在阶段8正式A/B/C前完成；当前不运行真实模型也不进入阶段8。后续需模型名/API地址/密钥环境变量、受限模型网络路径、真实正常任务及文档/邮件注入调用记录、适用原判定器及不兼容任务处理。AgentDojo当前只有3函数映射、三个官方任务INCOMPATIBLE，原GOAL回放不是官方完整任务成功得分。原四节点/密钥同机、SQLite邮箱、Windows3.14基准依赖锁、无Git HEAD均为明确限制。源码/证据摘要在results/phase7，不重写旧阶段历史清单；Git仍0跟踪，不自动commit。

普通exec及node_repl初始化报helper_unknown_error: setup refresh had errors；只读exec按工具提权流程已获准，尚无审批拒绝。所有敏感工具仍只能在本地受限容器中运行；勿在Windows直接执行删除/邮件工具。进度和本交接后续必须补充实际命令、结果和未解错误，不将本段视为完成证据。

以下阶段6、5为历史交接。

## 当前交接：阶段6技术验收通过，等待用户验收

2026-10-26，D:\CCF / PowerShell，Docker在Ubuntu WSL2。用户授权范围仅R2 mail.send完整C闭环，不推进Agent/React/其他工具。下文阶段5原记录为历史，不能据其“未授权C”否认当前用户指令，也不能据阶段6完成扩大范围。

首先读AGENTS及architecture/contracts/decisions/progress/本文件；再读phase6-contracts.md/runbook.md/acceptance.md、实际chain_*.py/phase6_server.py/chain_mail.py及测试和git状态/diff/log。仓库仍无HEAD、0跟踪，空diff不证明无改动。当前文件摘要results/phase6/source-manifest.json，原证据摘要evidence-manifest.json；冻结21+8和三个原合约不得重写。

当轮实际验证：新模块10 passed；最终pytest154 passed，final-pytest.txt/xml；Hardhat71 passing，resume-hardhat.txt；build_specs/freeze_policy --check PASS。修改前基线144/71、上下文恢复基线149/71均在results/phase6。真实run-06 PASS：5预约+4审计+1markUnknown+2重放回滚，原四Besu20261026高度3556→3600，4封本地MIME，无外部投递。独立verification-06.json PASS：48实时receipt、原签名/链状态/邮箱mode=ro/result/evidence承诺与MIME吻合。不要把run-03旧3封邮件版或任何旧通过当新会话基线。

```powershell
Set-Location D:\CCF
git status --short
git log -5 --oneline # 仍无HEAD时会失败，如实记录，不创建提交
git diff --stat
git diff --cached --stat
& .\scripts\chain.ps1 -UseWSL -Action health
# 链离线时只恢复原网络，不重置任何卷：chain.ps1 -UseWSL -Action up
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
# 输出必须新文件；默认只读RPC+公开MIME，--tool-volume另读原测试数据库。
& .\.venv\Scripts\python.exe scripts/verify_phase6.py results/phase6/run-06 --tool-volume --out results/phase6/new-session-verification.json
# 仅确有需要重新做真实验收时使用新目录；会生成新卷/合成邮件/真实链交易：
# & .\.venv\Scripts\python.exe scripts/run_phase6.py --out results/phase6/new-run
```

run-06当前三个测试容器为chainguard-p6-dd02674773-gateway/tool/qa，卷同名，保留供复核。其余run-01至05已停止，卷及证据保留；原四Besu和合约不重建。JWT15分钟、证书2天仅测试材料，过期时新建一次独立运行，不绕过身份验证。服务启动/停止与只读复核详见runbook，禁止prune/delete卷。

实现入口：gateway新增chain_crypto/rpc/store/service/api/transport及phase6_server；工具独立chain_mail；真实验收phase6_lab/run_phase6；只读verify_phase6。工具端节点2/4，网关1/3，均真实RPC；QA是可信测试签名器和只转发真实Besu的故障代理。Agent尚不存在，agent JWT只能提议，不持请求者/审批/工具/relayer私钥。工具API强制实际mTLS证书指纹+独立Bearer，调用参数承诺/当前链审批角色scope/TaskGrant/时间/配额全部必需。

关键持久约定：TaskGrant/完整参数盐/回执和raw交易AES-GCM链下存储；只把原协议元数据上链。工具永久actionId、配额、MIME与真实签名回执同一SQLite事务提交。网关持久dispatch_started但保持RESERVED，不提前声称EXECUTING；崩溃后UNKNOWN仅GET原日志，回执有效后确认执行→EXECUTION_RECORDED。审计队列只有原hash/nonce/raw：pending/receipt只查，原hash确实不在健康节点且nonce未消费时只重投同字节；不新建动作/交易、不重发邮件。nonce冲突/工具签名撤销保留人工处理，不降级校验。

旧失败保留：GBK向量读取修复；run-01TLS健康超时、run-02exec资源失败；run-04恢复期间预期FORBIDDEN但先链不可用；run-05HTTP代理重复建TLS trust store内存达1GiB，待预约超时。改固定HTTPConnection+显式close并缓存必要TLS context后，run-06QA58.35MiB、三服务无OOM，全部场景通过。不得通过覆盖失败目录/放宽授权/重冻协议“修复”。

尚未实现：其他C工具、Agent/前端、完整proof/verify/metrics API、自动未派发过期收尾；无原有效回执的UNKNOWN持续未知。支持单worker/专属relayer；不要同时运行两套验收争用原资金账户。本地SQLite邮箱原子效果不代表第三方SMTP一次性保证；同机四节点/批准密钥不等同独立机构运维；生产HSM/RPC认证与实验统计TODO。没有代码待修的已知失败；上述边界不伪装完成。

正常reserve `0xd981973e4ed994a4f50606e92442803d3919314aa2b9f6dd02a1bfbce8e4a499`（3567/status1），finalize `0xaaa2befc5b713bea34d6e514c28b6b2004d5512ef0045281ad3865182754697a`（3568/status1）；UNKNOWN reconcile `0x3ae8c5e04ac9fd55e1a82bd3b83f5bee12443809713bd877003c8b53c049c797`。mail-1.eml SHA256 f52261662c34e7ac6c11a79e07534a4015f9d53a101cead70f70f007614c7312。所有真实receipt/签名/public signer在run-06/report与tx/replay文件；三个合约仍下文阶段5地址。

私钥来源仍忽略.local/phase5原角色、.local/phase4原资金；运行拷贝/证书在.local/phase6和独立Docker卷，勿输出或提交。普通exec沙箱仍helper_unknown_error，经工具审批正常执行；无未解决审批拒绝。等待用户验收，不自动推进下一阶段。

## 阶段5历史交接（以下保留原信息，不是当前状态）

更新时间：2026-10-26，Asia/Shanghai。工作区D:\CCF，PowerShell，Docker在Ubuntu WSL2。**当前阶段5：三个业务合约已实现，自动测试/真实四节点Besu技术验收通过，等待用户验收。** 用户已明确授权阶段5；此前摘要说“未授权/未编码”已过时。没有进入C网关/工具查链、Agent或React阶段。

## 首先核验

1. 重读AGENTS.md、architecture.md、contracts.md、decisions.md、progress.md和本文件，及docs/phase5-contracts.md/acceptance.md和相关源码/测试；不直接按摘要编码。
2. git status/log/diff/cached/ls-files。已知仍无HEAD、0跟踪文件，全项目未跟踪；空diff不等于无变化。不自动add/commit或清理原文件。
3. 核验原config/phase0-freeze.json的21文件和phase3-policy-freeze.json的8文件；正常只check、不重冻。阶段5完整文件摘要在results/phase5/source-manifest.json，证据摘要在evidence-manifest.json。
4. 运行下列当轮基线；所有输出用新results/phase5/checks目录。已有部署复核只读，不广播新交易；若链离线先用原chain up恢复，禁止重置验证者/卷/资金账户。

```powershell
Set-Location D:\CCF
git status --short
git log -5 --oneline  # 已知无提交，仍须实际核验
git diff --stat
git diff --cached --stat
git ls-files
& .\scripts\chain.ps1 -UseWSL -Action health
# 如网络离线，恢复原网络：
# & .\scripts\chain.ps1 -UseWSL -Action up
& .\scripts\check_phase5.ps1 -VerifyRun results/phase5/besu-run-01
# 仅当任务确需重新部署整套新合约时运行；会产生真实交易和新本地测试身份：
# & .\scripts\check_phase5.ps1 -DeployBesu
```

## 本轮实际事实

- 原冻结21+8输入不变；build_specs/freeze_phase3检查PASS。新增治理单列spec/phase5/governance.json，不改原ActionIntent/ExecutionReceipt和状态机。
- 修改前144 pytest/41 Hardhat；三个模块分别7/15/8项通过；最终144 pytest/71 Hardhat通过。一键复验日志results/phase5/checks/final-20261026，包含pytest.xml、hardhat.txt、spec/shared-policy和Python/Besu验证输出。
- 首次审计测试7过1失败：夹具时间在另一意图签发前，先触发InvalidReceipt；修改测试构造顺序隔离签名重放后8项通过，未弱化合约校验。原失败保留results/phase5/audit-test.initial-failure.txt。
- 真实部署`node scripts/deploy_phase5.cjs --out results/phase5/besu-run-01`通过，27笔链交易=17成功+10预期回滚，四节点各有相同真实receipt，共同高度1247→1274。重复验证不是额外独立样本。
- Python独立eth-account/eth-abi重算部署域意图/回执digest、恢复公开签名人并调用四节点实际合约，108份实时receipt/规范区块成员与代码摘要核验PASS。原始report/逐笔tx-json/ABI/python-verification*.json在该目录。
- 回执为**合约测试夹具**；实际Besu用REJECTED表示无工具派发。没有声称mail.send/doc.delete通过C链授权真实执行；OK/ERROR状态在本地EVM用签名夹具测试。未来工具必须签真实结果。
- 原阶段4source-manifest的README因为新阶段说明有明确变化；不重写旧清单。其余15份历史链源码及21份原证据保留。最终结果见results/phase5/integrity.json。

## 实际部署与恢复

chainId=20261026；RPC8545–8548回环；官方Besu25.10.0，4独立JVM/节点身份/卷，原genesis hash `0xcb4778cbcf96b2891907209e06448c518e82f7fa633c376efe4621761e072173`。

- PolicyRegistry：0x68EAD07579A2B75bA4B024F8e02D14fb60a72dAa
- ExecutionRegistry：0x5effbc396C8532801C2a5e7A4d903b7c8702878A
- AuditRegistry：0x5d505B4ad2c4596b3bA3742ca5B338eB4d05f2eE
- 部署区块1248/1249/1250，runtime字节9871/10532/6057；代码摘要见report.json。
- R2预约hash `0xcfb64f9e1000036058ceb984edd7edec9d64da3746deaa81bd74ed96d276cbeb`，block1253/status1；R2 REJECTED夹具确认 `0xaea17cfa244875ca289d8f7b0074df503b89923c6ef4be859df655dbc7694ab6`，block1266/status1。
- 公开签名地址、完整typed夹具/ABI/27笔hash及4节点receipt在report.json及tx-*.json；证据不是唯一授权来源，工具必须独立查链。三份验收预约最终FINALIZED_REJECTED，nonce仍消费；当前R3策略在撤销测试后disabled/epoch2，R2 enabled/epoch1。不要把验收部署当已完成C服务初始化。
- 新测试身份密钥：忽略目录.local/phase5/<run>/accounts.private.json，只供本地链；不要读出到日志/聊天或提交。原资金密钥.local/phase4/accounts.private.json；节点密钥在chainguard_chain_node1至4独立Docker卷。
- 不删除卷、不prune、不重建验证者。chain.py up维持隐藏WSL会话，down释放会话但保留链卷；不改全局WSL/代理/防火墙。阶段4旧运行/故障说明在docs/phase4-runbook.md及results/phase4/failure-history.json。

## 实现细节与冻结边界

- PolicyRegistry.sol继承OpenZeppelin AccessControl/EIP712/ECDSA；全部新增写入走executeGovernance，当前至少两组织GOVERNANCE_ADMIN签同一GovernanceChange，完整Change[] ABI哈希/实际域/nonce/全局治理epoch/排他期限。每次成功治理提升epoch，批次原子回滚；策略policyEpoch单独自动递增。直接grant/revoke/renounce全部拒绝，无DEFAULT_ADMIN；单方只能emergencyPause，解除必须治理；批次不能移除最后两个有效治理组织。
- ExecutionRegistry.sol：原ActionIntent所有字段签入同一digest。请求者当前角色/scope及agent绑定；R2业务+安全来自不同地址/组织；R3第三账户人审；全部签名当前有效且有scope，禁止重复及requester/agent/TOOL_SIGNER，最多16份。采用角色分配搜索防多角色重复计数。登记规则精确工具/scope/risk/epoch/时效；nonce/actionId永久一次消费，不因过期/UNKNOWN/失败/撤销释放。
- AuditRegistry.sol：相同预约参数，当前绑定toolId的TOOL_SIGNER；版本/非零承诺/时间检查；部署未来时间容差0秒。finalize只RESERVED，reconcile只UNKNOWN，均只0/1/2结果；markUnknown只有当前RECONCILER且非零原因。终态不可覆盖，完全相同digest+工具签名地址幂等返回，不新增事件。暂停/策略撤销不阻止真实旧证据锚定，当前工具签名人撤销仍拒绝。
- 只有固定Audit可recordAuditOutcome；Execution/Audit引用不可变且构造互查。先Policy、再Execution（预测下一CREATE Audit地址）、再Audit，EOA部署中间不得插入其他交易；脚本逐笔核验，不用管理员可变setter。
- 动作域ChainGuard ExecutionRegistry、回执域ChainGuard AuditRegistry，version=1；实际20261026/真实地址；原golden31337和中央B域0保持原样。治理是第三个独立域ChainGuard PolicyRegistry，不重定义原结构。
- frozen /v1 API和C网关仍TODO；中央/central/v1不改变。execute_reserved仍拒绝未接入链执行；不能将中央结果/测试夹具或普通转账receipt当真实C工具执行回执。

## 下一步依赖与限制

用户验收后、明确指定下一阶段才能接入：可信C网关交易确认/持久状态/错误映射；工具独立RPC查已确认reservation、全批准者当前角色/组织/scope与policy epoch；真实TaskGrant/收件人/doc_id/显式删除/时效/原子配额；完整JCS+盐承诺重算；工具持久唯一claim后沙箱副作用；真实工具结果签名/加密证据/待提交队列；UNKNOWN检索原始日志并reconcile，禁止重派发。

Agent不得持有真实敏感工具凭据；敏感测试邮件仍仅本地，删除仅测试文件。私钥/API Key/原文/盐不上链或公开日志。四节点与测试批准密钥同机管理，不代表四机构独立治理；生产RPC认证、HSM/密钥交付、性能和LLM评测未做。

普通exec沙箱初始化持续helper_unknown_error，必要步骤按工具规则获准执行后完成；无审批拒绝遗留。Git缺初始提交/回滚历史仍是限制；新增source/evidence摘要不是独立信任根。下次仍须检查源码、接口、测试与新部分工作，不能凭本文件断定未来状态。当前等待阶段5验收，不自动推进后续。
