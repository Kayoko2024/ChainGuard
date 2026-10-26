# ChainGuard 测试报告

匿名竞赛原型 · 实测日期2026-10-26 · 阶段9

## 1. 验收范围与环境

本轮验收只读审计控制台、真实证据导出、一键部署、冒烟、演示和受控干净重建。原执行安全逻辑不变。阶段8真实模型实验作为单独历史轨引用，不把本轮协议回放重复计入真实LLM样本。

环境为Windows/Ubuntu24.04 WSL2、Python3.14.4、Node22.23.1/npm10.9.8、Docker29.1.3/Compose2.40.3、四个真实Besu25.10.0 QBFT节点。前端React19.1.1、Vite6.3.6、Playwright1.56.1，浏览器为已安装Microsoft Edge。依赖以原Python/Hardhat锁及独立前端package-lock固定。

| 实际命令/证据 | 结果 | 验证对象 |
|---|---|---|
| python -m pytest -q | 231通过，8.98秒 | 原协议、网关、沙箱、模型/实验、审计层回归 |
| npm.cmd test | 71通过 | 三Registry、角色撤销、重放/过期/参数篡改、golden vector |
| 阶段9模块pytest | 19通过 | 只读接口、隐私投影、篡改目录、断链保守结论 |
| npm.cmd --prefix dashboard test | 3通过 | 未知/失联文字、hash、未知副作用区分 |
| 两项冻结check及原源码摘要 | PASS | 21+8清单共25个不同文件、116份原有源码无漂移 |
| deploy-final | PASS | 真实协议、原卷复核、锁定构建、Compose、HTTP与Edge |
| observer-final.json | PASS | 5类真实证据篡改拒绝、审计容器实际断网恢复 |

结果文件位于results/phase9/final-checks、audit-unit-04.xml、integrity-final.json、deploy-final和observer-final.json。单元测试使用的夹具或离线stub仅用于验证观察层分支，不作为链部署或真实业务效果证据。

## 2. 控制台与安全边界

真实Edge冒烟不拦截网络、不替换API：核验合法C动作、两组织审批/签名、UNKNOWN待回执、组别/搜索、移动视口与零JavaScript错误。HTTP另检验网络、原始动作、签名、四节点receipt与副作用来源，拒绝POST执行入口，并确认响应没有正文、盐、工具路径或私钥字段。

<!-- pagebreak -->

## 3. 本轮真实链与副作用证据

最终一键部署源为results/phase8/phase9/b5b09af5ea。138个实际案例、93封本地MIME、59笔真实交易和236份四节点receipt；chainId=20261026，共同高度22651 → 22722。原工具卷readonly挂载、SQLite mode=ro、签名/承诺/calldata/事件/nonce和统计重算均PASS。重复核验不增加独立样本。

控制台合法C动作protocol-0000在区块22656预约、22657确认工具回执，状态FINALIZED_OK。两个不同组织批准同一原意图；工具签名恢复地址与链上绑定一致。HTTP冒烟核验到共同高度22760，每笔交易均有四节点一致成功receipt及区块成员验证。

reserve交易：0xb50108147ae9660bf863059f4dc17c5d1450275b40b9421d23e012dd3837a00b

finalize交易：0x3ea909c6740b973b7e253d58c731722bc5c6cb4f09fffa614d303ba306c0aea5

完整原件为源目录tx-receipts.json、逐case JSON与traces.jsonl；工具副作用由原卷核验和逐案例MIME base64证明。公开控制台只展示承诺和核验结论，不用截图或UI颜色代替这些证据。部署目录public/export-verification.json保留独立原卷检查摘要。

UNKNOWN记录protocol-0006有预约但缺工具签名回执，实时结果PENDING_RECEIPT，当前链状态仍RESERVED。该结论不表示“没有执行”，页面没有重发按钮。越权记录protocol-0043没有预约，不补造拒绝交易。A/B返回HISTORICAL_ONLY，不伪装链上确认。

真实负面验证分别修改证据副本的paramsCommit、审批签名、resultCommit、预约区块和actionId，五类均INVALID。随后只断开审计容器的链网络，同一真实FastAPI进程返回UNAVAILABLE/tool_signature_valid=null；恢复网络后再次VERIFIED。全过程未写交易、未运行敏感工具，未修改原始证据或停止四Besu。

## 4. 指标定义与统计方法

UER=实际越权执行数/越权尝试数；UBR=已阻断越权数/越权尝试数；ASR=攻击成功任务/可评价注入任务；TCR=实际任务完成/任务机会；TDR=已发现篡改/篡改尝试。UNKNOWN保留未知计数/上下界，分母为0时标未适用，不填虚构零风险。

比例报告Wilson95和场景cluster bootstrap；性能采用固定工作负载trial bootstrap、线性分位数，失败另计。各轨完整置信区间在aggregated_metrics.csv；不池化重复运行，不把固定trace计入真实LLM ASR。

<!-- pagebreak -->

## 5. 协议轨与真实模型轨分列

本轮协议轨共同策略cohort每组9个配对样本；A记录任务策略shadow，B/C强制相同冻结规则。审批伪造只对有审批机制的组适用，不能用不同分母直接比较。

| 组 | UER及Wilson95 | UBR及Wilson95 |
|---|---|---|
| A | 6/9，66.67%，[35.42%,87.94%] | 3/9，33.33%，[12.06%,64.58%] |
| B | 0/9，[0,29.91%] | 9/9，[70.09%,100%] |
| C | 0/9，[0,29.91%] | 9/9，[70.09%,100%] |

B/C篡改检测6/6，Wilson95=[60.97%,100%]；A为0/6。含故障TCR为A/B 28/31、C 25/31，保留C额外独立查链失联的可用性成本。每组60次原actionId网关/工具重放，未新增副作用。协议轨ASR为NOT_MEASURED。

| 组（各n=10） | P50毫秒（95%区间） | P95毫秒（95%区间） | P99毫秒（95%区间） |
|---|---|---|---|
| A | 33.79 [33.34,34.97] | 35.51 [34.19,35.51] | 35.51 [34.41,35.51] |
| B | 278.96 [275.96,294.31] | 308.52 [284.26,311.96] | 311.27 [284.30,311.96] |
| C | 3350.80 [3056.44,3613.16] | 4170.79 [3522.83,4519.86] | 4450.05 [3522.83,4519.86] |

上述为服务层真实签名/磁盘/链延迟，不含生产HTTP/mTLS或模型耗时；小样本尾分位数只作探索。完整原始精度和各阶段延迟、失败率在CSV。

历史正式模型轨单列：results/phase8/complete-experiment-01/real-abc实际12任务、36模型请求、12读取、12本地MIME、C8真实交易/32节点receipt。DeepSeek/deepseek-flash，temperature=0、top_p=1、thinking disabled、max_tokens=512、并行工具关闭；任务/模型/数据/schema/评估相同。

各组ASR=0/3，Wilson95=[0,56.15%]；TCR=4/4，[51.01%,100%]。模型没有提出越权敏感调用，UER/UBR无分母，不能说网关阻断了三次攻击。每组正常性能仅n=1，不推断总体P99。完整官方AgentDojo utility仍INCOMPATIBLE，112份原源码/判定器不改；这里只评价明确映射的攻击目标，不是官方排行榜得分。

<!-- pagebreak -->

## 6. 重建、失败与复现

clean-02和clean-final两次受控干净重建均PASS：新源码目录、新Python venv、根/前端新node_modules、锁定安装与pip check、231pytest/71Hardhat/3前端测试、无缓存Docker构建、独立8081真实HTTP和Edge冒烟通过。最终版17步骤退出0，证据为results/phase9/clean-final/rebuild.json。

此验收复用现有OS/WSL/Docker、原四Besu和已核验Linux wheel缓存，以及仅含公开记录的只读证据卷。不复制.env.local、私钥、工具数据库或旧node_modules。不是空白机器安装，也不是全新创世链部署；首次机器需按阶段4/5独立准备。

失败记录保留：deploy-01/02协议执行因真实验证者RPC返回缺失值触发异常，整轮FAIL；仅新增演示进程的读取适配器将缺失值变为CHAIN_UNAVAILABLE，既有有限轮询处理，成功值原样返回，不伪造receipt，不改核心逻辑。clean-01挂载的公开卷缺catalog.json，HTTP失败；加入PASS来源/目录摘要/实际卷预检与readiness后clean-02通过。

旧区块权限查询曾返回Besu Internal error，记录historical-state-failure.json；保留UNAVAILABLE并用新真实协议运行演示，不能把旧记录改为已重新验证。一次临时报表读取遇Windows默认GBK，改显式UTF-8后读取成功，未改变实验数据。Git尚无HEAD/提交历史，不能靠空diff证明无改动；使用原摘要补充核验，不冒称Release Commit。

最终隐私扫描初轮因跨行空白正则误判空模板，改逐行解析后PASS；模板与干净源码快照相同。公开文件和构建上下文未检测到当前Key，模板为空且私密配置被Git忽略；没有输出Key或其摘要。

| 目的 | 在项目根目录执行 |
|---|---|
| 一键真实证据及控制台 | .venv/Scripts/python.exe scripts/deploy_phase9.py |
| 只读HTTP冒烟 | .venv/Scripts/python.exe scripts/smoke_audit.py --out results/phase9/new-http.json |
| 现场只读演示 | .venv/Scripts/python.exe scripts/demo_phase9.py |
| 独立重建 | .venv/Scripts/python.exe scripts/rebuild_phase9.py --deployment results/phase9/deploy-final |
| 真模型两轨重做 | .venv/Scripts/python.exe scripts/run_phase8.py --track real_llm |

命令自动使用新目录；手动--out也必须新路径。默认端口8080需空闲，已有服务可改--port。演示脚本输出原交易hash/区块和待回执结论，模型Key仅在本地忽略配置，不写报告。截图只作可视检查，不是执行证据。

## 7. 未完成项与匿名化边界

未完成：空白OS完整重建、其他C工具/R3闭环、跨机器多机构独立运维、生产认证和HSM、大样本多模型、完整官方benchmark及匿名发布包/提交。当前只是本地竞赛原型。匿名报告无学校/教师/队员信息或个人仓库URL，PDF作者为空；原始工程日志含本机路径，未经单独匿名化不可直接作为公开提交附件。
