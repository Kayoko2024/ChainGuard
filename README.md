# ChainGuard

可运行的智能体执行授权与审计原型：真实 DeepSeek 调用授权工具，任务授权与跨组织审批决定执行权，四节点 Besu 保存预约与签名结果。默认工具库支持文档列举/搜索/读取、本地邮件列举/读取及 **R2 本地测试邮件发送**。当前为阶段10原型，冻结协议为1.0.0；Python/合约包为0.1.0、审计UI为0.9.0、业务UI为0.10.0，组件版本与开发阶段分别记录。

## 使用

- [业务台](http://127.0.0.1:8090/)：输入新任务、双组织审批、请求者确认执行、查看真实本地邮件。
- [动态只读审计](http://127.0.0.1:8091/)：自动读取新增动作，实时复核四节点、审批、交易和工具签名。8080是旧快照。
- [现场操作指南](docs/judge-walkthrough.md)：完整成功、拒绝、重复和UNKNOWN演示；无需阅读源码。

测试登录密码只在本机 `.local/phase10/20261026T123255815352Z/access.local.txt`。新邮件任务的审批与执行窗口已调整为 **24小时**（仍受任务自身截止时间限制），双审批后仍须请求者发起预约。旧任务及旧签名保持原期限，过期请新建一轮请求。

业务台以 Agent 对话为主：首条消息创建会话，后续消息保留同一 `session_id` 和上下文，刷新后恢复；点击“新建会话”才另开对话。选择旧版独立任务后直接输入新消息，会在原窗口幂等关联历史，不重跑原任务。授权范围固定于会话创建时，各轮仍有独立 TaskGrant；改变工具或附件范围需新建会话。审批和交易证据在“审批与证据”中查看。

左侧“删除”仅隐藏会话，不弹确认框；消息、审批、交易和工具回执仍保留在只读审计中。网页审批／执行和实时核验异步提交并自动查询结果；列表读取本地持久投影，不逐条查链。实际广播前交易哈希为空，广播后显示真实哈希；后台受理不代表执行成功。

自定义工具现在由 **OrgB 审核时选择 LOW/HIGH**，提交者不用填写风险；标签绑定精确版本并写入独立工具注册表。旧工具需 OrgB 明确复审，不会自动转为 LOW。LOW 会话由服务端 OrgA 测试身份签 EIP-712 授权，页面可设最长24小时、最大调用次数；有效范围内的查询免逐次审批。HIGH 须对精确调用完成双组织审批。原 `mail.send` 始终保留双审批、预约、工具二验和签名回执；通用 HTTP 仍只支持查询／推理。

默认文档／邮箱读取和自定义查询支持会话 LOW 预授权；额度跨轮共用。旧窗口发送新消息时，过期或耗尽会显示“重新授权并继续”，点击后签发24小时／50次新授权，用原消息ID继续，未受理消息不调用模型。已经受理的调用仍受原绑定及精确强审批约束；UNKNOWN不清除或重发，已结束会话不能重新开放。LOW 日志每5分钟／50条、续期边界或点击“结束会话并存证”提交累计 Merkle Root；续期不重置序号、不改旧根。“审批与证据 → 会话授权与批量审计”显示授权周期、区块、交易和根；8091 的 `conversation-…` 记录实时核验应为 `BATCH_VERIFIED`。在途调用尚无结果时不能封存最终根。根只证明包含性；附件仍沿原本地文档授权，不冒充链上 LOW 认证。

邮件提议时保存消息、工具批次及游标并挂起；OrgA／OrgB 各自批准后，请求者确认预约执行。原工具回执与四节点 finalize 核验通过，Agent 自动继续接话；UNKNOWN 只查原回执，不续模型或重发。快照不包含模型未返回的内部推理。24小时配置只适用于新任务；历史记录继续按原签名域与期限验证。

旧窗口恢复、自然60秒授权到期、显式续签、原消息重提、真实双审批邮件和双周期LOW根验收：` .\.venv\Scripts\python.exe scripts/check_conversation_renewal.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/conversations/my-new-renewal `。实际调DeepSeek并产生1封本地邮件，使用独立私库及临时8092/8093，输出目录须不存在；现有证据见`results/conversations/20261029-renewal-01/summary.json`，不当作ASR实验。

一条命令复现真实模型的“总结 → 同会话发送 → 双审批 → 链与邮件核验 → 自动续聊”、UNKNOWN 恢复及网页刷新（独立业务存储，实际产生两封本地测试邮件；新输出目录）：
```powershell
.\.venv\Scripts\python.exe scripts/smoke_conversation_sessions.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/conversations/my-new-run --web
```
原件只读复核：` .\.venv\Scripts\python.exe scripts/verify_conversation_sessions.py --source results/conversations/my-new-run --out results/conversations/my-new-verification `。它检查真实模型请求中的前轮记忆、两门持久记录、原 MIME、工具签名及四节点，不调用模型或重发。旧任务级 SessionGrant／批次继续兼容，以下脚本用于旧轨验收。

一条命令复现新网页、真实 DeepSeek、LOW/HIGH、过期／超额／重放／UNKNOWN 与四节点批次核验（需现有本地链、测试签名卷及模型配置；输出目录须不存在）：
```powershell
.\.venv\Scripts\python.exe scripts/smoke_tool_sessions.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/sessions/my-new-run --web
```
原件独立复核：`scripts/verify_tool_sessions.py --config <同runtime> --source results/sessions/my-new-run --out results/sessions/my-new-verification`，用同一 Python 运行，不重调模型或工具。并发审核复现用 `scripts/check_tool_session_concurrency.py --config <同runtime> --out results/sessions/my-new-concurrency`，两独立业务进程真实争用 epoch，核对原交易 nonce 和四节点 receipt。当前证据见 `results/sessions/20261028-resume-01/summary.json`。已有环境升级顺序为 `update_default_tools.py --feature sessions --apply`、`setup_tool_sessions.py`（均带原 config 和独立新 results/sessions 输出），再按下文重启 Web；不会重部署原三个 Registry。

工具接入统一在“工具与设置 → 接入与管理”的“接入方式”：默认通用 API，可切换 GitHub 应用模板或 CSV/JSON 个人数据。GitHub 模板内展开“仓库策略与验证”查看准入与探测，不再单列顶层标签；其专用只读适配器继续强制链上仓库限制，不能通过通用 API 绕过。

通用 API：选择通用 API 后展开“接入通用 API 工具”，填写 HTTPS 地址、GET/POST、URL 参数和 JSON Body；提交后切换 OrgB 审核地址、参数和查询／识别用途，启用后选择请求配置准备 Agent 任务。Agent 通过原网关实际请求，只能使用已审核参数；修改地址或参数须提交新版本。支持无密钥 JSON API；不支持认证Headers、浮点请求参数、二进制图片上传或任意写操作。图片URL可放在Body中，但须接入真正的识别服务；“HTTP 回显示例”只验证连通性。API返回的状态码/时间/响应摘要可查看，审计明确标为非链认证，GitHub保留原链上仓库限制。

已有环境安装此适配器：先运行 ` .\.venv\Scripts\python.exe scripts/update_default_tools.py --feature http --config .local/phase10/20261026T123255815352Z/runtime.json --out results/http-tools/new-upgrade --apply `，再运行 ` .\.venv\Scripts\python.exe scripts/setup_http_reader.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/http-tools/new-reader `，最后按下文重启Web。本机已完成；脚本保留原卷、回退容器及链，不重放历史UNKNOWN。新网页/真实DeepSeek/外部HTTPS一条命令：` .\.venv\Scripts\python.exe scripts/smoke_http_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/http-tools/new-smoke `。只读复核加 `--verify-source results/http-tools/20261028-generic-01/live-04` 并换新out；不重调模型或HTTP。测试使用独立临时业务存储，不向8090添加演示任务，不发邮件或交易。

对话框“添加文件”支持 DOC/DOCX、文字型 PDF、UTF-8 TXT/MD，每任务最多4个、每个5MB。上传后输入“读取附件并总结，引用段落或页码”；如需文件，勾选“允许生成 / 修改 Word、PDF 副本”，输入“将 Alice 改为 Bob，生成新的 Word 副本和 PDF 摘要”。结果区提供实际文件下载、摘要和引用位置，刷新后仍可下载。可在“工具与设置”取消邮件等无关工具。修改保存新副本，保留原件；DOCX 改动段落使用纯文字格式，PDF 修订为重排文字版，不保留图片、表单或数字签名；扫描件暂不做 OCR。附件内容始终是不可信资料，不能增加邮件权限。文档是本地结果，不冒充 R2 链上认证；若要求发送摘要，仍须原双组织审批及预约，仅发送文字，不发送文件附件。

文档运行环境首次安装：` .\.venv\Scripts\python.exe scripts/setup_document_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/documents/new-setup `，然后按下文重启 Web。构建只打包document_tools三份源文件，无私密数据；运行时无网络/主机挂载、非root、只读根文件系统，私有附件与结果AES-GCM持久化，100MB总配额。真实文件及可选网页/DeepSeek验收：` .\.venv\Scripts\python.exe scripts/smoke_document_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/documents/new-smoke --web `。输出目录须不存在；使用合成文档和独立临时业务存储，调用真实模型但不发邮件或链交易。同会话后续轮保留附件授权；旧独立任务不自动迁移。

在左侧“工具与设置 → 任务授权”统一勾选默认/已启用自定义工具及资源，或点击“搜索并总结文档 / 读取后发送摘要 / 读取本地邮件”示例，再创建任务。示例只填写输入，不预填执行结果。读取只针对两份合成测试文档和明确勾选的本地邮箱；只读完成显示 READ_COMPLETED，无需链上预约。发送摘要仍须原双组织审批。删除保持禁用。

“工具与设置 → 接入与管理”集中提供 CSV/JSON 导入、自定义工具版本注册、OrgB 准入与真实 GitHub 接入。自定义工具支持只读结构化资料查询：requester填写名称、记录键、返回字段与JSON资料，提交待审版本；security身份审阅本版本的数据/Schema/摘要并启用；requester再在任务中勾选该工具及允许的记录键。可输入“查询DEMO-1的负责人和状态”，也可组合mail.send发送查询摘要。只读任务无需链预约，发送仍须原双组织审批。资料变更产生新版本，停用后工具端拒绝新查询。现有可信适配器为dataset.lookup、github.read和http.request；API地址须在提交时固定并审核，不接受任意脚本或新的高风险写工具。

真实 GitHub 工具已接入，并增加独立 `RepositoryReadPolicy` 链上仓库准入。当前只允许 `microsoft/vscode`；其他仓库默认拒绝，无需 GitHub Token。任务精确资源授权与链上仓库策略必须同时通过，OrgB 启用目录不能扩大链权限。读取服务与工具分别核验两个 Besu 节点，链不可用时拒绝降级。只支持公开仓库元数据及精确 Issue，不克隆/写入；仓库授权不包含全部 Issue。链上准入不证明 GitHub 正文真实性，R0 查询不产生 R2 预约/回执。

现场验收：requester 在“工具与设置 → 接入与管理”展开“接入真实 GitHub 只读工具”→“填入 VS Code 验收用例”→提交；security 审阅并启用；requester 勾选三条测试键→“用本版本准备 Agent 任务”。输入“调用本工具查询 microsoft/vscode#1 的标题、状态与内容”并创建，展开调用记录核对 HTTPS 来源和链上准入高度。再创建查询 `facebook/react#1` 的任务，或选中原任务，在“工具与设置 → 接入与管理 → 应用模板 · GitHub → 仓库策略与验证”点击“测试其他仓库被链上拒绝”：应为 `GITHUB_REPOSITORY_DENIED`、`chain_enforced=true`、GitHub 请求数不增加。模板刻意允许本地查询 react，以证明拒绝来自链上；`microsoft/vscode#2` 未列入任务范围，另一个按钮应返回工具端 `UNAUTHORIZED_SCOPE`。页面的“GitHub 链上仓库策略”显示合约、双组织策略交易与实时高度。

一条命令新建两条可见任务并核对真实模型、工具原卷、HTTPS 原始响应和动态审计（调用真实模型，无邮件）：
```powershell
.\.venv\Scripts\python.exe scripts/test_github_policy.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/github/my-new-acceptance
```
输出目录必须不存在。增加 `--verify-source results/github/20261028-policy-01/live-03` 并换新输出目录，只读核验原件，不重新调用模型/GitHub。每条读取用 `eth_call` 查真实链策略，不单独发交易；策略变更的交易及四节点 receipt 见部署证据。测试版本保持启用供人工复验；不能将它的 R0 OrgB 准入当作双组织链治理。

GitHub 实测与只读复核入口：`.\.venv\Scripts\python.exe scripts/smoke_custom_tools.py --github --config .local/phase10/20261026T123255815352Z/runtime.json --out results/custom-tools/my-github`。两条新真实模型/API查询使用隔离业务存储，不新增现场任务、不发邮件或交易；加 `--verify-source results/custom-tools/github-20261028-01` 并换输出目录只读复核原始HTTPS响应、工具日志和模型记录，不重新请求GitHub。当前结果索引为 `results/github/20261028-01/summary.json`。

当前运行镜像为 `chainguard/resilience:0.10.9`，保留会话、24小时邮件配置及原 GitHub 策略。以下为历史 GitHub 适配器安装顺序，不应用它降级当前镜像：`update_default_tools.py --feature github-policy --config <本地runtime路径> --out <新results/github目录> --apply`，再 `setup_github_policy.py --config <同runtime> --out <另一新results/github目录>` 部署/恢复独立策略及读取服务，最后按原脚本重启Web。新环境须先运行 `setup_github_reader.py` 建立读取服务。原三个 Registry、原私有卷和冻结协议保持；回退旧无策略镜像不保留本轮链上仓库限制。匿名限流/失联明确报错；原 QBFT 网络不是 internal，固定域名/GET 是读取服务约束，尚无域名防火墙。

也可选择 UTF-8 CSV/JSON 文件，校验预览后填入待审版本。CSV 默认保留字符串编号，整数/布尔列须显式指定类型；预览不会注册或运行任务。版本审阅支持“以此版本修改资料”、父版本差异/事件历史，以及选记录后“用本版本准备 Agent 任务”；仍需自行提交、审核及点击创建任务。dataset.lookup仍是导入快照；github.read与http.request实际联网，前者固定GitHub资源，后者固定已审核API配置；不接受Agent临时指定URL或脚本。

导入与版本链路真实验收：`.\.venv\Scripts\python.exe scripts/smoke_custom_tools.py --management --config .local/phase10/20261026T123255815352Z/runtime.json --out results/custom-tools/my-management`。在隔离业务存储运行两条真实模型查询，不发邮件、不写链；增加 `--verify-source 已通过的结果目录` 并换输出目录可只读复核原数据/日志/模型记录，不重新执行。

注册表单新增“填入联系人查询示例”和“填入库存查询示例”：分别填入合成联系人、本地测试邮箱，以及含数量/预警线/仓库的库存资料。按钮只填写输入，仍需提交与安全审核。启用后，仅勾选相应工具和目标记录：可问“查询 CONTACT-001 的姓名、部门和本地测试邮箱”，或“查询 SKU-002 的数量、预警线并判断是否需要补货”。只读任务请取消mail.send；查询不赋予发信、调整库存或采购权限。

两示例真实网页/DeepSeek验收：`.\.venv\Scripts\python.exe scripts/smoke_custom_tools.py --examples --config .local/phase10/20261026T123255815352Z/runtime.json --out results/custom-tools/my-examples`。临时8092/8093、独立业务存储，真实注册/审核/查询后停用测试版本；不发邮件、不新增预约。只读复核可增加`--verify-source results/custom-tools/20261028-examples-01/real-smoke-01`并换输出目录，不重调模型或查询工具。

真实网页验收（使用独立8092/8093与测试存储，会实际发送一封本地邮件）：`.\.venv\Scripts\python.exe scripts/smoke_custom_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/custom-tools/my-smoke`。只读复核原数据/查询/模型记录、参数承诺、MIME及四节点：同命令增加`--verify-source results/custom-tools/20261028-02/real-smoke-03`并更换输出目录；不调用模型、不重发邮件。容器升级沿用update_default_tools.py，指定`--feature custom`及results/custom-tools新目录；保留原卷和回退副本。

真实模型冒烟：`python scripts/smoke_default_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/default-tools/my-smoke`。使用已有环境和模型Key，在独立业务测试存储运行三条真实模型流程，创建一封本地邮件；报告含真实交易与MIME摘要，不计入ASR。已有容器升级命令：`python scripts/update_default_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/default-tools/my-upgrade --apply`，随后运行下文Web恢复命令；保留卷和停止的回退容器，不重置链。

只读复核本轮三任务：`python scripts/smoke_default_tools.py --config .local/phase10/20261026T123255815352Z/runtime.json --verify-source results/default-tools/20261028-01/real-smoke-01 --out results/default-tools/my-verification`。核对原工具卷读取日志/实际文件与MIME、模型邮件参数承诺及四节点签名交易；不重调模型、不重新执行工具。

界面参考 [Linear](https://linear.app/) 的侧栏与信息层级，使用独立实现的共用组件 `shared/`。重新构建页面：`npm.cmd --prefix console run build`、`npm.cmd --prefix dashboard run build`；原Web服务读取各自dist，无需重建链。对话与设置只读回归：`node console/tests/conversation-browser.mjs .local/phase10/20261026T123255815352Z/runtime.json results/ui/my-chat-review`。检查草稿/范围切换、真实历史调用与邮件、独立身份及手机布局，不创建业务任务。原只读浏览器回归：`node console/tests/ui-review.mjs .local/phase10/20261026T123255815352Z/runtime.json results/ui/my-review`，输出路径须不存在；检查真实登录、既有邮件和链证据，不新建任务或发送邮件。

```powershell
# 在 D:\CCF 恢复已有Web服务，保留任务与数据卷
.\scripts\restart_phase10.ps1 -Config D:\CCF\.local\phase10\20261026T123255815352Z\runtime.json
# 独立核验你刚创建的业务任务；输出目录必须不存在
.\.venv\Scripts\python.exe scripts/verify_demo_task.py --task-id 你的完整业务任务ID --out results/phase10/my-verification
```

已有环境依赖：Windows PowerShell、Python3.14.4、Node22.23.1、Ubuntu WSL2 Docker、原四Besu及阶段5部署、忽略目录中的测试密钥与固定wheel缓存。模型Key仅从 `.env.local` 安全读取。已有配置恢复不等于空白机器部署；首次依赖安装见 [环境说明](docs/phase1-environment.md)，链部署见 [链运行说明](docs/phase4-runbook.md)。不得删除原卷或重置链。

`BACKEND_UNAVAILABLE` 表示执行网关/可信桥暂时失联，`CHAIN_UNAVAILABLE` 表示实时链核验未通过；均不能据此判定动作未执行。2026-10-29 已修复周期核验创建 TLS 上下文导致的网关内存超限退出，并配置有限内存和自动重启。只读压力复验：`.venv/Scripts/python.exe scripts/check_rpc_memory.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/maintenance/<全新目录> --iterations 400`；不调用模型、不发邮件或交易。恢复后刷新页面查询原动作，UNKNOWN 不重新发送。证据入口为 `results/maintenance/20261029-gateway-oom-01/summary.json`。

## 验证与实验

最新 [2026-10-29 A/B/C 实跑报告](results/phase8/abc-rerun-20261029-01/report.md)：60条真实模型对照与138条协议观测分别核验，原始指标、置信区间、交易/MIME证据和复现命令均在报告中；前置和历史样本不混算。

[C为何需要区块链：机制补验](results/phase8/bc-contribution-20261029-01/report.md)另外实跑65条B/C观测，展示共同治理、预约互斥与公共元数据取证的条件性增益，同时保留强中央对照、C的双工具库重复反例和性能成本；不宣称C全面优于所有中央架构。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd test
npm.cmd --prefix console test
npm.cmd --prefix dashboard test
.\.venv\Scripts\python.exe scripts/build_specs.py --check
.\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
```

[实验使用说明](evaluation/README.md)包含固定协议轨、真实模型轨、摘要任务重复实验和原卷复验。三组共用任务与模型配置；A保留账号授权及任务策略shadow，B/C强制相同冻结策略。真实模型攻击率与固定trace拦截率分别统计，错误和未知不丢弃。

## 维护入口

内部 mTLS 叶证书按用户选择有效 **7天**，本地 CA 为365天。当前一批叶证书到期为2026-11-04约22:10（北京时间）；续期后以检查输出为准。演示前检查证书、当前卷与指纹，距到期不足24小时返回 `NEEDS_RENEWAL`：
```powershell
.\.venv\Scripts\python.exe scripts/renew_phase10_mtls.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/maintenance/my-tls-check
```
续期使用同命令换一个新的输出目录并加 `--apply --days 7`。脚本检查空闲状态、保留原私钥和角色，将CA／叶证书与精确指纹一并更新，重启原网关／工具及Web；备份只放忽略目录及私有卷，失败恢复原文件。不会重置链或重放UNKNOWN。当前为手动续期，没有自动定时续签；结果目录必须不存在。

- [架构与边界](docs/architecture.md)、[接口及冻结契约](docs/contracts.md)。
- [当前进度及剩余缺陷](docs/progress.md)、[接手记录](docs/handoff.md)、[决策记录](docs/decisions.md)。
- 阶段历史说明已合并到 [历史归档](docs/history.zip)，原路径和逐文件SHA-256见 `docs/history-index.json`；`python scripts/tidy_docs.py --check` 可复核。冻结规范与原测试证据保留。

源码交付使用 `python scripts/make_source_bundle.py --out results/remediation/my-source-bundle`，包含尚未提交的阶段10源码及逐文件摘要，排除私密运行数据。它不替代Git提交或空白机器部署验收。

当前限制：同机节点/测试审批身份，非生产机构隔离；不支持完整C组R3和真实外部SMTP；官方AgentDojo仅明确适配子集，不是完整排行榜成绩。参数承诺保护参数一致性，不代替内容语义审查。UNKNOWN不盲目重发。许可证等待项目所有者选择，当前不授予额外开放授权。
# 连续会话验收（当前增量）

打开 `http://127.0.0.1:8090/`，请求者点击“新建会话”，选择初始工具/附件范围并发送第一条消息。之后直接在输入框继续提问，消息追加到同一会话，刷新仍保留；改授权范围需新建会话。历史独立任务不自动合并。

可先要求“读取 meeting-notes，总结负责人，不发邮件”，再说“把上一条摘要发给 alice@inbox.chainguard.invalid”。LOW读取用OrgA会话签名免逐次审批；邮件挂起在精确动作，两组织分别登录审批，请求者在24小时任务窗口内确认预约执行。finalize和工具回执核验通过后，Agent自动在同一会话接话。UNKNOWN只查原回执；旧120秒动作不会被延长。

点击“结束会话并存证”提交剩余LOW会话根；审计台8091可核验LOW包含性与独立HIGH预约/回执。LOW根不是邮件成功证明。附件沿原本地文档沙箱授权，当前不冒充链上LOW凭证。

新建合成测试（真实DeepSeek、两封本地测试邮件、真实链；结果目录必须不存在）：

```powershell
.\.venv\Scripts\python.exe scripts/smoke_conversation_sessions.py --config .local/phase10/20261026T123255815352Z/runtime.json --out results/conversations/<新目录> --web
```

只读独立复核，不调用模型/工具/签名或新增交易：

```powershell
.\.venv\Scripts\python.exe scripts/verify_conversation_sessions.py --source results/conversations/20261029-implementation-01/live-02 --out results/conversations/<新核验目录>
```
