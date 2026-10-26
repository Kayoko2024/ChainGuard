# 阶段 0 验收记录

日期：2026-10-25（Asia/Shanghai）。范围：设计、接口、必要契约测试。当前状态：**阶段0交付待用户验收；业务模块全部TODO，不进入下一阶段。**

输入为设计方案V1.0及用户阶段0指令。目录初始为空、没有Git仓库。来源指纹记录在spec/baseline.json；没有修改下载目录的原方案。

## 新增文件与实现内容

| 文件 / 目录 | 本阶段完成内容 |
|---|---|
| README.md、.gitignore | 文件索引、复现命令、未实现范围与敏感文件排除 |
| docs/requirements-matrix.md | 17项MVP需求、来源、状态、本阶段证据和未来实际验收 |
| docs/threat-model.md | 参与者、凭据、11类攻击、强制边界和可信假设 |
| docs/permissions.md | R0–R3的任务授权、批准门槛、断链处理、拒绝结果 |
| docs/state-machine.md | 高风险17条转换、低风险7条转换、链状态8条转换及映射 |
| docs/protocol.md | ActionIntent全部14字段与ExecutionReceipt全部7字段逐项解释、承诺公式、签名域、时间与nonce规则 |
| docs/http-api.md | 11个HTTP操作的输入输出、鉴权、幂等、错误和对账语义 |
| spec/baseline.json、identifiers.json、risk-rules.json、errors.json、state-machines.json | 可机读的来源、登记映射、权限门槛、错误码和状态边 |
| spec/eip712.json | 签名字段类型/顺序、JSON映射和两个独立签名域 |
| spec/schemas/protocol.schema.json、spec/openapi.json | 严格DTO、整数上界、工具/参数绑定、未锚定/终态约束和OpenAPI3.1 |
| spec/vectors/eip712-v1.json | 真实签名的公开密码学向量、逐层摘要、规范化字节；无私钥、无业务交易声明 |
| contracts/interfaces/*.sol | 统一Solidity类型及三个合约接口；无业务函数实现 |
| contracts/test/ProtocolHashHarness.sol | 只用于本地EVM验证的真实哈希、承诺及OpenZeppelin验签 |
| tests/python/*.py、tests/solidity/protocol.spec.cjs | Schema/API/状态规范与跨语言密码学测试 |
| scripts/build_specs.py、generate_vector.py | 声明式接口生成/漂移检查；一次性公开签名夹具生成 |
| scripts/check_phase0.ps1、write_acceptance_report.py | 实际测试、失败退出、保存日志和从日志导出结果 |
| requirements-dev.txt、requirements-dev.lock、package.json、package-lock.json、hardhat.config.cjs | 阶段0精确依赖、锁定solc-js、本地EVM测试配置 |
| results/phase0/{pytest.xml,pytest.txt,hardhat.txt,summary.json} | 本机真实测试证据、环境和SHA-256；没有实验业务指标 |

## 核心字段、状态和依赖的验收入口

全部字段逐项定义在 [protocol.md](protocol.md) 的两个字段表：

- ActionIntent：schemaVersion、actionId、taskId、requester、agent、toolId、resourceScope、paramsCommit、policyId、policyEpoch、nonce、issuedAt、expiresAt、risk。
- ExecutionReceipt：schemaVersion、actionId、paramsCommit、resultCommit、evidenceIndexCommit、executedAt、outcome。
- 每项均注明JSON名称、Solidity类型、约束、生产者和消费者。大整数使用十进制字符串；时间采用排他到期；新加schemaVersion/issuedAt及状态变化在“相对原方案的明确细化”中记录。

每条状态转换的前置事实、责任模块和重试行为在 [state-machine.md](state-machine.md) 表中，机器清单在spec/state-machines.json。高风险必须经过AWAITING_APPROVAL、RESERVING、RESERVED和工具核验；回执先到EXECUTION_RECORDED，再凭真实审计交易确认进入FINALIZED_*。UNKNOWN只能查询原结果，不能重新执行或凭超时转失败。R0/R1采用独立READ_*路径。

后续模块按 [requirements-matrix.md](requirements-matrix.md) 的依赖顺序消费本协议：

| 模块 | 必要依赖与尚待实现 |
|---|---|
| 网关/任务/策略 | TaskGrant与身份绑定、严格JSON解析、资源范围与配额、参数承诺；真实服务TODO |
| 合约/链 | 本阶段类型/域/向量；先补治理写签名协议，再实现授权/防重放/回执及四节点QBFT |
| 沙箱工具 | 真实部署地址、可信链客户端、独立凭据与签名、沙箱资源、幂等日志、TaskGrant查询 |
| 审计/对账 | 工具真实回执、链事件及历史角色组织、加密原文与盐、持久补交队列 |
| Agent/评测/React | 可运行网关与沙箱、固定数据/模型及真实trace；前端延后 |

## 实际执行与结果

本机：Windows11、Python3.14.4、Node22.23.1、npm10.9.8；Hardhat2.26.3、Solidity0.8.28、OpenZeppelin5.4.0。精确Python包与环境由results/phase0/summary.json记录。

```powershell
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe -m pytest tests/python -q --junitxml results/phase0/pytest.xml
npm.cmd test
& .\.venv\Scripts\python.exe -m pip check
```

一键重跑：`& .\scripts\check_phase0.ps1`。

| 检查 | 真实结果 |
|---|---|
| Schema/OpenAPI生成一致性、OpenAPI3.1有效性 | 通过 |
| pytest | **33 passed，0失败、0错误、0跳过** |
| Hardhat | **41 passing**；接口及测试合约编译成功 |
| Python依赖一致性 | No broken requirements found |
| npm直接依赖版本核对 | 全部与package.json固定版本一致 |
| 私钥字段/常见私钥标记检查 | 仅命中测试中的禁止字段名称，未发现实际私钥；向量无私钥字段 |

密码学覆盖：Python eth-account与独立eth-abi重算、ethers重算、Solidity/OpenZeppelin重算；两个对象每个签名字段的篡改、签名域四个字段的篡改、公开签名恢复、盐变化、单字节变化、JCS UTF-16排序、Unicode不归一化、Keccak/SHA3差异、JS大整数边界、截断/错误v/零/高s签名。结构覆盖：越界整数、额外/缺失字段、外部邮箱、CRLF及尾部换行、路径输入、工具参数错配、无签名回执与未知结果冒充最终态。

首次 `npm install` 因默认缓存目录写权限EPERM失败，首次 `npm test` 因Hardhat用户配置目录写权限EPERM失败；获准重试后均成功。没有测试断言失败被隐藏或跳过。依赖安装还输出旧版传递依赖的弃用提示；本阶段未做依赖漏洞审计，不能据测试通过宣称依赖已通过安全审计。

## 已知问题与明确未完成项

- 所有业务模块与安全强制执行仍TODO；测试通过不证明工具隔离、跨组织治理、持久幂等或真实链防重放已实现。
- 治理写入的EIP-712类型/nonce/ABI需在合约阶段单独设计和测试；现有PolicyRegistry仅给出业务查询接口。
- R0/R1的签名读取日志、内容返回与批量锚定API留待读取模块阶段定义；高风险执行/回执接口已冻结。
- 身份历史、TaskGrant的可信查询/撤销、时间偏差阈值、链确认健康标准、加密证据取回和完整ProofBundle内容验证均需真实实现；Schema无法证明跨字段值相等或现实行为真实。
- Docker/Besu未部署；Hardhat是本地测试EVM，未做QBFT、负载、AgentDojo、A/B/C或性能实验。没有邮件投递或文件删除。
- 当前仅在所列Windows环境验证，尚未在Linux/其他Python版本验证。目录未初始化Git，因此没有Commit标识；依赖锁、设计与向量指纹和实际日志已保存。

阶段0已按范围交付，等待用户验收和下一阶段明确指令。
