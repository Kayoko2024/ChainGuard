# ChainGuard 架构与实现边界

更新：2026-10-26，Asia/Shanghai。当前阶段9只读审计控制台、一键部署、真实HTTP/浏览器/链验证、受控干净重建和匿名PDF报告技术验收PASS，等待用户验收。阶段8真实DeepSeek与协议轨分列保留，完整官方AgentDojo任务仍不兼容，小样本结果不外推。本文为导航，不替换冻结规范；新增审计层见phase9-contracts.md/phase9-acceptance.md。

## 已实现模块

| 层 | 实际入口与职责 | 当前边界 |
|---|---|---|
| 协议 | `spec/`、`contracts/interfaces/`；字段、EIP-712、权限、状态机、HTTP契约 | 原21份文件冻结；新治理规范单列spec/phase5 |
| FastAPI | `gateway/src/chainguard_gateway/main.py` | 默认仅健康检查；显式注入central_service才提供中央接口 |
| A/B执行网关 | `central_api.py`、`central_service.py`、`identity.py`、`policy.py`、`approvals.py` | `/central/v1`真实中央流程，与C共享冻结策略 |
| 中央持久与审计 | `central_store.py`、`audit.py` | AES-GCM/SQLite、原子幂等和配额；B有真实签名追加日志及独立检查点验证 |
| 工具沙箱 | `sandbox_tools/src/chainguard_sandbox/` | doc.read、mail.send、doc.delete真实本地工具；Linux受限容器、SQLite执行记录、路径/作用域保护 |
| 工具中央适配 | `central_adapter.py` | 独立重验当前中央授权/签名/参数；不是C组链上核验 |
| QBFT链 | `chain/compose.yaml`、`scripts/chain.py` | 四Besu验证者、真实转账/RPC/持久与故障验收；阶段5复用原链不重置 |
| 业务合约 | `contracts/PolicyRegistry.sol`、`ExecutionRegistry.sol`、`AuditRegistry.sol` | 双组织治理、当前权限、R2/R3审批、一次预约/nonce、工具验签/UNKNOWN对账；真实部署证据results/phase5/besu-run-01 |
| C网关 | `chain_api.py`、`chain_service.py`、`chain_rpc.py`、`chain_store.py` | 冻结/v1的R2邮件子集、真实确认、加密队列、原hash恢复，无Agent签名入口 |
| C工具 | `sandbox_tools/src/chainguard_sandbox/chain_mail.py` | 独立节点2/4查链与当前签名人/参数/TaskGrant核验、原子本地MIME与签名回执 |
| C传输/启动 | `chain_transport.py`、`phase6_server.py`、`scripts/run_phase6.py` | 真实mTLS+独立Bearer、分卷/网络；测试代理仅转发真实Besu并注入失联 |
| Agent/模型边界 | `agent/src/chainguard_agent/` | Runner/Proxy/加密Journal；固定trace保留；真实DeepSeek独立配置、工具循环与脱敏请求记录已实测 |
| 读取/可信审阅 | `phase7_server.py`、`read_broker.py` | 独立R0测试capability；原高风险/v1路径与冻结策略不变，Agent无审批/工具凭据 |
| 基准适配 | `evaluation/workspace_adapter.py`、`check_agentdojo.py`、锁与vendor | 官方0.1.35/v1.2.2 workspace包/判定器原样；只映射邮件/按ID读取/删除，完整任务不兼容明确排除 |
| 协议实验/统计 | `evaluation/replay.py`、`metrics.py`、`phase8_plan.json`、`scripts/run_phase8.py`/`verify_phase8.py` | 真实服务/工具/四Besu；语义输入配对、seed调度、故障/篡改/重放/性能、Wilson/Bootstrap；无真实模型/正式ASR |
| 真实模型实验 | `live_plan.json`、`live_bridge.py`、`live_results.py`、`run_live_agent.py`、`verify_live_agent.py`、`run_real_experiments.py` | DeepSeek正常/注入/原判定器目标适配、同配置A/B/C；真实副作用和协议轨分开统计，不是全官方utility |
| 只读审计控制台 | `audit_projection.py`、`audit_verify.py`、`audit_console.py`、`dashboard/` | 原卷/链验证后公开投影、独立只读四节点核验、React；不持签名凭据、不改变执行权 |
| 交付与重建 | `deploy_phase9.py`、`rebuild_phase9.py`、`demo_phase9.py`、`docs/reports/` | 真实一键/冒烟、17步新目录重建、匿名PDF；复用OS/链，不称空白机器全重建 |

中央调用路径：登记身份/任务 → 确定性策略 → B组同一意图的请求者与独立批准签名 → 持久dispatch记录 → 工具再次核验 → 沙箱副作用/持久幂等结果 → 中央审计。A组执行常规账号授权，记录任务ABAC的shadow决策；B组强制任务ABAC和签名。B/C共享冻结策略，未来C在相同业务策略上增加真实预约及共同链历史。

## 链业务与待接入路径

目标路径：ActionIntent → 多组织审批 → ExecutionRegistry.reserve真实确认 → 工具独立查链/当前策略/承诺/时效 → 一次性副作用 → 工具签署ExecutionReceipt → AuditRegistry.finalize/reconcile。

上述路径已通过阶段6真实R2邮件场景，阶段7Runner复用同一路径。ChainMailTool是强制C入口；旧`LocalTestTools.execute_reserved`保留拒绝。中央成功结果仍不产生RESERVED/FINALIZED。阶段5回执仍是合约测试夹具；阶段6/7/8/9邮件回执来自真实本地MIME。UNKNOWN只查询原记录，审计断链保留原回执和签名交易；详见phase6-contracts.md。阶段8真实LLM和阶段9React已验收；其他C工具及完整原proof/verify/metrics API仍TODO，独立audit-api不替换原接口。

## 部署与信任边界

- gateway与链使用独立Compose项目；根`compose.yaml`只管原gateway，链使用`chain/compose.yaml`。默认健康API中的stage=1、显式中央服务stage=3表示该服务功能，不是整个项目进度。
- 本地链chainId=20261026，RPC回环8545–8548。4个独立JVM/身份/数据卷同属一台WSL宿主，不能声称四家组织独立运维或生产级拜占庭安全。
- 私有客户端账户在忽略目录`.local/phase4`；节点私钥在独立Docker数据卷。只读公开配置挂载不含私钥。Agent没有凭据或节点管理接口。
- 阶段5测试角色密钥在忽略目录`.local/phase5/<run>`。双组织EIP-712治理、不可变合约引用、禁用直接角色变更，协议见docs/phase5-contracts.md；测试密钥同机管理不代表机构独立托管。
- 阶段6工具密钥仅工具卷、relayer仅网关卷；原审批密钥的可信QA测试签名器与Agent权限分离。生成材料在忽略.local/phase6；三个新容器无宿主目录/公共端口，QA仅为验收代理而加入链网。节点1/3和2/4分别供网关/工具独立验证。
- WSL systemd服务不能单独维持发行版会话。`chain.py up`维护隐藏的专属WSL会话，`down`释放该会话、保留所有链卷；不修改全局代理/防火墙。
- RPC限本机可信操作员，尚无生产认证/mTLS/组织准入治理；host allowlist不是身份认证。文件副作用只允许容器内专用测试目录，邮件不访问外部邮箱。

## 可检查来源

- 原始目标：[需求矩阵](requirements-matrix.md)、[威胁模型](threat-model.md)。
- 协议入口：[contracts.md](contracts.md)；中央实现契约：[phase3-api.md](phase3-api.md)。
- 沙箱：[phase2-design.md](phase2-design.md)、[phase2-acceptance.md](phase2-acceptance.md)。
- 共享策略/审计：[phase3-design.md](phase3-design.md)、[phase3-acceptance.md](phase3-acceptance.md)。
- 链部署与真实证据：[phase4-runbook.md](phase4-runbook.md)、[phase4-acceptance.md](phase4-acceptance.md)。
- 业务合约/字段/状态及真实部署：[phase5-contracts.md](phase5-contracts.md)、[phase5-acceptance.md](phase5-acceptance.md)。
- R2闭环、恢复与实际副作用：[phase6-contracts.md](phase6-contracts.md)、[phase6-runbook.md](phase6-runbook.md)、[phase6-acceptance.md](phase6-acceptance.md)。
- Runner/Proxy、LLM扩展点、基准兼容性和本轮真实证据：[phase7-contracts.md](phase7-contracts.md)、[phase7-runbook.md](phase7-runbook.md)、[phase7-acceptance.md](phase7-acceptance.md)。
- 可重放协议实验、配对字段与统计边界：[phase8-contracts.md](phase8-contracts.md)、[phase8-runbook.md](phase8-runbook.md)。
- 当前验证和接手步骤：[progress.md](progress.md)、[handoff.md](handoff.md)。
- 阶段9只读接口/真实部署/匿名报告/干净重建：[phase9-contracts.md](phase9-contracts.md)、[phase9-acceptance.md](phase9-acceptance.md)、[demo-phase9.md](demo-phase9.md)。
