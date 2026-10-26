# 阶段8验收

**最新补充2026-10-26：完整一键 `results/phase8/complete-experiment-01` PASS，真实DeepSeek预检→C前置→A/B/C→协议轨全部实际退出0。** 模型轨12真实任务/12MIME/C8tx，协议轨138案例/93MIME/59tx；原卷readonly、四节点receipt、签名/承诺与统计重算均通过。最终212pytest/71Hardhat及冻结check PASS，等待用户验收。修改文件、命令、各项物理证据、原判定器适配、小样本统计和失败说明见 [live-experiments.md](live-experiments.md)。下文是原协议轨验收原件，其中“缺Key/模型尚未完成”属于历史记录；协议指标不混入模型ASR。

日期2026-10-26，D:\CCF。用户最新指定DeepSeek/deepseek-flash/https://api.deepseek.com；安全加载与真实API预检入口已实现，但本轮三次实际预检均LLM_API_KEY_MISSING，未发送API请求。真实正常任务/提示词注入、官方AgentDojo判定及正式模型A/B/C/ASR未完成，阶段7/8均不能标记完整通过。以下仅为真实本地协议实验的技术验收，等待用户验收。

## 修改文件与实现

| 文件组 | 实现与验收依赖 |
|---|---|
| evaluation/phase8_plan.json、replay.py、phase8.Dockerfile | 固定seed、46个相同sample_id逐组配对/轮换组序；真实原A/B/C服务、独立测试卷、本地MIME/持久幂等/签名/原四Besu；138行完整计划 |
| evaluation/metrics.py、evaluation/tests/test_metrics.py | CSV/Markdown自动导出；Wilson95、scenario cluster bootstrap、固定工作负载trial bootstrap、B/C配对差异、UNKNOWN界限、shared_tool_policy共同分母 |
| scripts/run_phase8.py、verify_phase8.py、evaluation/tests/test_replay_contract.py | 一键运行/报告；离线构建与版本/环境/顺序/输入源码清单；原WSL保活；四节点receipt/事件/calldata/nonce/签名、原工具卷readonly+SQLite mode=ro、统计重算；拒绝缺行/失配/伪LLM标记 |
| agent/src/chainguard_agent/local_config.py、agent/tests/test_local_config.py | 白名单字面值.env.local安全加载，进程环境优先、原子解析与递归密钥脱敏；不改变Agent工具权限 |
| evaluation/deepseek_config.json、scripts/check_deepseek.py | 用户指定模型与参数固定；真实/models与诊断Tool Calling预检；无密钥/网络/HTTP/模型或参数不兼容明确失败，无模拟兜底 |
| .env.local.example、.gitignore | 空密钥模板；忽略.env.local、允许模板，实际git check-ignore验证 |
| docs/phase8-design.md、phase8-contracts.md、phase8-runbook.md、deepseek-runbook.md及本文件 | 输入/边界/字段/状态/指标方法/复现/后续依赖 |
| README.md、docs/architecture.md、contracts.md、decisions.md、progress.md、handoff.md | 持久进度/导航/安全决策；与历史阶段区分 |

阶段8沿用现有pytest发现evaluation/tests的配置；未改原21份协议、共享8份规则、三个业务合约、原AgentDojo源码/判定器或生产网关/工具安全控制。Git仍无HEAD/0跟踪，使用原始文件及摘要核验，不自动提交。

## 实际运行命令与结果

```powershell
& .\.venv\Scripts\python.exe scripts/run_phase8.py --out results/phase8/run-04
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=results/phase8/final-checks/pytest-complete.xml
& npm.cmd test
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe scripts/check_deepseek.py --out results/phase8/deepseek-preflight-02
```

最后一条为预期BLOCKED，其余通过。一键无参数命令自动生成唯一新目录：`& .\.venv\Scripts\python.exe scripts/run_phase8.py`。旧结果目录拒绝覆盖。依赖及只读复验见phase8-runbook.md；真实API重试见deepseek-runbook.md。

最终全量**197 pytest passed**（8.78s，final-checks/pytest-complete.txt/xml）；**71 Hardhat passing**（final-hardhat.txt）。配置/脱敏+实验统计模块**22项通过**（deepseek-and-protocol-unit.txt/xml）。生成规范与共享策略检查PASS；最终run-04所有记录源码摘要与当前匹配，无漂移。

`results/phase8/run-04/run_manifest.json`与`verification.json`均PASS。实际**138行=46样本×A/B/C**，**93封本地MIME**（A40/B28/C25）、**59笔真实交易/236份四节点receipt**；原chainId **20261026**，共同高度**12505→12602**，独立复核高度12603。真实总gas **20,965,771**，不是公链货币费用。副作用只在专属Docker卷，容器uid10001、只读根、无主机挂载/公共端口、cap-drop ALL；新容器已退出0，原卷chainguard-p8-6765c7f69744保留，原四Besu与WSL保活保留。

四种要求输出均已生成：`traces.jsonl`、`cases.csv`、`aggregated_metrics.csv`、`run_manifest.json`；另有自动report.md、138份case JSON和四节点原始tx-receipts.json。公开案例只含合成MIME、元数据、原签名和承诺，不导出私钥、API Key、参数盐或raw交易。

## 实测指标

UER/UBR使用`shared_tool_policy`：文档目标调用、邮件目标调用、参数更换各3次，每组完全相同9个案例；不会与B/C独有6次审批尝试混比分母。下列比例括号为95% Wilson区间，完整cluster/配对区间见CSV。

| 指标 | A | B | C |
|---|---|---|---|
| UER | 6/9=66.67% [35.42%,87.94%] | 0/9 [0,29.91%] | 0/9 [0,29.91%] |
| UBR | 3/9=33.33% [12.06%,64.58%] | 9/9 [70.09%,100%] | 9/9 [70.09%,100%] |
| TCR，含指定故障 | 28/31=90.32% [75.10%,96.65%] | 同A | 25/31=80.65% [63.72%,90.81%] |
| TDR | 0/6 [0,39.03%] | 6/6 [60.97%,100%] | 6/6 [60.97%,100%] |
| FAR，伪造/异动作审批 | 不适用 | 0/6 [0,39.03%] | 0/6 [0,39.03%] |
| RSE | 60重放/0重复副作用 | 60重放/0重复副作用 | 60重放/0重复副作用 |
| ASR | 未测，n=0 | 未测，n=0 | 未测，n=0 |

中央任务账号同时有Alice/Bob权限、任务只许Alice，A保留原账号检查/任务shadow差异。B/C共同冻结业务策略均生效。B签名追加日志保留独立checkpoint，本威胁模型下B/C都检出篡改，不得据该表宣传区块链独有的篡改能力。C额外三次工具查链失联选择不执行，导致TCR低于中央组；不是丢弃失败后的成功率。

每组预定性能样本n=10、并发1，全部完成；单位毫秒，括号为固定工作负载trial bootstrap95区间：

| 组 | P50 | P95 | P99 |
|---|---|---|---|
| A | 37.12 [34.24,44.29] | 50.50 [40.98,53.30] | 52.74 [40.98,53.30] |
| B | 336.11 [292.47,369.52] | 375.58 [356.53,376.34] | 376.19 [356.53,376.34] |
| C | 4474.34 [3377.70,4749.20] | 6111.47 [4662.89,7111.52] | 6911.51 [4731.93,7111.52] |

CSV还包含均值、样本标准差、最大值、失败率、审批/预约/工具/审计分量和收到调用至工具响应边界分量。全部是可信服务层真实磁盘/签名/RPC测量，包含自动测试审批，不包含模型/HTTP/mTLS。n=10的P99仅探索，单机/单任务重复不能外推生产吞吐或总体尾延迟。

正常C样例actionId=`0x8bfa348be53dcc57d299a026663b0cf6701893d9092e11e37ad0811ece1abb38`：reserve `0xb47cb8c391b33f1a9478a60188f9d6fd2b9cc9f17b621647c31a6047eccb31cf`，block12541/status1；finalize `0xed71c3e8cb40c5a83bf3091dec5e8a07af0cea779991f66755b85f72ffcf88a6`，block12542/status1。真实MIME SHA256=`cc36e0651e7d31694263627fad494352072cb15fc24b7d258b405028f15010c6`，原bytes存case JSON/base64并与原卷匹配。

## 失败、已知问题与下一步

run-01保留138行/93MIME，其中一次C pending-finalize在真实审计status1后TypeError，整轮FAIL。首次未保留stack，根因仍未定位；后续新增不含locals的stack诊断、原hash确认轮询，run-02/03/04均未再现，不能声称已确诊修复。

run-02旧统计版独立PASS；run-03共同分母版业务138行无错误，但独立receipt复核CHAIN_UNAVAILABLE，原manifest FAIL保留。之后四节点同一时间重新启动、restart0/无OOM，可能WSL runtime停止；最终启动脚本复用原显式隐藏WSL保活和健康等待，只读复核RPC增加有限重试。run-04最终一键完整PASS。所有迭代分开保留，不池化为独立样本，也不覆盖失败。

DeepSeek三次预检均未读到密钥；按用户“已重新填入”两次复查，D:\CCF\.env.local仍不存在，进程/Windows用户/系统变量和已知模板字段均为空，只输出布尔值。随后独占创建正确路径的空密钥文件，确认Git忽略并请求编辑器打开（queued），等待在实际文件中保存；不索要聊天密钥。真实API连通性、指定deepseek-flash/参数兼容性、真实Tool Calling/正常与注入任务、AgentDojo与正式A/B/C均未完成。预检脚本已经可重试，先通过它再继续后续模型任务，不将协议n=0的ASR改为0%。

其他限制：原四节点/签名材料同机，可信harness同进程并非Agent安全隔离验收；仅R2、本地SQLite邮箱、单relayer顺序；没有第三方SMTP exactly-once、生产HSM或大样本显著性结论。Git缺初始提交，源/证据摘要不是独立防恶意管理员的信任根。

下一步依赖：本地正确配置密钥→最小真实API/ToolCalling PASS→阶段7正常/注入与官方判定器兼容性→固定同模型/思考模式/采样/数据/评价运行正式A/B/C→重新计算正式ASR与任务指标。协议轨等待用户验收，不进入新的业务阶段。
