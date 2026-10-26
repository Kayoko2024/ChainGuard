# 阶段3验收记录

日期：2026-10-25（Asia/Shanghai）。状态：**阶段3验收通过，等待用户验收；不进入下一阶段。** results/phase3/summary.json的acceptance=PHASE3_CENTRAL_AB_PASS。

## 输入与修改文件

编码前范围已记录docs/phase3-design.md。输入为冻结阶段0字段/API/规则、阶段1健康网关、阶段2真实隔离工具。原21份冻结文件未修改。

| 文件/目录 | 实现 |
|---|---|
| gateway/src/chainguard_gateway/canonical.py、crypto.py、identity.py、policy.py、approvals.py | 严格JSON/JCS、冻结加盐keccak承诺和EIP-712、HS256 JWT、白名单、B/C确定性ABAC/RBAC和独立批准门槛 |
| gateway/src/chainguard_gateway/central_store.py、audit.py | AES-GCM持久数据、原子配额/幂等、固定部署身份、真实签名哈希链、追加保护及独立检查点核验 |
| gateway/src/chainguard_gateway/authorization.py、central_service.py | 请求者/Agent绑定、提议/审批/执行/查询、当前撤销/时效/参数再核验、UNKNOWN不重发 |
| gateway/src/chainguard_gateway/central_api.py、central_contract.py、central_server.py、main.py | 真实FastAPI/Uvicorn入口、错误信封、中心化契约、显式服务注入；默认实例保留健康端点 |
| sandbox_tools/src/chainguard_sandbox/central_adapter.py | 工具独立加载当前中央授权、再次核验签名/作用域/承诺；工具本身持有操作员凭据，原语许可不延长意图/任务的绝对到期时间 |
| gateway/tests/test_phase3_*.py、gateway/integration/*.py | 纯模块、真实工具/API、安全负例、Uvicorn进程和跨容器重启验收 |
| gateway/requirements.txt、requirements.lock、central-test.lock、central.Dockerfile、requirements-dev.lock | 精确密码学/JSON运行依赖、测试闭包、离线安装测试镜像 |
| config/phase3-policy-freeze.json、phase3-policy-draft-revisions.json | 共用8份规范/代码指纹，保留验收前一次非法曲线点错误处理的草稿修订原因 |
| spec/central/schemas.json、docs/phase3-api.md | 加法中心化API/ActionTrace/状态契约，复用原字段，不修改冻结链API |
| scripts/freeze_phase3_policy.py、prepare_phase3_wheels.py、run_phase3_container.py、phase3_evidence_host.py、check_phase3.ps1、write_phase3_report.py | 显式冻结/漂移检查、锁定轮子、受限容器、独立证据核验、一键回归和机器报告 |
| scripts/run_phase2_container.py、README.md、本阶段文档 | 修复WSL/GBK测试日志显示问题；更新运行/验收说明 |
| results/phase3/* | 实际测试日志、JUnit、OpenAPI、MIME、SQLite快照、ActionTrace、检查点和摘要 |

## 运行命令

```powershell
# 首次准备固定Linux轮子；仅下载依赖，不安装系统软件
& .\.venv\Scripts\python.exe scripts/prepare_phase3_wheels.py
# 完整验收（Docker在Ubuntu WSL2）
& .\scripts\check_phase3.ps1 -UseWSL
# 单独真实HTTP/副作用/重启验收
& .\.venv\Scripts\python.exe scripts/run_phase3_container.py --wsl-distro Ubuntu --evidence
```

默认check不重写策略或依赖锁；轮子准备后离线构建/安装。工具业务原语只在非root、network=none、只读根、无主机目录挂载的容器执行。实际API只监听容器回环，JWT/各类密钥由可信测试操作员在私有目录生成；审批私钥仅在独立签名测试进程内存中。没有真实外部邮件或主机文件删除。

## 实际验收和失败修复

首轮纯模块24项、审计12项、容器20项通过；加固后容器22项通过。最终完整验收如下，全部实际运行。

| 验收 | 实际结果 |
|---|---|
| 宿主pytest | **128 passed**，包含原协议/环境/健康/阶段2参数回归、JSON/JCS/JWT/策略/审批密码学及审计模块 |
| Hardhat | **41 passing**，原ABI/EIP-712/golden vector不变 |
| 中央网关/工具隔离容器 | **25 passed**，真实邮箱、默认/显式删除、读文档、签名/组织/角色、撤销/epoch、工具重验/调包、并发配额、幂等、审计损坏和UNKNOWN |
| 原工具模块回归 | **8+26 tests PASS**，读取/删除路径边界、链接、持久幂等、100次并发邮件、50次并发删除、实际子进程崩溃 |
| 合计 | **228项通过，0失败/错误/跳过**；首次失败记录另行保留 |
| 原规范/策略冻结 | 原21份SHA-256不变；B/C共用8份输入指纹检查通过 |
| 实际HTTP A组 | Uvicorn健康200且PID对应实际进程；正常发送和任务范围外发送各1封，邮箱2封；默认删除DENIED，测试文件保留 |
| 实际HTTP B组 | 正常发送有请求者+业务/安全真实签名后成功，邮箱1封；任务范围外发送与默认删除DENIED |
| 重启重放 | 第二个不同容器重新启动A/B服务，各重放10次，邮箱仍A=2/B=1；新增邮件0 |
| 独立证据 | 宿主只读核验实际SQLite完整性、逐封MIME/哈希；恢复B日志用第一次HTTP导出的独立检查点验证VALID；截去尾项验证INVALID |
| 安装与隔离 | 固定Python3.14.4与精确Linux依赖，实际pip check通过；非root UID10001、根只读、CapEff=0、仅lo网络接口，无主机目录挂载 |
| 关闭与清理 | 实际关闭生命周期日志完整、端口释放；本次容器及专用测试卷已移除，导出证据保留 |

B/C共享策略指纹：`0xea85b2decc8ac88a391b9f890fbfe4b7aa981f9f9103ca7313ce21afab3c214c`。原规则/字段不变；只在本阶段验收前补齐非法曲线点的显式拒绝，修订前后指纹和原因已记录。今后正常验收使用--check，不自动更新冻结文件。

证据在results/phase3：pytest.xml、integration.xml、hardhat.txt、sandbox-*.txt；a/b-openapi.json；a/b-mailbox.sqlite3、a/b-central.sqlite3；a/b-traces.jsonl；b-checkpoint.json和实际*.eml。http-side-effects.json记录真实HTTP响应、PID/关闭状态、两个不同容器身份、各组副作用数及重启结果。source-manifest.json和summary.json保存实际源文件及证据SHA-256。快照中无私钥、JWT或原始工具令牌，中央敏感数据为AES-GCM密文。

已检出并修复，不把未运行或中断当通过：

1. 首轮一个64KiB参数用例的pytest自动名称超过Windows环境变量上限，出现setup/teardown错误；改短用例名后通过，保存primitives.failed-windows-env.xml。
2. 加固固定部署配置时引入缩进错误，审计测试收集和容器导入失败；修复并复验，保存audit.failed-indent.xml、integration.failed-indent.txt。
3. 显示混合WSL诊断/UTF-8日志时，Windows GBK输出异常；保存原始日志，成功分支仅显示已验证计数，失败分支输出原字节。原沙箱脚本相同问题在完整回归中检出并修复，保留sandbox-resources.failed-encoding.txt。
4. Uvicorn0.38处理关闭后重抛SIGTERM，实际退出码可为-15；首轮仅断言0导致烟测失败。现同时核验实际生命周期完成日志、进程退出码0/-15及端口释放；不把SIGKILL当优雅关闭。保留http-prepare.failed-sigterm.stderr.txt。
5. 审查补齐execute幂等键跨action作用域，绑定主体+operation+完整含action_id请求，新增A/B负例；原始actionId永久去重继续保留。

## 共用策略、字段和状态

详细字段/API/状态见docs/phase3-api.md。B/C冻结输入是risk-rules、identifiers、eip712、protocol.schema及policy/approvals/canonical/crypto代码，共8份；策略指纹由规范化manifest哈希计算，每次启动/执行/工具调用核验。ABAC不依赖LLM或链，未来C从真实身份/策略源提供相同属性，增加真实预约和共同审计，不改变B的授权条件。

A/B使用相同任务模板、资源数据、账号权利、工具和基础规则。A有常规账号鉴权与统一沙箱不可逆操作上限，任务ABAC为shadow；B强制TaskGrant、当前身份/资源/时效/配额、请求者+跨组织审批签名、工具再核验和签名追加日志。HTTP无法切换组别，数据库改写组别与受保护部署文件不一致时拒绝。

正常结果是CentralActionRecord/LocalExecutionRecord，未生成链交易、ExecutionReceipt或FINALIZED状态。未知动作/响应丢失保留UNKNOWN且tool_executed=null，不自动重执行。

## 限制与后续依赖

- 本阶段为确定性API/工具对照，没有Agent、模型、AgentDojo实验或统计指标，不把几条用例称作攻击成功率。
- B/C业务策略相同，C仍需真实合约/Besu、链确认/撤销/身份适配、真实工具签名回执、加密证据对账；冻结/v1链路径未实现。
- 本地HS256 JWT签发由可信操作员管理；无生产身份提供商、密钥轮换、多组织治理写协议或外部网络mTLS部署。中央服务与适配器同容器/可信OS身份，Agent未接入，无工具凭据。
- B审计签名保护事件/判定/执行观测；完整结果在加密中央记录及工具库中。正式工具ExecutionReceipt签名仍TODO。运营者若同时掌握签名私钥、全部数据与检查点可重写历史，不能冒充多机构独立信任。
- 中央SQLite与工具SQLite/文件系统不原子，已测试丢响应保留UNKNOWN；跨库人工/链上对账与自动恢复待后续阶段。
- Linux x86_64/Python3.14.4镜像与Windows宿主纯模块已实测；其它架构未验收。全链审计/业务性能未测量。

阶段结束等待用户验收；不进入下一阶段。
