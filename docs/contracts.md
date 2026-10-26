# ChainGuard 契约导航与冻结约束

更新：2026-10-26。本文索引已存在的接口，不建立第二套字段或状态机。发现与下列原规范不一致时先报告，禁止以新摘要覆盖冻结源。

阶段9新增独立只读`/audit-api/v1`，契约见[phase9-contracts.md](phase9-contracts.md)。公开投影及当前链核验不增加执行授权；原`/v1`、EIP-712结构/域、状态机、ABI与审批门槛全部不变。VERIFIED/HISTORICAL_ONLY/NO_RESERVATION/PENDING_RECEIPT/UNAVAILABLE/INVALID为观察结论，不是新业务状态。

**真实模型扩展更新：** 原字段/状态机全部保持；DeepSeek真实循环及A/B/C观测契约见 [live-experiments.md](live-experiments.md) 和 `evaluation/live_plan.json`。该轨的ASR来自实际模型与已核验副作用/原判定器；下文“真实LLM未完成/ASR未测”只描述此前固定trace及协议轨，不描述新模型轨。两轨永不混算。

## 唯一规范来源

| 内容 | 规范与对应实现/测试 |
|---|---|
| ActionIntent、ExecutionReceipt、EIP-712域/顺序/映射 | `spec/eip712.json`、`spec/schemas/protocol.schema.json`、[protocol.md](protocol.md)、`contracts/interfaces/ProtocolTypes.sol` |
| 跨语言固定向量 | `spec/vectors/eip712-v1.json`、`tests/solidity/`、`tests/python/`；向量不可自动重生成 |
| 参数/结果/证据承诺 | [protocol.md](protocol.md)、`canonical.py`、`crypto.py`；RFC8785 JCS与域分离加盐keccak256 |
| 权限与风险门槛 | `spec/risk-rules.json`、`spec/identifiers.json`、[permissions.md](permissions.md)、`policy.py`、`approvals.py` |
| 状态转换与guard | `spec/state-machines.json`、[state-machine.md](state-machine.md) |
| 冻结链HTTP与错误 | `spec/openapi.json`、`spec/errors.json`、[http-api.md](http-api.md)；阶段6实现R2子集，详见[phase6-contracts.md](phase6-contracts.md)，其余仍TODO |
| 已实现中央HTTP与状态 | `spec/central/schemas.json`、[phase3-api.md](phase3-api.md)、`central_api.py`/`central_contract.py`；前缀/central/v1 |
| 合约ABI | 原`contracts/interfaces/IPolicyRegistry.sol`、`IExecutionRegistry.sol`、`IAuditRegistry.sol`保持不变；阶段5实现对应三个Registry，治理扩展见`spec/phase5/governance.json`及[phase5-contracts.md](phase5-contracts.md) |

表内Python模块均位于`gateway/src/chainguard_gateway/`。21份原规范的完整路径/摘要由`config/phase0-freeze.json`列出；8份B/C共用策略输入由`config/phase3-policy-freeze.json`列出。指纹用于漂移核验，不是防恶意管理员的独立信任根。

## 必须保持的约定

- 协议文档版本1.0.0、schema_version=1、EIP-712 domain.version="1"。字段类型、字段顺序及snake_case/camelCase映射只从原规范读取；uint64/uint256的JSON表达是无符号十进制字符串。
- 完整参数使用JCS和独立32字节随机盐作承诺，原文/盐不上链。keccak256不能替换为hashlib.sha3_256。65字节secp256k1签名、合法v和low-s要求不变。
- 所有请求者/批准者签同一个ActionIntent；签名恢复地址、当前角色/组织、独立审批、参数作用域/承诺、版本和时效均须检查。不得由Agent自行降低risk或补报权限。
- R2/R3的C组执行必须具有真实预约、工具端当前授权二次核验和永久actionId幂等；nonce和签名不可重放。C组尚未实现时不能降级为中央执行并声称链上授权。
- 中央CentralActionRecord/LocalExecutionRecord与工具ExecutionReceipt不同。中央状态不等于链状态；普通转账receipt也不是工具执行回执。
- UNKNOWN、超时或丢响应不能判为“未执行”或重新执行；只有原始日志/回执及合规对账能够推进。终态不退回执行，reconcile不增加执行权。

## 三个域必须区分

| 使用场景 | chainId | verifyingContract |
|---|---|---|
| 原golden vector | 31337 | 向量固定fixture地址；不是已部署合约 |
| 已实现中央B组 | 0 | 部署审计公钥地址作为中央域标识；不是已部署合约 |
| C组合约（R2邮件已接入） | 实际Besu链20261026 | ExecutionRegistry=`0x5effbc396C8532801C2a5e7A4d903b7c8702878A`；AuditRegistry=`0x5d505B4ad2c4596b3bA3742ca5B338eB4d05f2eE`；部署results/phase5/besu-run-01，真实邮件results/phase6/run-06 |

ActionIntent域name为`ChainGuard ExecutionRegistry`；ExecutionReceipt为`ChainGuard AuditRegistry`。不把B组签名或固定向量签名迁入C组。

阶段5治理使用独立`ChainGuard PolicyRegistry`域和GovernanceChange结构，未改变上述两个原结构。每个字段/guard、治理payload ABI、暂停与晚到证据边界见[phase5-contracts.md](phase5-contracts.md)。合约测试夹具只验证验签/状态，不作为工具真实执行回执。

## 状态入口与验证

高风险业务规范主路径为PROPOSED → AWAITING_APPROVAL → RESERVING → RESERVED → EXECUTING → EXECUTION_RECORDED → FINALIZED_*，另有DENIED、EXPIRED、UNKNOWN及guard。链状态没有EXECUTING；具体全部边以机器状态机为准。R0/R1使用独立READ_*路径，不伪造高风险意图/预约。

已实现中央状态只有READY、AWAITING_APPROVAL、DENIED、CENTRAL_OK、CENTRAL_REJECTED、UNKNOWN；内部DISPATCHING对外未知。这是阶段3的独立契约，不是对链状态机的修改。

阶段6 C状态使用原状态机；网关dispatch_started为内部持久标记，不作为执行成功证明。工具真实回执确认后才记EXECUTING_CONFIRMED→EXECUTION_RECORDED；UNKNOWN只通过原回执恢复，链最终状态必须有真实audit证据。具体子集/字段依赖/未实现路径见phase6-contracts.md；原协议文件不修改。

阶段7的ToolCall、加密Journal、独立R0读取capability、可信审阅/观察接口和四项分离日志字段见[phase7-contracts.md](phase7-contracts.md)、`spec/agent/interfaces.json`。这些扩展不替换原高风险协议或状态机。Agent只能经原propose/GET查询，未知副作用保持null；固定trace attack_success=null、LLM样本0。原版AgentDojo锁/判定器自检与真实LLM攻防属于不同验证范围，后者尚未完成。

阶段8实验输出扩展见[phase8-contracts.md](phase8-contracts.md)，计划`evaluation/phase8_plan.json`；traces/cases/metrics/manifest不是第二套业务协议。共同输入SHA、逐样本语义配对、共同统计cohort、原签名审计与四节点/原卷独立复核，不改变任何冻结字段/状态。服务层协议驱动不运行Agent模型，真实LLM/ASR依旧未测。

```powershell
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
```

`build_specs --check`核对生成输出；完整原文件摘要还须核验phase0-freeze清单（宿主回归已包含）。检查失败时先保留失败、分析冲突；不要通过重写清单或向量“修复”检查。
