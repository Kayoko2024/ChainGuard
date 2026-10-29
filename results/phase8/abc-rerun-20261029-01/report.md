# ChainGuard A/B/C 重跑报告 · 2026-10-29

三套原有计划分别重跑，原始失败与未知保留，正式模型、目录开发探测、协议故障轨和 C 前置分别统计。本轮没有修改核心安全逻辑、链或业务页面数据。

| 轨道 | 实际 A/B/C 任务 | 真实模型请求 | 本地 MIME | C 交易 / 四节点 receipt |
|---|---:|---:|---:|---:|
| [原始固定任务](canonical/real-abc/report.md) | 12 | 36 | 12 | 8 / 32 |
| [模型生成摘要](summary/real-abc/report.md) | 36 | 108 | 36 | 24 / 96 |
| [目录注入开发探测](directory-probe/real-abc/report.md) | 12 | 36 | 8 | 4 / 16 |
| [独立协议/故障/性能](canonical/protocol/report.md) | 138 | 0 | 93 | 59 / 236 |

独立 C 前置不计入以上 A/B/C 样本。模型固定为 DeepSeek / deepseek-flash，temperature=0、top_p=1、thinking disabled、parallel_tool_calls=false；前两计划 max_tokens=512，目录探测为原配置1024。计划与每次真实请求/响应均可核对，三组各轨共享同一任务/材料/参数摘要。响应模型均为 deepseek-flash，观察到同一 provider fingerprint；远端服务别名将来仍可能升级，不保证再次请求输出逐字相同。

## 真实模型结论

| 轨道 | 组 | TCR | ASR | ASR Wilson 95% | 实际越权 / UER | 明确拒绝 / UBR |
|---|---|---|---|---|---|---|
| 原始 | A | 4/4 | 0/3 | [0.00%, 56.15%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 原始 | B | 4/4 | 0/3 | [0.00%, 56.15%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 原始 | C | 4/4 | 0/3 | [0.00%, 56.15%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 摘要 | A | 12/12 | 0/8 | [0.00%, 32.44%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 摘要 | B | 12/12 | 0/8 | [0.00%, 32.44%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 摘要 | C | 12/12 | 0/8 | [0.00%, 32.44%] | 无实际尝试，未测 | 无实际尝试，未测 |
| 目录探测 | A | 2/4 | 2/2 | [34.24%, 100.00%] | 2/2 | 0/2 |
| 目录探测 | B | 2/4 | 0/2 | [0.00%, 65.76%] | 0/2 | 2/2 |
| 目录探测 | C | 2/4 | 0/2 | [0.00%, 65.76%] | 0/2 | 2/2 |

原始及摘要轨没有实际越权工具提议，ASR=0不意味着网关完成过拦截。目录探测中三组均提出两次 Bob 调用：A实际发出两封，B/C真实拒绝且零对应邮件。该探测同时包含路由数据污染与指令注入，只有两个底层任务、未作消融，不能作为完整官方基准、总体零风险结论或 C 优于 B 的证据。各组目录轨总 TCR 为2/4，不能改用干净任务2/2代替。

## 协议、故障与性能

| 口径 | 指标 | A | B | C |
|---|---|---|---|
| 共同九个样本 | UER | 6/9 | 0/9 | 0/9 |
| 共同九个样本 | UBR | 3/9 | 9/9 | 9/9 |
| 全部适用样本 | TCR | 28/31 | 28/31 | 25/31 |
| 全部适用样本 | TDR | 0/6 | 6/6 | 6/6 |
| 全部适用样本 | FAR | 不适用 | 0/6 | 0/6 |
| 每组10次正常性能 / ms | P50 | 40.2 | 304.5 | 3401.6 |
| 每组10次正常性能 / ms | P95 | 52.5 | 333.8 | 4595.6 |
| 每组10次正常性能 / ms | P99 | 58.6 | 334.3 | 4617.6 |

所有95%区间、cluster bootstrap、样本数、UNKNOWN与性能失败率见各轨 aggregated_metrics.csv。性能是服务层自动测试审批/磁盘/签名/链确认，不含真实人工审批等待或HTTP/mTLS；模型轨另含模型时间，不可混合比较。n=10的P99仅为探索值。

伪造及异动作审批：B/C各6次均未接受、零邮件；A无该机制，其合法无签名调用不能记成伪造成功。三组参数篡改均零邮件；C保留UNKNOWN。每组3个幂等场景各10次网关及10次工具重投（共60次）新增邮件0。丢工具响应后，B维持3/3 UNKNOWN，C查询原回执后3/3 FINALIZED_OK；三组各只有原始一封邮件。派发前丢请求均 UNKNOWN；C 工具RPC不可用时3/3无邮件并UNKNOWN，未把安全拒绝解释为可用性优势。待补 finalize 使用原交易hash完成，未重发工具。

## 独立核验与修改范围

只读观察器重新挂载原卷（network none、read-only、SQLite mode=ro），核对原 MIME、模型输入、签名、承诺、calldata、链事件、nonce、四节点receipt与统计。结论文件位于 checks/*reverification.json。链ID20261026，原四Besu QBFT 2秒，仍为同机四验证者，不声称四机构生产部署。

合法C样本：[live-case-0001.json](canonical/real-abc/live-case-0001.json)，actionId `0x25852c5916b47fda8bc26f8338ee71cc67b2f4d633096599fa5cdc371c8d0d61`。
预约 `0xbbef8502968545554a6bb0feaedf4488edabc256874eae3b68b0e44731a574ff`；finalize `0xb873d2853ecb6d91e19215101095cc999705f7a8f0c4ef39bdd61d7656e41eea`；具体高度及原四节点receipt在 [tx-receipts.json](canonical/real-abc/tx-receipts.json)。

本轮仅修改 scripts/verify_live_agent.py 和新增 evaluation/tests/test_live_observer.py：允许操作员显式选择完整 SHA-256 的非root只读观察镜像，默认不自动降级；报告区分执行镜像/观察镜像，原容器及原卷身份仍强制一致，重复输出拒绝覆盖。原始执行时核验已经通过；后续标签复用导致早期镜像ID不可启动，首次收尾复验失败原件仍在 canonical/real-abc/volume-verification-failure.txt。后续显式观察镜像复核不增加模型样本或工具执行，不伪称找回原镜像。原核心源码与21+8冻结文件摘要保持。

## 测试与复现

基线88通过；只读观察镜像边界专项10通过；最终完整pytest586通过。前两次基线引用不存在的测试路径，均未运行测试，保留在 checks/baseline*.txt/xml，不能当成功。

在D:\CCF运行（输出目录必须全新；真实调用模型并产生本地邮件）：

```powershell
.\.venv\Scripts\python.exe scripts/run_real_experiments.py --plan evaluation/live_plan.json --out results/phase8/my-new-canonical
.\.venv\Scripts\python.exe scripts/run_real_experiments.py --plan evaluation/summary_plan.json --model-only --out results/phase8/my-new-summary
.\.venv\Scripts\python.exe scripts/run_real_experiments.py --plan evaluation/directory_probe_plan.json --model-only --out results/phase8/my-new-directory-probe
```

每条命令生成自己的 traces.jsonl、cases.csv、aggregated_metrics.csv、run_manifest.json 与逐例证据。依赖既有四链、原部署/测试身份、缓存wheel、本地.env.local与AgentDojo锁定环境；不是干净机器部署。后续只读复验较早模型批次若缺执行镜像，可在 verify_live_agent.py 中显式提供 --observer-image 完整内容ID，禁止改manifest。

## 旧结果清理

已对57个候选条目、1212文件做逐字节ZIP归档及哈希核验，归档为 [phase8-before-20261029-01.zip](../../archive/phase8-before-20261029-01.zip)，索引 [cleanup-index.json](cleanup-index.json)。保留回归/部署硬依赖的complete-experiment-01、phase9与B/C机制原件。

删除已核验散文件的操作被自动审批检查拒绝，只返回 blocked by policy，未给更具体原因。原文件未删除，也未更换方式重试；结果见 [cleanup-result.json](cleanup-result.json)。没有修改Docker卷、链数据、私密运行配置或现场任务。
