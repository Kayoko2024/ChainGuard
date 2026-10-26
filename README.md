# ChainGuard monorepo

## 阶段9：只读审计控制台

阶段9技术验收通过，等待用户验收。独立React控制台已运行于 `http://127.0.0.1:8080`，原核心安全逻辑不变。最终231pytest/71Hardhat/3前端测试、真实链/HTTP/Edge、17步受控干净重建通过。修改文件、全部命令/失败/限制见 [阶段9验收](docs/phase9-acceptance.md)，只读接口见 [阶段9契约](docs/phase9-contracts.md)；阶段8以下为历史阶段。

匿名交付：[设计报告PDF](output/pdf/设计报告+ChainGuard.pdf)、[测试报告PDF](output/pdf/测试报告+ChainGuard.pdf)，对应源在docs/reports。报告已去身份化并逐页渲染检查，历史运行日志含本机路径，整个仓库/发布包仍需提交前单独匿名审查。

环境：Windows PowerShell、Python3.14.4、Node22.23.1/npm10.9.8、Ubuntu WSL2 Docker与Compose、现有四Besu和阶段5部署、原本地测试签名材料。审计进程不持有签名密钥或LLM Key。准备依赖与公开镜像后，在根目录一条命令：

```powershell
& .\.venv\Scripts\python.exe scripts/deploy_phase9.py
```

默认重新运行原协议实验（真实本地邮箱/真实链交易），原验证器检查原工具卷后导出公开投影；`npm ci`、React构建、离线镜像、Compose和HTTP冒烟顺序执行。完成后访问 `http://127.0.0.1:8080`。只挂载公开证据卷，页面不包含正文/盐/私钥，不提供任何执行或审批入口。旧历史区块的权限状态查询可能失败，不能用旧UI状态冒充重新验证成功；失败保留。用近期证据时可传 `--protocol results/phase8/某次实际通过的协议运行`；已有完整两轨可传 `--bundle`。

当前8080已运行；另做验收可加`--port 8083`，避免端口冲突。最终部署`results/phase9/deploy-final`、真实协议源`results/phase8/phase9/b5b09af5ea`：138案例、93本地MIME、59tx、236份四节点receipt，chainId20261026、高度22651→22722。原tx-receipts.json、逐case签名/副作用与原卷readonly复核保存；控制台状态不能替代这些原件。容器启动后自动进行实际Edge浏览器冒烟，需要本机已安装Microsoft Edge。

冒烟与演示（新输出路径）：

```powershell
& .\.venv\Scripts\python.exe scripts/smoke_audit.py --out results/phase9/my-http.json
node dashboard/tests/browser-smoke.mjs http://127.0.0.1:8080 results/phase9/my-browser.json
& .\.venv\Scripts\python.exe scripts/demo_phase9.py
```

源码重建步骤（新目录/新虚拟环境，不复制`.env.local`、`.local`私有状态或`node_modules`）：

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
& .\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
& .\.venv\Scripts\python.exe -m pip check
npm.cmd ci --ignore-scripts --no-audit --no-fund
& .\.venv\Scripts\python.exe -m pytest -q
npm.cmd test
npm.cmd --prefix dashboard ci --ignore-scripts --no-audit --no-fund
npm.cmd --prefix dashboard test
npm.cmd --prefix dashboard run build
```

受控重建命令会创建新的源码/venv/npm目录，无缓存构建Docker镜像，并对8081执行HTTP和真实浏览器冒烟：

```powershell
& .\.venv\Scripts\python.exe scripts/rebuild_phase9.py --deployment results/phase9/某次通过的部署
```

部署前需要已下载的固定Python基础镜像及按`results/phase3/wheels.json`核验的Linux wheel缓存；可用 `scripts/prepare_phase3_wheels.py`准备缓存。源码复制中仅有明确列出的公开历史单测夹具，不复制密钥。重建复用原本机OS/WSL/Docker/链和公开证据卷、已校验wheel缓存，**不等同于空白机器/新创世链完整部署**；后者尚未验收。首次机器的链与合约初始化依赖阶段4/5运行说明，禁止对现有卷重置。

本次`results/phase9/clean-final/rebuild.json`为PASS，17步全部退出0：全新目录/venv/root及前端node_modules、锁定安装与pip check、231pytest/71Hardhat/3前端测试、无缓存镜像、8081真实HTTP/Edge通过。重做可直接使用`--deployment results/phase9/deploy-final`。PDF重建使用ReportLab4.4.9、pypdf6.10.0及支持中文的TrueType字体：`python scripts/build_phase9_reports.py --font <font.ttf>`；PDF依赖独立于网关。

阶段8历史结果：完整一键真实DeepSeek前置/A-B-C/协议轨技术验收通过，证据 `results/phase8/complete-experiment-01` 全部PASS，当时212pytest/71Hardhat及冻结检查通过。完整官方AgentDojo utility不兼容，适配目标不称排行榜得分。阶段0协议/golden vector、阶段3 B/C策略和阶段5三个合约保持冻结；当前React实现见上文阶段9。

真实模型与协议轨一起复现（密钥仅在Git忽略的 `D:\CCF\.env.local`）：

```powershell
& .\.venv\Scripts\python.exe scripts/run_phase8.py --track real_llm
```

命令依次运行API预检、真实C前置、真实A/B/C、协议故障/性能及独立核验，各轨四种输出分开。首轮模型轨12真实任务、12本地MIME、8真实链交易/32节点receipt；各组ASR0/3，95%上界56.15%，模型无越权尝试，不能声称网关阻断或总体零风险。[完整配置、证据、统计及限制](docs/live-experiments.md)。

## 阶段8一键真实回放与报告

```powershell
& .\.venv\Scripts\python.exe scripts/run_phase8.py
```

复用原A/B/C服务与四Besu，本地独立受限卷真实发送、审批伪造/签名重放/参数与审计篡改/故障恢复及性能测试。新目录自动输出traces.jsonl、cases.csv、aggregated_metrics.csv、run_manifest.json及report.md；四节点receipt、原MIME、独立签名日志及原卷readonly复核。三组共用输入/基础策略，A原shadow差异、机制不适用及共同分母分别披露。固定协议trace不计算真实LLM ASR。

[实验字段和统计口径](docs/phase8-contracts.md)、[依赖与复现](docs/phase8-runbook.md)、[实际验收及限制](docs/phase8-acceptance.md)。run-04为138实际行、93本地邮件、59笔真实交易/236份节点回执复核PASS；历史197 pytest/71 Hardhat通过。最新模型轨另见上文，不与协议样本混算。

DeepSeek最小真实API/ToolCalling预检：`& .\.venv\Scripts\python.exe scripts/check_deepseek.py`。模型固定deepseek-flash；按[安全配置说明](docs/deepseek-runbook.md)将密钥只配置在D:\CCF\.env.local或环境变量，最新真实预检已通过。不要将真实密钥填入可提交的example文件。

## 阶段7运行与验收

```powershell
& .\scripts\chain.ps1 -UseWSL -Action up
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
& .\.venv\Scripts\python.exe scripts/run_phase7.py --out results/phase7/my-run --fixture agent/fixtures/acceptance.json --stop-after
& .\.venv\Scripts\python.exe scripts/verify_phase7.py results/phase7/my-run --out results/phase7/my-verification.json
& .\.venv\Scripts\python.exe evaluation/setup_agentdojo.py --download
& .\.local\phase7-agentdojo-venv\Scripts\python.exe evaluation/check_agentdojo.py --out results/phase7/my-ad-check.json
```

最终175项Python、71项Hardhat、容器内6项读取测试通过。final-run-02四场景产生4封真实本地邮件和8笔Besu交易，32份实时receipt/签名/承诺与原工具卷只读复核通过。越权/删除拒绝，重启无重复投递，Agent工具/节点直连隔离。AgentDojo0.1.35官方包/判定器未改，部分workspace调用已映射，不兼容样本明确列出。模型独立环境模板在agent/.env.example；本轮llm_sample_count=0、attack_success=null。[接口与状态](docs/phase7-contracts.md)、[复现](docs/phase7-runbook.md)、[验收证据和后续必做](docs/phase7-acceptance.md)。

## 阶段6运行与验收

```powershell
& .\scripts\chain.ps1 -UseWSL -Action up
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
# 新结果目录；真实交易和邮件只落新的本地隔离测试卷。
& .\.venv\Scripts\python.exe scripts/run_phase6.py --out results/phase6/my-new-run
# 已有运行只读复核，输出必须用新文件名。
& .\.venv\Scripts\python.exe scripts/verify_phase6.py results/phase6/run-06 --tool-volume --out results/phase6/my-verification.json
```

最终运行run-06：154项Python、71项Hardhat回归通过；4封真实SQLite MIME邮件，5次预约/4次审计确认、1次markUnknown和2次预期重放回滚；48份四节点实时receipt复核通过。UNKNOWN只找回原回执，审计待提交只重投同签名字节，工具不盲目重派发。[字段与状态](docs/phase6-contracts.md)、[复现与恢复](docs/phase6-runbook.md)、[验收证据/限制](docs/phase6-acceptance.md)。旧失败证据保留；重跑不当作独立实验样本。

## 阶段5合约与验收

```powershell
# 原四节点网络已初始化；保留原数据和密钥。
& .\scripts\chain.ps1 -UseWSL -Action up
# 回归并部署一套新合约、发送真实正反交易、逐节点验证receipt。
& .\scripts\check_phase5.ps1 -DeployBesu
# 仅回归并复核本次已有部署，不广播新交易。
& .\scripts\check_phase5.ps1 -VerifyRun results/phase5/besu-run-01
```

PolicyRegistry使用双组织EIP-712治理；ExecutionRegistry强制R2/R3同意图独立审批、当前角色/scope、epoch及时效、nonce/actionId一次性预约；AuditRegistry核验绑定工具签名、追加UNKNOWN及对账、阻止终态覆盖。部署引用不可变、无升级后门。部署脚本使用本地测试身份，私钥保留忽略目录；签名回执为明确标注的合约测试夹具，不表示邮件/删除实际执行。[字段/治理/状态/后续依赖](docs/phase5-contracts.md)、[实际结果/地址/命令](docs/phase5-acceptance.md)。

## 阶段4部署与验收

```powershell
& .\.venv\Scripts\python.exe scripts/pull_besu_image.py
wsl.exe -d Ubuntu -u root -- docker load --input /mnt/d/CCF/.local/besu-download/besu.docker.tar
& .\scripts\check_phase4.ps1 -UseWSL
# 查询和停止；down保留私有密钥及链数据卷。
& .\scripts\chain.ps1 -UseWSL -Action health
& .\scripts\chain.ps1 -UseWSL -Action down
```

独立链Compose在chain/compose.yaml，真实chainId=20261026，4个回环RPC端口8545-8548。官方Besu25.10.0镜像及摘要固定，实际签名转账和四节点receipt/余额核验、单节点停机与恢复写入results/phase4。随机测试密钥只存忽略目录或私有Docker卷，未交给Agent。初始化不重置已有链；同机四容器不代表四家独立机构。[部署说明](docs/phase4-runbook.md)、[阶段范围](docs/phase4-design.md)、[实际验收](docs/phase4-acceptance.md)。

## 阶段3验收

```powershell
& .\.venv\Scripts\python.exe scripts/prepare_phase3_wheels.py
& .\scripts\check_phase3.ps1 -UseWSL
```

A为常规账号鉴权，B强制任务ABAC/RBAC、真实EIP-712请求者/独立审批签名、工具端再核验与签名追加审计。两组共用资源和规则，B/C策略已冻结。中央接口在/central/v1；冻结/v1链契约未实现。实际Uvicorn和重启验收会导出MIME、SQLite、ActionTrace和独立检查点，测试容器/专用卷结束后清理。没有私钥/JWT输出或真实外部邮件。

单独运行真实HTTP验收：`& .\.venv\Scripts\python.exe scripts/run_phase3_container.py --wsl-distro Ubuntu --evidence`。预置私有中央目录后，容器内可用`python -m chainguard_gateway.central_server --root /sandbox/test-.../central --port 8001`启动实际服务；测试fixture创建该目录与登记身份，生产预置/外部身份服务尚未实现。默认原网关仍只有健康端点，不自动生成执行凭据。

[阶段3接口/字段/状态](docs/phase3-api.md)、[验收报告](docs/phase3-acceptance.md)、[B/C策略指纹](config/phase3-policy-freeze.json)。

## 阶段2验收（Windows + Ubuntu WSL Docker）

```powershell
& .\scripts\check_phase2.ps1 -UseWSL
```

该命令运行宿主机参数/协议/网关回归、Hardhat回归、两个工具容器测试套件，以及两个不同容器间的持久化重放验收。容器非root、无网络、根文件系统只读，不挂载主机目录；只对容器内新建测试文件操作。实际SQLite快照、MIME邮件和结果保存在results/phase2。验收后移除本次新建的测试卷，保留导出证据。

工具目前为内部Python库与隔离测试入口，没有新增HTTP业务端点。敏感原语需要工具端独立校验可信操作员签发的LocalTestPermit；它不代表链上R2/R3授权。正式execute_reserved入口返回CHAIN_UNAVAILABLE，等待真实链核验接入。[阶段2设计](docs/phase2-design.md)、[验收记录](docs/phase2-acceptance.md)、[工具用法与状态](sandbox_tools/README.md)。

## 快速启动（Windows PowerShell）

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\start_gateway.ps1
```

默认监听127.0.0.1:8000；Ctrl+C退出。健康端点为`GET /health/live`和`GET /health/ready`；业务/v1路径返回404。运维OpenAPI位于/operations/openapi.json，与冻结业务契约分开。

## WSL Docker Compose

本机已获授权安装Ubuntu24.04 WSL2的Docker29.1.3、Compose2.40.3及Buildx0.30.1。

```powershell
& .\scripts\compose.ps1 -UseWSL -Action validate
& .\scripts\compose.ps1 -UseWSL -Action up
& .\scripts\compose.ps1 -UseWSL -Action down
```

已有原生Docker CLI/Engine时省略-UseWSL。Compose仅启动本阶段gateway；无空的Besu/Agent服务。镜像使用Python3.14.4与固定digest，从Docker Official Images公共ECR分发入口拉取；运行容器无凭据、非root、只读根文件系统，使用bridge网络且只在回环发布端口。敏感工具服务与其隔离网络留待后续阶段。

## 验收

```powershell
# 本地测试、协议回归和真实HTTP进程启动
& .\scripts\check_phase1.ps1
# 本机完整验收，包含真实Compose构建/启动/检查/清理
& .\scripts\check_phase1.ps1 -UseWSL
# 原生Docker对应完整验收
& .\scripts\check_phase1.ps1 -RequireDocker
```

Docker烟测拒绝覆盖现存项目容器，请先显式down。测试完成会清理自身进程与容器，不删除镜像或用户数据卷。bootstrap不覆盖已有.env，不安装系统Docker；依赖锁为requirements-dev.lock、gateway/requirements.lock和package-lock.json。

## 文件索引

| 路径 | 内容 |
|---|---|
| gateway/ | FastAPI Python包、健康端点、pytest、Dockerfile与运行时锁 |
| contracts/ | 三个业务Registry、冻结类型/接口与协议测试合约 |
| spec/、config/ | 冻结协议、指纹、工具链版本 |
| scripts/、tests/ | 安装/启动/检查脚本、原有回归和环境测试 |
| sandbox_tools/ | 本地测试工具、工具端许可核验、SQLite幂等/邮箱/日志与隔离测试 |
| agent/、evaluation/ | 最小Runner/Proxy、独立模型配置、固定trace和AgentDojo映射/锁/原判定器自检 |
| dashboard/ | 阶段9 React只读审计控制台、独立锁、受限Compose与真实浏览器冒烟 |
| results/phase0、results/phase1 | 实际运行证据，不是业务实验指标 |

详细工程与兼容性：[阶段1环境说明](docs/phase1-environment.md)；修改文件、运行结果和已知问题：[阶段1验收记录](docs/phase1-acceptance.md)。

冻结基线：[需求矩阵](docs/requirements-matrix.md)、[威胁模型](docs/threat-model.md)、[权限表](docs/permissions.md)、[数据规范](docs/protocol.md)、[状态机](docs/state-machine.md)、[HTTP契约](spec/openapi.json)、[golden vector](spec/vectors/eip712-v1.json)。正常复现不重新生成向量。

当前阶段结束等待用户验收，再指定下一阶段。
