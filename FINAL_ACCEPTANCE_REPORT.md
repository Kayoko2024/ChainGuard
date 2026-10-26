# ChainGuard V1.0.0 最终独立验收报告

验收日期：2026-10-26。范围：复验当前实现，不开发新功能。证据根目录为 `results/final_acceptance/v1-independent-01/`（下文简称 E）。本报告优先于旧报告中对当前 HEAD、实时可验证性及发布完整性的描述；历史报告原件保持不变。

**结论：当前不具备“V1.0.0 完整研究成果／正式竞赛提交包”无条件最终签收条件。已实现的本地 R2 邮件原型可按下述范围有限签收。**

本轮实际重新执行了 Python 231、Hardhat 71、前端 3 项测试，全部通过；独立干净目录再次通过相同数量。真实四 Besu、真实预约／确认交易、原工具卷 MIME、签名、拒绝、UNKNOWN、篡改和断网恢复得到实证。主要未结项为：旧区块授权状态无法完整复验、项目许可证和匿名发布包缺失、软件版本号未统一、空白机器全流程重建及完整研究实验尚未验收。没有将这些项目标记 PASS。

## 1. 验收范围和判定

PASS 表示本轮有实际执行证据；FAIL 表示已发现交付要求不满足；UNAVAILABLE 表示所需观测不可取得，不能推断合法或非法；NOT_TESTED 表示没有执行。不同结论不得互相替代。

| 项目 | 本轮结论 | 证据和边界 |
|---|---|---|
| 1. 仓库、依赖锁、密钥和环境 | PASS；版本一致性 FAIL | 环境／锁可用，Key 已忽略且公开源无当前 Key；Python/根包仍 0.1.0，控制台 0.9.0，协议 1.0.0，不宣称已有正式 V1.0.0 软件发行 |
| 2. 全量 Python／Hardhat／前端 | PASS | 231／71／3，失败 0；E 中 pytest.xml 及原日志 |
| 3. 四节点 QBFT、区块、合约和 receipt | PASS | chainId 20261026，四真实 JVM／身份／卷；4 个验证者、各 3 peers；实时区块和代码、交易成员关系相符 |
| 4. protocol-0000 合法执行 | 新隔离运行 PASS；原报告旧动作完整复验 UNAVAILABLE | 新动作双组织签名、reserve、MIME、真实工具签名、finalize 全部复验；旧动作交易／原卷可读，但历史授权 eth_call 不可用 |
| 5. protocol-0043 非法调用 | PASS | 原件和新运行均无此案例动作预约及邮箱副作用；不存在 actionId，不伪造“拒绝交易” |
| 6. protocol-0006 缺回执 | 新运行 PASS；旧动作完整复验 UNAVAILABLE | 新运行网关 UNKNOWN、链 RESERVED、观察 PENDING_RECEIPT；无工具签名／finalize，不重发、不判失败 |
| 7. 伪造、参数替换、撤销、重放、并发幂等 | PASS，限实际测试范围 | Hardhat／Python、真实协议负例、原 27 笔合约交易重新查 receipt；100 并发邮件／50 并发删除在受限本地工具容器中通过，不宣称多 relayer 并发链写已验收 |
| 8. 五类审计篡改／失联／恢复 | PASS | 五类 INVALID；真实审计容器断网 UNAVAILABLE，恢复 VERIFIED；不写链、不执行工具 |
| 9. 两轨统计独立复算 | PASS | 协议 138 行／模型 12 行分别重算；Wilson 独立计数、150 项独立 Bootstrap／分位数检查；没有固定 trace 进入模型 ASR |
| 10. 受控干净重建 | PASS；空白机器 NOT_TESTED | 17 步退出 0，新 venv／npm／无缓存镜像／真实 API／Edge；复用 OS、Docker、链、公开卷和已核验 wheel |
| 11. 有效 HEAD 和可追溯版本 | PASS，本轮建立 | 初始 HEAD 缺失已实证；新建通用作者本地源码基线，283 个审核文件，无推送、无 Release 标签，原始实验保留 |
| 12. 报告、README、复现、许可证、证据和匿名包 | 部分 PASS；完整交付 FAIL | 两份报告及 PDF、README、脚本、原证据与新索引存在；项目许可证、正式匿名发布归档未提供 |

## 2. 环境、冻结协议与版本

实测 Python 3.14.4、Node 22.23.1、npm 10.9.8、Ubuntu WSL2、Docker 29.1.3／Compose 2.40.3；Besu 25.10.0、Solidity 0.8.28、Hardhat 2.26.3、OpenZeppelin 5.4.0，React 19.1.1／Vite 6.3.6。具体输出见 E 的 `*-version.log`、`network-health.log`、`environment.json`。

Python 开发／运行锁、根及前端 package-lock、AgentDojo 独立环境锁、镜像锁及 toolchain 配置均存在。`pip check` 退出 0，干净安装通过。锁和安装成功不等于跨 OS／跨架构全覆盖。

`build_specs.py --check`、`freeze_phase3_policy.py --check` 均退出 0。`source-integrity.json` 对阶段8原 116 份源文件及冻结清单共 25 个不同文件无漂移。没有修改 ActionIntent、ExecutionReceipt、golden vector、状态机、共享策略或三个合约；没有修改测试预期来消除失败。

本地 `.env.local` 存在且被 Git 忽略，模板 Key 为空；当前 Key 未出现在扫描的公开源中。提交前再次扫描已暂存 blob，逐字节等于磁盘源；不含当前 Key、私密运行文件、PEM 私钥或个人主目录路径。没有调用新 DeepSeek API、输出 Key 或 Key 摘要。此检查不宣称能识别任意历史泄漏或证明生产密钥托管安全。

初始 `git rev-parse --verify HEAD` 退出 128，不能用空 diff 宣称仓库原本干净。本轮按明确授权建立源码基线：

`b4a57819215c971eda48e4c60ae60feb4c2fde7a`

作者／邮箱采用通用 ChainGuard 标识；`git fsck --full` 退出 0。清单及 blob 摘要在 `E/git-baseline.json`、`git-allowlist-v2.json`。仅必要合成测试夹具随源码纳入 Git；大部分原始运行证据仍留本机未跟踪，未经匿名审查不能整体 `git add .`。这次初始提交不能补造此前开发历史，也不等于正式发行许可。

## 3. 实际测试及安全覆盖

| 命令（仓库根执行） | 退出码 | 实际结果／日志 |
|---|---:|---|
| `.venv/Scripts/python.exe -m pytest -q --junitxml=results/final_acceptance/v1-independent-01/pytest.xml` | 0 | 231 passed，9.96s；E/pytest.log、pytest.xml |
| `npm.cmd test` | 0 | 71 passing，Hardhat 本地 EVM；E/hardhat.log |
| `npm.cmd test`，cwd=`dashboard` | 0 | 3 passed；E/frontend.log |
| `.venv/Scripts/python.exe scripts/build_specs.py --check` | 0 | E/spec-check.log |
| `.venv/Scripts/python.exe scripts/freeze_phase3_policy.py --check` | 0 | E/policy-check.log |
| `.venv/Scripts/python.exe -m pip check` | 0 | 无依赖冲突；E/pip-check.log |
| `.venv/Scripts/python.exe scripts/check_phase9_integrity.py --out <新文件>` | 0 | 原安全实现／冻结输入不变；E/source-integrity.json |
| 无网络、非 root、只读根工具容器：`python -m unittest discover -s sandbox_tools/tests -p test_resources.py -v` | 0 | 8 项；E/sandbox-resources.log |
| 同受限容器：`python -m unittest discover -s sandbox_tools/tests -p test_tools.py -v` | 0 | 26 项；E/sandbox-tools.log |

231／71／3 为不同框架基线；干净环境重复通过不增加独立测试用例数。受限容器另测 34 项，真实副作用只在临时测试文件／本地邮箱中。

`tests/solidity/registries.spec.cjs` 实际覆盖：单组织／重复组织审批、伪造和错域／high-s、完整参数承诺替换、到期、actionId／nonce 重放、策略 epoch／停用、审批者和工具角色撤销、一次预约、UNKNOWN／终态保护、相同回执幂等。Python 覆盖请求和参数核验、加密持久、待提交原字节交易恢复、代理未知语义和审计拒绝分支。这些单测使用的夹具和注入 RPC 不作为真实链证据。

工具容器实际覆盖 100 次并发重放只生成一封邮件、50 次并发删除只删除一次、重复开启后幂等、路径穿越／符号链接／作用域与外部邮箱拒绝。没有删除主机真实文件或投递真实外部邮箱。

原合约验收 27 笔交易本轮逐笔查询四节点：17 成功、10 预期回滚，108 份 receipt 与原件和规范区块成员关系一致，见 `E/phase5-original-receipts.json`。回滚 status=0 本身不能证明具体 revert 原因；具体 guard 由重跑的安全测试验证。阶段5工具回执仍是 REJECTED 合约夹具，不冒充真实邮件。

测试断言失败为 0。验收记录工具的失败单列保留：首轮 history 把字典误用为路径而 TypeError；retry-01 因混合编码输出发生 UnicodeDecodeError，retry-02 完成交易／原卷核验；旧区块完整复验返回 UNAVAILABLE。补充新证据检查首轮把拒绝案例误认为都有 transactions 字段而 KeyError，按实际“拒绝无交易列表”格式修正后第二次退出 0，没有放宽安全断言。交互诊断曾因默认 GBK 和 WSL 格式串拆分失败，显式 UTF-8／无管道 JSON 输出后完成；不计为产品测试失败。早期 history 重试没有完整外层退出码账本，失败由原 error.json 佐证，不能宣称所有辅助命令均退出 0。收尾文档的 Git 空白检查因 Windows CRLF 与仓库 `* -text` 配置退出 2；恢复原文档正文原字节、让新报告与新增段落使用 LF 后重新检查。该失败日志保留，未改冻结文件或全局 Git 配置。旧阶段失败目录全部保留。

## 4. 真实链及工具证据

原网络创世 hash：`0xcb4778cbcf96b2891907209e06448c518e82f7fa633c376efe4621761e072173`。本轮启动检查共同高度 23979；独立只读验证再次实际观察 24546 → 24550。RPC 为回环 8545–8548，每节点 3 peers、相同四验证者、syncing=false。

| 合约 | 实际地址 | 四节点相同 runtime 字节数 |
|---|---|---:|
| PolicyRegistry | `0x68ead07579a2b75ba4b024f8e02d14fb60a72daa` | 9871 |
| ExecutionRegistry | `0x5effbc396c8532801c2a5e7a4d903b7c8702878a` | 10532 |
| AuditRegistry | `0x5d505b4ad2c4596b3ba3742ca5b338eb4d05f2ee` | 6057 |

代码摘要和实时节点记录在 `E/fresh-chain-evidence.json`，地址／代码与部署约定吻合。每笔指定交易核对真实 calldata、事件、nonce、四节点 receipt 和区块成员，不由 UI 推断。

### 4.1 优先只读复验的原报告证据

原协议源：`results/phase8/phase9/b5b09af5ea/`；原模型源：`results/phase8/complete-experiment-01/real-abc/`。

`E/history-retry-02/` 中保存协议 59 笔／236 receipt、模型 8 笔／32 receipt 的实时查询，以及原卷 readonly、SQLite mode=ro 检查。协议 138 案例／93 MIME，模型 12 案例／12 MIME 与原卷一致，原结果／证据承诺相符。

原 protocol-0000 预约 `0xb50108147ae9660bf863059f4dc17c5d1450275b40b9421d23e012dd3837a00b`（22656），确认 `0x3ea909c6740b973b7e253d58c731722bc5c6cb4f09fffa614d303ba306c0aea5`（22657），本轮 receipt 仍真实存在。原 protocol-0000／0006 的完整观察器复验因旧授权区块 eth_call 不可用而 UNAVAILABLE；不能把原报告中的历史 VERIFIED 当成本轮完整 PASS。原 protocol-0043 为 NO_RESERVATION。

完整验证器只对新复制目录执行；`protocol-full-reverification.json`、`model-full-reverification.json` 如实保存 UNAVAILABLE。`E/historical-preservation.json` 对旧阶段9证据索引的 162 份原件核对 changed=[]、missing=[]。没有覆盖原统计、receipt 或 case 文件。

### 4.2 独立目录／隔离卷的新真实执行

现有旧状态不可完整查询后，使用已存在的一键脚本，在 `results/phase9/final-independent-deploy-01/` 新建演示，源为 `results/phase8/phase9/7f6e0d69f7/`。这是同一案例名称的新动作，**不是原 actionId 的重新发送，也不是对旧证据的替换**。新独立卷、138 实际案例／93 MIME／59 真实交易，原验证器 export-verification.json PASS；之后又独立复核全部 receipt／原卷。新运行不并入正式模型 ASR 或原报告统计。

protocol-0000（该计划中的 performance/1 合法案例）：

- actionId：`0x8d7a2ff9b369cbbc18adb3ceb7c71b9dee5669371100148a2325b8a0834bd803`。
- reserve：`0xf160bb7b226e4d788ecaf39c67e1d0465e7a66d337739a0979ad1859e2f53f3d`，区块 24180，四节点 status=0x1。
- finalize：`0x17bf31964142e5e37af245dc0039fd559a72f96518c175a79d77c81df9c7672c`，区块 24181，四节点 status=0x1。
- 同一冻结意图的请求者签名和 OrgA_Business／OrgB_Security 不同组织审批，预约时有效；nonce 已消耗；工具端独立查链／承诺核验后产生真实签名回执。
- 原工具卷中本地收件人 `alice@inbox.chainguard.invalid` 的 MIME SHA256：`5a993f98daaf9b035f631d3b3ef492fe911a6c953c07544621330f69e6ee3d0f`。MIME 原字节、To、持久记录与承诺一致。网关 FINALIZED_OK，观察器 VERIFIED。

protocol-0043：提议被拒，无 actionId、无 reserve／finalize；独立原卷该案例无邮件，实际副作用 false。验证结论 NO_RESERVATION。这里只证明该案例；不把“某条目录无预约”泛化为全链绝无其他动作。

protocol-0006：预约 `0x5013fdda4e3b0ed9fd35ae01d0f5401e7334b9acaa45fcfbf4e80a2ac039b805`，区块 24184；无回执、无工具签名、无 finalize。网关 UNKNOWN，链 RESERVED，观察 PENDING_RECEIPT；没有推进 FINALIZED_ERROR、没有重派发。实验侧只读观察到邮箱为零是该实验时点的物理事实，不是一般 UNKNOWN 自动等于“未执行”的规则。

索引：`E/fresh-chain-evidence.json`（签名、组织、链状态、指定交易原 receipt），`fresh-live-receipts.json`（全部 59 笔／236 receipt），`fresh-mime-index.json`，`fresh-original-volume.log`（readonly／mode=ro）。原始 source 的逐 case JSON、tx-receipts.json、manifest 保留完整出处。

## 5. 五种篡改与故障恢复

对内存证据副本分别改 paramsCommit、审批签名、resultCommit、预约区块、actionId，五种均 INVALID。随后仅断开本轮新审计容器的 chainguard_qbft 网络：同一真实 FastAPI 进程返回 UNAVAILABLE、tool_signature_valid=null；网络恢复后验证为 VERIFIED。未修改原证据、未广播交易或执行工具，也未停止 Besu。

实际命令：`.venv/Scripts/python.exe scripts/check_phase9_observer.py --deployment results/phase9/final-independent-deploy-01 --out results/final_acceptance/v1-independent-01/observer.json`，退出 0。原始结果在 `E/observer.json`，日志在 `observer-tamper-outage.log`。截图和浏览器状态只验证展示，不承担链真实性证明。

## 6. 实验统计独立复核

协议轨固定 trace／确定性驱动和真实 DeepSeek 模型轨始终分别计算。原 traces 与 cases.csv、aggregated_metrics.csv 逐行匹配；计划调度／任务配对／模型参数和模型事件观测一致；原 AgentDojo security 判定器重新运行结果相同。没有修改官方判定器或把不兼容 utility 算作通过。

独立原始 k/n 与 Wilson95 复核见 `E/*-independent-counts.json`；独立标准库 inclusive 分位数和显式随机重采样另核对 150 项比例 cluster bootstrap／性能 trial bootstrap，见 `independent-quantiles-bootstrap.json`。所有区间来自原数据及固定 seed 重算，没有新增／池化样本。

协议轨（原报告源 b5b09af5ea，138 行；共同策略 cohort 各组 9 例）：

| 组 | UER（Wilson95） | UBR（Wilson95） | TDR | 含故障 TCR |
|---|---|---|---|---|
| A | 6/9，66.67% [35.42%,87.94%] | 3/9，33.33% [12.06%,64.58%] | 0/6 | 28/31 |
| B | 0/9 [0,29.91%] | 9/9 [70.09%,100%] | 6/6 | 28/31 |
| C | 0/9 [0,29.91%] | 9/9 [70.09%,100%] | 6/6 | 25/31 |

TDR=6/6 的 Wilson95 为 [60.97%,100%]；A/B TCR 区间 [75.10%,96.65%]，C 为 [63.72%,90.81%]。每组网关／工具合计 60 次重放，新增副作用 0。A 仍按冻结设计执行账号权限并 shadow 任务 ABAC，B/C 强制同一任务策略；B/C 独有审批案例不与 A 不同分母直接比较。协议轨 ASR=NOT_MEASURED，LLM 样本 0。

| 组（n=10） | P50 ms [95% CI] | P95 ms [95% CI] | P99 ms [95% CI] |
|---|---|---|---|
| A | 33.79 [33.34,34.97] | 35.51 [34.19,35.51] | 35.51 [34.41,35.51] |
| B | 278.96 [275.96,294.31] | 308.52 [284.26,311.96] | 311.27 [284.30,311.96] |
| C | 3350.80 [3056.44,3613.16] | 4170.79 [3522.83,4519.86] | 4450.05 [3522.83,4519.86] |

服务层耗时包含真实签名／磁盘／链，未包含生产 HTTP/mTLS 或模型时间。n=10 的尾分位数只作探索，不证明总体性能。

真实模型轨（complete-experiment-01/real-abc）：12 任务、36 模型请求、12 读取／12 MIME、C 组 8 真实交易。DeepSeek/deepseek-flash、temperature=0、top_p=1、thinking disabled、max_tokens=512、parallel_tool_calls=false，三组同任务／数据／工具 schema／评估配置。

三组各 ASR=0/3，Wilson95=[0,56.15%]；TCR=4/4，[51.01%,100%]。模型没有提出越权调用，UER／UBR 没有分母，不能填为“系统零越权率”或“成功拦截三次”。正常性能每组 n=1，P50/P95/P99 数值退化为同一观测（A 3496.83、B 3346.94、C 7750.86 ms），不推断总体尾延迟。

本轮只读复算历史真实请求记录与副作用、重跑原判定器，**没有重新调用 DeepSeek**；因此当前 API 可用性为 NOT_TESTED。适配的 security 目标不能替代完整官方 AgentDojo utility／排行榜评测。小样本、单模型、少量攻击且无模型越权尝试，完整研究有效性验收仍未通过。

## 7. 受控干净重建和真实冒烟

实际执行：

```powershell
.\.venv\Scripts\python.exe scripts/deploy_phase9.py --out results/phase9/final-independent-deploy-01 --port 8083
.\.venv\Scripts\python.exe scripts/rebuild_phase9.py --deployment results/phase9/final-independent-deploy-01 --out results/phase9/final-independent-clean-01
```

两命令均退出 0。第一条产生前述独立真实协议证据，部署只读控制台至 8083。第二条按 README 指向的现有脚本在新目录重建；`rebuild.json` 中 17 步全部 0：

| 步骤 | 实际调用 | 退出码 |
|---|---|---:|
| new-venv | Python `-m venv <clean-source>/.venv` | 0 |
| locked-python | 新 Python `-m pip install --disable-pip-version-check -r requirements-dev.lock` | 0 |
| editable-python | 新 Python `-m pip install --disable-pip-version-check --no-deps --no-build-isolation -e .` | 0 |
| pip-check | 新 Python `-m pip check` | 0 |
| root-npm-ci | 根 `npm.cmd ci --ignore-scripts --no-audit --no-fund` | 0 |
| pytest | 新 Python `-m pytest -q --junitxml=<新证据>/pytest.xml` | 0；231 passed，10.36s |
| hardhat | 根 `npm.cmd test` | 0；71 passing |
| spec／policy | 两项冻结 `--check` | 各 0 |
| dashboard-npm-ci | 前端 `npm.cmd ci --ignore-scripts --no-audit --no-fund` | 0 |
| dashboard-test／build | 前端 `npm.cmd test`／`npm.cmd run build` | 各 0；3 tests |
| no-cache-image | WSL Docker `build --no-cache --network none -f dashboard/Dockerfile -t chainguard/audit-clean:0.9.0 -` | 0 |
| public-volume-check | 无网络只读容器核对原公开卷 catalog 摘要 | 0 |
| clean-start | 非 root、只读、限制权限容器，只挂公开卷，回环 8081 | 0 |
| clean-http | 新 Python `scripts/smoke_audit.py --url http://127.0.0.1:8081 --out <新证据>/http.json` | 0 |
| clean-browser | `node tests/browser-smoke.mjs http://127.0.0.1:8081 <新证据>/browser.json`，cwd=新 dashboard | 0 |

`<clean-source>` 的实际绝对路径在 rebuild.json，源码逐文件摘要也在其中。每步完整 stdout/stderr 在同目录相应 .txt。真实 Edge/Playwright 无 route fixture、无 JS 错误，检查合法签名／组织、UNKNOWN、分组／搜索及移动视口；HTTP 实际查四节点，并拒绝写入口。

此重建复用了现有 Windows/WSL/Docker/Besu、原合约／公开卷、受核验 wheel 缓存及可用包缓存／网络；没有复制旧 venv、node_modules、.env.local 或私有工具卷。未实测空白 OS、全新 genesis／机构密钥和独立机器一条命令完成全流程，不能将其标为完成。8081 重建容器已自动停止且保留；8083 本轮控制台及原8080、四 Besu 保留运行，所有原卷保留。

## 8. 交付材料、冲突及风险

两报告源位于 `docs/reports/`，PDF 位于 `output/pdf/`：设计 3 页、测试 4 页，作者为空、文字可提取。本轮只读重新渲染七页并检查版面，无明显截断／重叠；原 PDF 摘要不变。结果见 `E/pdf-review/`。报告包含范围和小样本／完整 benchmark 不兼容说明；原测试报告中“无 HEAD”现由本轮新基线补充，不重写历史。

README、启动／部署／演示／重建／协议和模型复现脚本均存在；其前提是已有本地链及受控测试材料。原始证据按两轨／逐案例／交易／工具卷可索引，新增 `E/evidence-index.json` 保存本轮验收与所引原件的相对路径和 SHA256。摘要支持完整性检查，不构成独立时间戳或外部信任根。

项目根许可证缺失；AgentDojo 的 MIT LICENSE 只授权该第三方内容，不能当作 ChainGuard 项目许可证。交付目录无正式匿名发布 ZIP／归档／提交清单，历史运行日志包含宿主路径；本地源码基线不等于完成匿名竞赛发布包。未擅自代作者选择许可证、改软件版本、补写研究结果或创建发行标签。

尚未解决：

1. 旧授权区块 eth_call 无法完整获取，原 protocol-0000／0006 和旧模型完整验证为 UNAVAILABLE；需归档／历史状态方案后另行验收，不能用新动作替代旧动作证明。
2. 版本号不统一、项目权属／许可证和正式匿名发行归档缺失。原开发史不存在，本轮基线仅能从当前状态开始追溯。
3. 完整研究实验缺少更多模型／样本／攻击及完整官方 utility；当前无真实越权模型尝试，不能据 0/3 推导防御强度。
4. 空白机器／新创世链全流程没有重建验收；依赖既有 wheel、链、密钥准备及已安装 Edge。
5. 四节点和批准密钥同宿主，不是四机构独立运维；生产 HSM/KMS、RPC 身份准入、跨主机故障安全未验收。
6. 完整 C 链闭环只覆盖 R2 本地 mail.send；其他 C 工具、R3 删除闭环及原完整 proof/verify/metrics API 仍未完成。并发实证限本地工具，生产多 worker／多 relayer 未验收。
7. SQLite 本地邮箱原子性不能外推第三方 SMTP exactly-once；UNKNOWN 的安全行为是保留未知，不能以可用性指标要求自动重发。

正式提交仍缺：项目权属／许可证决定和第三方声明汇总；统一软件发行标识及发布清单；经独立审查的匿名源代码／证据归档、校验和及索引；声明前提完整的首次机器准备指南；若以“完整研究实验”提交，还须上述研究补充。具体赛事格式、报名／作者证明或附件要求未提供，本轮 NOT_TESTED。

## 9. 签收结论与停止点

- **本地原型：可有限签收。** 范围为现有 R2 本地邮件闭环、冻结协议／安全测试、四节点真实链、只读审计和依赖既有环境的受控重建；接受本报告披露的历史复验不可用和原型边界。
- **完整研究实验：不可签收。** 统计复算正确，但样本量、攻击覆盖、完整基准兼容性及外推依据不足。
- **正式竞赛提交／无条件 V1.0.0 最终交付：不可签收。** 许可证、匿名发布归档、发行版本一致性等必要交付未完成，且旧证据完整授权复验受限。

本轮只新增验收记录／辅助检查、建立明确授权的本地 Git 基线，并更新 progress/handoff；没有开发新业务功能、重定义协议、降低校验、覆盖原实验或自动补发 UNKNOWN 动作。验收结束后停止，未自动进入补缺或新开发。

## 附：实际命令与完整证据入口

`E/commands.jsonl` 保存主要命令的真实 argv、cwd、UTC 起止、耗时、退出码与日志文件；`history-retry-02/commands.jsonl` 保存原卷重读命令。标准输入未保存，命令行均不含 Key。本地日志中的运行时绝对路径未经匿名发布审查；下列自动附录将项目根／bundled Python 路径用占位符表示，原始 argv 仍留原账本。收尾完整性检查和文档提交的最终记录继续写入该账本，最终 HEAD 见 `E/git-final.json`。

| 记录名 | 实际 argv（路径占位） | cwd | 退出码 | 日志（E/） |
|---|---|---|---:|---|
| git-start-status | `git status --short` | `.` | 0 | git-start-status.log |
| git-start-head | `git rev-parse --verify HEAD` | `.` | 128 | git-start-head.log |
| git-start-diff | `git diff --stat` | `.` | 0 | git-start-diff.log |
| git-start-cached | `git diff --cached --stat` | `.` | 0 | git-start-cached.log |
| python-version | `<repo>\.venv\Scripts\python.exe --version` | `.` | 0 | python-version.log |
| node-version | `node --version` | `.` | 0 | node-version.log |
| npm-version | `npm.cmd --version` | `.` | 0 | npm-version.log |
| docker-version | `wsl.exe -d Ubuntu -u root -- docker version --format "{{json .}}"` | `.` | 0 | docker-version.log |
| compose-version | `wsl.exe -d Ubuntu -u root -- docker compose version` | `.` | 0 | compose-version.log |
| network-health | `<repo>\.venv\Scripts\python.exe scripts/chain.py health --wsl-distro Ubuntu` | `.` | 0 | network-health.log |
| pytest | `<repo>\.venv\Scripts\python.exe -m pytest -q --junitxml=<repo>\results\final_acceptance\v1-independent-01\pytest.xml` | `.` | 0 | pytest.log |
| hardhat | `npm.cmd test` | `.` | 0 | hardhat.log |
| frontend | `npm.cmd test` | `dashboard` | 0 | frontend.log |
| spec-check | `<repo>\.venv\Scripts\python.exe scripts/build_specs.py --check` | `.` | 0 | spec-check.log |
| policy-check | `<repo>\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check` | `.` | 0 | policy-check.log |
| pip-check | `<repo>\.venv\Scripts\python.exe -m pip check` | `.` | 0 | pip-check.log |
| source-integrity | `<repo>\.venv\Scripts\python.exe scripts/check_phase9_integrity.py --out <repo>\results\final_acceptance\v1-independent-01\source-integrity.json` | `.` | 0 | source-integrity.log |
| official-judges | `<repo>\.local\phase7-agentdojo-venv\Scripts\python.exe evaluation/judge_real_effects.py <repo>\results\final_acceptance\v1-independent-01\model-judge-copy` | `.` | 0 | official-judges.log |
| sandbox-build | `wsl.exe -d Ubuntu -u root -- docker build --network none -f sandbox_tools/Dockerfile -t chainguard/sandbox-tools:0.2.0 -` | `.` | 0 | sandbox-build.log |
| fresh-local-deploy | `.\.venv\Scripts\python.exe scripts/deploy_phase9.py --out results/phase9/final-independent-deploy-01 --port 8083` | `.` | 0 | fresh-local-deploy.log |
| observer-tamper-outage | `.\.venv\Scripts\python.exe scripts/check_phase9_observer.py --deployment results/phase9/final-independent-deploy-01 --out results/final_acceptance/v1-independent-01/observer.json` | `.` | 0 | observer-tamper-outage.log |
| controlled-clean-rebuild | `.\.venv\Scripts\python.exe scripts/rebuild_phase9.py --deployment results/phase9/final-independent-deploy-01 --out results/phase9/final-independent-clean-01` | `.` | 0 | controlled-clean-rebuild.log |
| fresh-independent-evidence | `.\.venv\Scripts\python.exe .local/acceptance_finish.py` | `.` | 1 | fresh-independent-evidence.log |
| fresh-original-volume | `wsl.exe -d Ubuntu -u root -- docker run --rm -i --network none --read-only --cap-drop ALL --security-opt no-new-privileges:true --mount type=volume,src=chainguard-p8-98dd08350683,dst=/sandbox,readonly sha256:1a79c8f090c888796f11f505295e5fd02e90c0e284aab4c82020c3c92dfa183a python -c " import hashlib,json,sqlite3,sys from pathlib import Path from Crypto.Cipher import AES from chainguard_gateway.central_store import CentralStore from chainguard_gateway.crypto import commit expected=json.load(sys.stdin) checked=[] for item in expected:  root=Path(item['tool_root'])  assert root.parent==Path('/sandbox') and root.name.startswith('test-')  with sqlite3.connect('file:'+str(root/'state.sqlite3')+'?mode=ro',uri=True) as db:   db.row_factory=sqlite3.Row   mail=[dict(r) for r in db.execute('SELECT action_id,recipient,mime_sha256,mime FROM mailbox ORDER BY message_id')]   for m in mail: assert hashlib.sha256(m.pop('mime')).hexdigest()==m['mime_sha256']   assert mail==item['mailbox']   assert db.execute("SELECT count(*) FROM executions WHERE state='COMPLETED'").fetchone()[0]==len(mail)   if item['group']=='C':    for r in db.execute('SELECT action_id,data FROM chain_mail'):     raw=r['data']; cipher=AES.new((root/'experiment-tool.key').read_bytes(),AES.MODE_GCM,nonce=raw[:16]); cipher.update(r['action_id'].encode())     original=json.loads(cipher.decrypt_and_verify(raw[32:],raw[16:32]))     assert commit('result',original['result_salt'],original['result'])==original['receipt']['result_commit']     assert commit('evidence',original['evidence_salt'],original['evidence'])==original['receipt']['evidence_index_commit']  if item['action_id']:   store=CentralStore(root/'gateway')   # Use mode=ro even for the gateway; no Store.connect mutation or tool APIs.   with sqlite3.connect('file:'+str(root/'gateway/state.sqlite3')+'?mode=ro',uri=True) as db:    record=db.execute('SELECT data FROM actions WHERE action_id=?',(item['action_id'],)).fetchone()    data=store.unseal('action/'+item['action_id'],record[0])    assert data['params']==item['params']    if data['intent']: assert commit('params',data['salt'],data['params'])==data['intent']['params_commit']  checked.append({'group':item['group'],'sample_id':item['sample_id'],'mail_count':len(mail)}) print(json.dumps({'status':'PASS','read_only_mount':True,'sqlite_mode':'ro','cases':len(checked),'mail_count':sum(c['mail_count'] for c in checked)})) "` | `.` | 0 | fresh-original-volume.log |
| fresh-independent-evidence-02 | `.\.venv\Scripts\python.exe .local/acceptance_finish.py` | `.` | 0 | fresh-independent-evidence-02.log |
| independent-quantiles-bootstrap | `.\.venv\Scripts\python.exe .local/acceptance_materials.py stats` | `.` | 0 | independent-quantiles-bootstrap.log |
| materials-privacy-plan | `.\.venv\Scripts\python.exe .local/acceptance_materials.py materials` | `.` | 0 | materials-privacy-plan.log |
| materials-privacy-plan-02 | `.\.venv\Scripts\python.exe .local/acceptance_materials.py materials` | `.` | 0 | materials-privacy-plan-02.log |
| pdf-readonly-review | `<bundled-python> .local/acceptance_pdf.py` | `.` | 0 | pdf-readonly-review.log |
| git-stage-reviewed | `git add --pathspec-from-file=<repo>\results\final_acceptance\v1-independent-01\git-pathspec.nul --pathspec-file-nul` | `.` | 0 | git-stage-reviewed.log |
| git-source-commit | `git -c "user.name=ChainGuard Acceptance" -c user.email=acceptance@chainguard.invalid -c commit.gpgsign=false commit -m "Record independently audited ChainGuard prototype source baseline"` | `.` | 0 | git-source-commit.log |
| git-valid-head | `git rev-parse --verify HEAD` | `.` | 0 | git-valid-head.log |
| git-baseline-fsck | `git fsck --full` | `.` | 0 | git-baseline-fsck.log |
| establish-reviewed-source-baseline | `.\.venv\Scripts\python.exe .local/acceptance_version.py` | `.` | 0 | establish-reviewed-source-baseline.log |
| original-receipts-and-preservation | `.\.venv\Scripts\python.exe .local/acceptance_archive_check.py` | `.` | 0 | original-receipts-and-preservation.log |
