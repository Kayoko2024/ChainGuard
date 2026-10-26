# 阶段2验收记录

日期：2026-10-25（Asia/Shanghai）。状态：**阶段2本地测试工具验收通过，等待用户验收；不进入阶段3。** 机器结果为results/phase2/summary.json，acceptance=PHASE2_LOCAL_TOOLS_PASS。

## 输入和修改文件

输入：冻结的ReadParams/DeleteParams/MailParams、DocumentId、作用域、actionId、UNKNOWN语义；阶段1Python/Docker基础。设计先记录在docs/phase2-design.md，冻结21文件不修改。

| 文件 | 实现 |
|---|---|
| sandbox_tools/src/chainguard_sandbox/protocol.py | 读取冻结Schema，校验参数并复制调用数据，本地请求指纹 |
| sandbox_tools/src/chainguard_sandbox/storage.py | 容器边界、私有操作员密钥、SQLite表/事务、目录描述符 |
| sandbox_tools/src/chainguard_sandbox/resources.py | 操作员新建测试文档、可信资源映射、真实读取/删除及文件边界 |
| sandbox_tools/src/chainguard_sandbox/tools.py | 工具端精确测试许可、撤销/时效/作用域、持久actionId幂等、本地邮箱MIME和状态查询 |
| sandbox_tools/tests/test_protocol.py | 冻结参数与宿主拒绝/构建上下文测试 |
| sandbox_tools/tests/test_resources.py | 真文件、映射、软/硬链接、FIFO、内容篡改及删除边界测试 |
| sandbox_tools/tests/test_tools.py | 邮箱/读取/删除、并发、作用域、重启、进程强制终止与UNKNOWN测试 |
| sandbox_tools/Dockerfile | 固定Python镜像、无新增运行依赖、非root测试镜像 |
| scripts/run_phase2_container.py | 白名单tar构建，受限容器测试，无主机目录挂载 |
| scripts/phase2_evidence.py、phase2_evidence_host.py | 真实副作用、跨容器数据卷重放、独立SQLite/MIME核验与自身测试卷清理 |
| scripts/check_phase2.ps1、write_phase2_report.py | 完整回归、冻结文件校验、测试/证据/源文件SHA-256报告 |
| pyproject.toml、README.md、sandbox_tools/README.md、docs/phase2*.md | 测试路径、运行方法、字段/状态及实施边界 |
| results/phase2/* | 真实自动化日志、JUnit、SQLite快照、MIME邮件和验收摘要 |

## 验收命令

```powershell
& .\scripts\check_phase2.ps1 -UseWSL
```

脚本依次检查冻结Schema生成、宿主pytest、原Hardhat回归、resources/tools真实容器测试，再执行跨容器持久化验收。命令在仓库根目录运行。资源和执行器测试不在宿主机运行。

## 实测证据

首轮模块实测：参数模块23项、资源模块8项、执行器23项通过；随后增加恶意参数、宿主边界、并发删除等用例，最终完整验收实际通过如下。

| 检查/测试 | 实际结果 |
|---|---|
| 冻结规范 | Schema/OpenAPI生成一致；21份原文件SHA-256全部一致 |
| 宿主pytest | **83 passed**；原57项+阶段2无副作用校验26项；0失败/错误/跳过 |
| Hardhat | **41 passing**；共享EIP-712/ABI/golden vector回归 |
| 资源/持久化容器模块 | **8 tests OK**；真实读取/删除、软硬链接/FIFO/坏映射/内容篡改控制 |
| 执行器容器模块 | **26 tests OK**；含100次并发邮件调用、50次并发删除、25次删除重试、真实子进程崩溃 |
| 真实跨容器验收 | 第一个容器读出合成文档、投递1封MIME邮件、删除1个测试文件；第二个不同容器重放30次后仍3条执行记录/1封邮件，新增副作用0 |
| 独立核验 | 宿主sqlite3以只读方式打开实际导出快照，integrity_check=ok，逐项核对执行结果与MIME；邮件正文绑定实际读出的文档哈希 |
| 清理 | 本次容器与专用测试卷已移除；导出快照、MIME、日志及其SHA-256保留 |

共**158项自动化测试**通过，另完成跨容器真实副作用验收。自动化测试没有失败。一次容器测试执行请求被拒绝，尚未启动测试；用户随后明确授权后已实际运行，没有把未运行状态计为通过。

证据：results/phase2/pytest.xml、hardhat.txt、resources.txt、tools.txt；side-effects.json记录真实随机输入、文件/MIME哈希和两个不同容器的运行身份；execution-snapshot.sqlite3为真实SQLite导出，不含操作员密钥或原始令牌；mail.eml为从实际邮箱取出的邮件。summary.json和source-manifest.json保存证据/源文件指纹。范围外哨兵是另一个容器测试目录中新建的文件，没有使用真实主机文件。

运行隔离：非root UID10001、network=none、无能力、只读根；实测UID、根挂载只读标志、CapEff=0和仅lo网络接口。单元测试/sandbox为tmpfs，持久化验收只挂载本次新建的测试卷。真实邮件存于SQLite，没有SMTP外发；删除只作用于新创建的容器测试文件。无新增第三方运行依赖，沿用固定Python3.14.4镜像digest。

## 字段、状态与依赖

详细字段和状态见sandbox_tools/README.md。action_id永久唯一；同请求返回原结果，不同参数/工具/调用主体拒绝。资源权限由工具自己读取数据库：doc_id必须在精确白名单，受限scope和组织同时匹配，收件人除测试域还须在许可集合，删除必须显式开启并登记为disposable。

mail.send把许可消费、执行记录、逐收件人MIME和完成结果同事务提交；崩溃回滚不会留下半封邮件。文件原语先提交CLAIMED；完成后持久COMPLETED；确定操作前拒绝为REJECTED；结果不明或崩溃遗留对外为UNKNOWN，不自动重试。未知/拒绝不伪造成功，也不推进链终态。

## 已知限制和后续依赖

- LocalTestPermit是隔离测试的真实工具端授权，尚不是业务TaskGrant、多方EIP-712批准或链上RESERVED。正式execute_reserved返回CHAIN_UNAVAILABLE；业务HTTP仍未接入。
- doc.read的签名读取日志、ExecutionReceipt、加盐keccak承诺、加密证据和独立签名密钥未实现，明确TODO。本地request_sha256不作为params_commit。
- SQLite与文件系统不原子；实际进程崩溃测试验证UNKNOWN不重做，尚无人工/链上对账模块。SQLite合成测试快照未加密/签名，不声称防管理员篡改。
- 只支持受限Linux容器执行原语；Windows宿主拒绝创建沙箱。可信工具OS用户、操作员和Docker管理员属于信任边界，不声称抵抗同UID恶意工具进程。
- 沿用阶段1已验证镜像入口和版本；依赖无新增。完整业务授权、链核验、网络mTLS/服务身份、证据签名和对账是后续依赖，需另行指定阶段。

阶段结束等待用户验收。
