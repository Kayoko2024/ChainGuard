# 阶段6 技术验收记录

日期：2026-10-26，Asia/Shanghai。状态：**R2 mail.send首个真实C闭环实现和技术验收通过，等待用户验收**。未进入下一阶段。依据原完整设计、冻结阶段0与B/C策略，复用阶段5原部署，无新业务合约和依赖版本变更。

## 实现和修改文件

| 文件 | 内容 |
|---|---|
| gateway/src/chainguard_gateway/chain_crypto.py | 原wire/typed映射、真实域digest与工具签名/low-s验签 |
| gateway/src/chainguard_gateway/chain_rpc.py | 实际Besu双节点健康/共同提交、部署代码/ABI、receipt/事件/预约/当前审批核验 |
| gateway/src/chainguard_gateway/chain_store.py | C加密SQLite、持久原签名交易队列和观察事件 |
| gateway/src/chainguard_gateway/chain_service.py | R2任务/提议/批准/预约/单派发/原回执恢复/审计确认worker |
| gateway/src/chainguard_gateway/chain_api.py | 冻结/v1 R2子集、内部任务权威、结构与权限检查 |
| gateway/src/chainguard_gateway/chain_transport.py | 真实TLS证书指纹、独立Bearer、限长严格JSON |
| gateway/src/chainguard_gateway/phase6_server.py | 分别初始化/启动网关和工具；凭据隔离私有卷 |
| sandbox_tools/src/chainguard_sandbox/chain_mail.py | 工具独立查链、任务作用域/承诺/时效/配额、原子真实邮箱与签名回执 |
| gateway/tests/test_phase6_primitives.py | 10项密码学/ABI/加密/持久补投/重启/服务身份单元测试 |
| gateway/integration/phase6_lab.py | 真实mTLS客户端与测试故障代理；不伪造链/邮件结果 |
| gateway/phase6.Dockerfile | 固定基础镜像、原锁/校验wheel离线构建、非root服务 |
| scripts/run_phase6.py / verify_phase6.py | 新卷隔离完整验收；独立只读实时链/邮箱/MIME复核 |
| scripts/record_phase6_integrity.py | 原冻结/历史证据核对、当前源码与真实容器构建包匹配、只新增摘要文件 |
| docs/phase6-design.md / phase6-contracts.md / phase6-runbook.md / 本文件 | 实施输入、逐字段/状态/边界、命令和验收 |
| README.md、docs/architecture.md / contracts.md / decisions.md / progress.md / handoff.md | 当前导航、决策和完整交接 |
| results/phase6/ | 原始基线、成功与失败记录、交易/MIME/签名/冻结及源码证据 |

原21份协议、8份共享策略、三个Solidity合约和阶段5证据均保留；原A/B实现未改。旧execute_reserved继续拒绝，新的ChainMailTool是C唯一强制入口，不能通过旧接口离线放行。

## 命令与实际结果

```powershell
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest gateway/tests/test_phase6_primitives.py -q
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=results/phase6/final-pytest.xml
& npm.cmd test
& .\.venv\Scripts\python.exe scripts/run_phase6.py --out results/phase6/run-06
& .\.venv\Scripts\python.exe scripts/verify_phase6.py results/phase6/run-06 --tool-volume --out results/phase6/verification-06.json
```

run-06和verification-06已存在，复现必须选择新目录/文件；不覆盖历史证据。

- 实施前基线：pytest **144 passed**、Hardhat **71 passing**，results/phase6/baseline。上下文恢复后重新基线：pytest **149 passed**、Hardhat **71 passing**，resume-baseline.txt/xml、resume-hardhat.txt。
- 新模块：**10 passed**，primitives-resume.txt/xml。最终完整Python：**154 passed**，final-pytest.txt/xml。Hardhat本轮**71 passing**，resume-hardhat.txt；合约/依赖未修改，包含跨语言向量与既有安全回归。
- 冻结生成/策略检查PASS；只读核验再次核对原21+共享8份SHA-256，全部匹配。
- 完整真实验收：**run-06/report.json PASS**，四Besu共同高度**3556→3600**，chainId **20261026**。不是Hardhat本地链或mock RPC。
- **12笔实际链交易**：5次reserve成功、4次audit成功、1次markUnknown成功、2次重放预期回滚。逐笔四节点完整receipt共**48份**实时复核PASS；并重核规范区块成员/合约代码、审批签名、receiptHash、原工具签名与状态。
- **4封实际MIME**写入本地SQLite邮箱，每个成功actionId恰好1封；工具卷mode=ro独立读取并重算MIME/result/evidence承诺，公开4个mail-*.eml SHA-256吻合。工具断链场景投递数0。没有真实外部邮件或文件删除。
- gateway/tool/qa均非root、只读根、drop ALL、无发布端口/宿主目录；本轮均Running、OOMKilled=false。结束时QA **58.35MiB/1GiB**，tool **54.77MiB/512MiB**，gateway **57.84MiB/512MiB**；这是验收资源快照，不是性能实验。

## 场景与交易、副作用证据

| 场景 | 实际结果 | 原始证据 |
|---|---|---|
| 合法R2邮件 | 请求者+不同组织业务/安全签同一意图；预约确认后独立工具核验，真实投递并FINALIZED_OK | normal.txt、report.cases.normal、mail-1.eml |
| 越权与参数攻击 | 任务只许alice，bob为UNAUTHORIZED_SCOPE；外部域Schema拒绝；改body为PARAMS_MISMATCH；无真实预约拒绝；错mTLS/Bearer拒绝；Agent不能reserve | normal.checks及normal.txt；只有合法1封MIME |
| 重放 | 相同reserve/approve/工具动作只返原结果；换HTTP键/工具重启不增加投递；两笔真实动作/nonce重放均status=0、AlreadyReserved | replay-action-receipt.json、replay-nonce-receipt.json、post-restart.txt |
| 回执异常恢复 | 代理改result_commit使原签名失效，网关持久UNKNOWN；重启后错误回执仍拒绝；找回原回执经链上UNKNOWN→reconcile最终确认，无二次派发 | unknown.txt、recover-unknown.txt、mark-unknown-receipt.json、report.cases.unknown、mail-2.eml |
| 审计已送达后丢响应 | 实际Besu接收交易，再丢弃HTTP响应并断开网关RPC；本地EXECUTION_RECORDED/PENDING保留，重启查原hash成功确认 | pending.txt、recover-pending.txt、fault_events、mail-3.eml |
| 审计未送达即断网 | 实际节点查询证明原hash不存在；重启后只重投原签名字节，同hash确认、无二次邮件 | prebroadcast.txt、recover-prebroadcast.txt、report.cases.prebroadcast、mail-4.eml |
| 工具独立链失联 | 网关节点仍正常、工具节点对不可达；工具不投递，网关UNKNOWN；链恢复后仍无盲目重新执行 | tool-outage.txt、report.cases.tool-outage；邮箱无该actionId |

正常actionId：`0xdce90cef5dbf3cbd75cb1639b6b8800b16a0807fde79e293bdb733194c3e9fd6`。

| 交易 | 真实hash | 区块/status |
|---|---|---|
| 正常reserve | `0xd981973e4ed994a4f50606e92442803d3919314aa2b9f6dd02a1bfbce8e4a499` | 3567 / 1 |
| 正常finalize | `0xaaa2befc5b713bea34d6e514c28b6b2004d5512ef0045281ad3865182754697a` | 3568 / 1 |
| UNKNOWN原回执reconcile | `0x3ae8c5e04ac9fd55e1a82bd3b83f5bee12443809713bd877003c8b53c049c797` | 见tx-04-audit.json / 1 |
| 动作重放 | `0xc86c00d8e57fe7877380da08239e5ffa3320a2b4e91c49d0f78798fe3bfafef4` | 见replay-action-receipt.json / 0 |
| nonce重放 | `0xfc65b0cae1f7c938fb573e97e14b3b5a31d5059a8ddc1d8dccc91f22873437e2` | 见replay-nonce-receipt.json / 0 |

mail-1.eml SHA-256：`f52261662c34e7ac6c11a79e07534a4015f9d53a101cead70f70f007614c7312`；Message-ID绑定原actionId，To为`alice@inbox.chainguard.invalid`。结果transport明确为LOCAL_SQLITE_MAILBOX，不把合成测试邮箱当真实外部投递。

## 失败记录与修复

- 最初primitive 1通过/4错误：Windows默认GBK读取向量报UnicodeDecodeError，改为显式UTF-8后通过；原primitives.initial-failure.txt保留。
- run-01：启动健康mTLS请求EXECUTION_UNKNOWN超时，未完成完整验收。run-02：核心部分已过，后续docker exec失败/资源问题；原日志和report保留，不能标整体成功。
- run-03：旧代码完整通过3封邮件版本；后续审查发现SENDING尚未到节点时永远只查hash，及过早标EXECUTING问题。已修复并新增同签名补投/派发独立标记测试，旧成功不冒充新代码通过。
- run-04：恢复断链后预期FORBIDDEN，实际先收到CHAIN_UNAVAILABLE；安全拒绝未失守，测试改为有限等待恢复再强制检查FORBIDDEN，不能接受成功或其他错误。
- run-05：资源压力下tool-outage等待仍停RESERVING；实际观察QA达到1024MiB/1GiB。发现每个HTTP转发新建urllib opener会带入不必要TLS信任库/循环对象，改固定HTTPConnection并显式close，缓存必要TLS上下文。run-06完整通过，容器未OOM，资源快照如上。没有靠放宽授权、时钟或链健康检查通过测试。
- 最后摘要检查初次把阶段5证据清单的相对文件名按仓库根解析，FileNotFoundError；integrity-check.txt保留。新record_phase6_integrity.py按各旧清单原有相对目录解析，不重写旧清单，随后实际复核结果见integrity-final.txt/integrity.json。

## 已知问题和下一阶段依赖

仅实现R2本地邮件。其他工具、Agent/React、完整审计/metrics API、自动未派发动作过期收尾仍TODO；无原始明确回执的UNKNOWN按设计保留。单worker/专属relayer，不支持多实例竞争同发送账户。策略/工具签名人撤销后的原回执不绕过当前合约检查。保守链健康要求四节点全连，新执行前核验后的并发撤销仍存在时间窗口。

本地原子邮箱保证不适用于第三方SMTP。测试身份/四节点/审批密钥同机，真实mTLS也不等同生产HSM或跨机构运维。JWT15分钟、证书2天仅供本轮；需新运行刷新测试材料。公开证据只含合成MIME、公钥/签名/承诺；私钥、令牌、原参数盐留忽略目录/受控卷。

Git仍无HEAD、0跟踪文件；未擅自add/commit。source/evidence摘要帮助恢复，不替代独立版本历史。没有性能/攻击率实验结论，多个重跑不作为独立样本。

下一阶段须用户验收并明确指定；可复用本阶段真实链客户端、签名和待提交接口，进一步工具/审计/Agent均需保留工具端强校验、nonce与actionId永久去重、原回执恢复边界。逐字段与转换依赖见[phase6-contracts.md](phase6-contracts.md)，复现和恢复见[phase6-runbook.md](phase6-runbook.md)。
