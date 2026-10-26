# 阶段5验收记录

日期：2026-10-26，Asia/Shanghai。状态：**实现、自动化测试及本地Besu技术验收通过，等待用户验收**。没有进入C网关、工具查链或Agent阶段。

## 修改文件与实现

- 新增`contracts/PolicyRegistry.sol`、`ExecutionRegistry.sol`、`AuditRegistry.sol`：双组织治理、当前角色/scope及绑定、冻结策略epoch、跨组织审批、防重放/一次预约、工具签名审计及UNKNOWN追加对账。
- 新增`spec/phase5/governance.json`：独立治理EIP-712、payload ABI、时间/nonce/epoch及权限约束；不修改原ActionIntent/ExecutionReceipt。
- 新增`scripts/lib/phase5.cjs`、`deploy_phase5.cjs`、`verify_phase5.py`、`check_phase5.ps1`：共用签名编码、本地真实部署/正反交易、四节点receipt核验、独立Python digest核验和回归入口。
- 新增`tests/solidity/registries.spec.cjs`：30项业务合约测试；保留41项原协议/golden回归。
- 新增本阶段三份设计/接口/验收文档与`results/phase5/`证据；更新README及五份architecture/contracts/decisions/progress/handoff上下文文档。

核心字段与状态每一项、治理写协议、工具端责任和下一阶段依赖详见[phase5-contracts.md](phase5-contracts.md)。原三个ABI接口逐一实现，扩展函数不改变原入口。OpenZeppelin 5.4.0、Hardhat 2.26.3、ethers 6.15.0、solc-js 0.8.28均沿用锁；optimizer runs=200，evmVersion=paris，与已激活London的Besu25.10.0兼容。无新增依赖、无编译器下载、无viaIR配置变更。

## 实际运行命令与结果

在`D:\CCF`的PowerShell运行；新输出在results/phase5，没有覆盖阶段0–4历史证据。

| 实际命令 | 结果 |
|---|---|
| `.venv/Scripts/python.exe scripts/build_specs.py --check` | PASS |
| `.venv/Scripts/python.exe scripts/freeze_phase3_policy.py --check` | PASS，8份共享输入匹配 |
| `.venv/Scripts/python.exe -m pytest -q --junitxml results/phase5/baseline/pytest.xml` | 修改前144 passed |
| `npm.cmd test` | 修改前41 passing；新增模块后71 passing（原41+新30） |
| `npm.cmd run compile:interfaces` | 新增12个Solidity编译单元成功，EVM paris；该旧命令名现会编译整个contracts树 |
| `node_modules/.bin/hardhat.cmd test --grep 'Phase 5 PolicyRegistry'` | 7 passing |
| `node_modules/.bin/hardhat.cmd test --grep 'Phase 5 ExecutionRegistry'` | 15 passing |
| `node_modules/.bin/hardhat.cmd test --grep 'Phase 5 AuditRegistry'` | 首次7 passing/1 failing；修正隔离分支的用例后8 passing |
| `scripts/chain.ps1 -UseWSL -Action health` | 本轮修改期间4节点在线、各3 peer、正确genesis/身份/验证者；只读 |
| `node.exe scripts/deploy_phase5.cjs --out results/phase5/besu-run-01` | PASS，27笔真实交易：17笔成功、10笔预期回滚；共同高度1247→1274 |
| `.venv/Scripts/python.exe scripts/verify_phase5.py results/phase5/besu-run-01` | PASS；从4节点重取108份receipt，核对实际合约代码及Python/Solidity部署域digest；21+8冻结文件不漂移 |
| `scripts/check_phase5.ps1 -VerifyRun results/phase5/besu-run-01 -EvidenceDirectory D:/CCF/results/phase5/checks/final-20261026` | PASS，144 pytest / 71 Hardhat，部署后只读复核通过；日志位于该checks目录 |

模块日志为policy-test.txt/execution-test.txt/audit-test.txt，全部回归为hardhat-final.txt，部署逐笔输出为deploy-run-01.txt，Python为python-verify.txt；都在results/phase5。最终一键入口复验输出另存checks目录，由progress.md记录实际结果，不用本表累加独立实验样本。

安全用例覆盖：合法R2/R3、缺少人审、同组织、重复地址、多角色不同席位、附加无效签名、requester/agent/tool signer审批排除、错请求者/伪造/错链错域/高s、参数/任务/nonce/期限篡改、过期/未来/过长TTL、角色/scope/组织全局撤销、agent解绑、策略撤销/epoch、防actionId/nonce重放、工具绑定/撤销、晚到证据、回执幂等与冲突、UNKNOWN与终态保护。

## 真实链部署和receipt

chainId=**20261026**；四个Besu25.10.0回环RPC8545–8548。genesis hash保持`0xcb4778cbcf96b2891907209e06448c518e82f7fa633c376efe4621761e072173`。部署前后均核对独立enode、4验证者、3 peer、非syncing和共同区块哈希。27笔交易每笔都保存4份相同原始receipt，并核对规范区块交易成员；Python随后独立重新查询。

| 合约 | 实际地址 | runtime字节数 |
|---|---|---|
| PolicyRegistry | `0x68EAD07579A2B75bA4B024F8e02D14fb60a72dAa` | 9871 |
| ExecutionRegistry | `0x5effbc396C8532801C2a5e7A4d903b7c8702878A` | 10532 |
| AuditRegistry | `0x5d505B4ad2c4596b3bA3742ca5B338eB4d05f2eE` | 6057 |

部署交易分别位于1248/1249/1250；完整hash、代码摘要、公钥、ABI、部署域、签名夹具及前后健康观测在[report.json](../results/phase5/besu-run-01/report.json)。

| 验收动作 | 交易hash | block / status |
|---|---|---|
| R2真实预约 | `0xcfb64f9e1000036058ceb984edd7edec9d64da3746deaa81bd74ed96d276cbeb` | 1253 / 0x1 |
| 相同action重放 | `0xe0c8d202929e58752eaf210f5f851c41b7741ac9186219d4ed103138a5fa85ec` | 1254 / 0x0 |
| 参数承诺篡改 | `0xc4bd000489d29b2105e2ae3bc2f558852eefdfd380df706ddcb809c7f377f24b` | 1256 / 0x0 |
| 已撤销审批角色 | `0x9d36661a6b764077b2c08aba824b8ed98d6b352d606dd0b5041da2cb59f8ceb6` | 1260 / 0x0 |
| R3三批准预约 | `0x40d35a4967ebb548ec32c013f20218a36588f88498c61582a19437e7fedee5d1` | 1262 / 0x1 |
| 工具签名REJECTED夹具确认 | `0xaea17cfa244875ca289d8f7b0074df503b89923c6ef4be859df655dbc7694ab6` | 1266 / 0x1 |
| UNKNOWN追加对账 | `0x88e8bf8be6d89f29b9a791f4e8971c4902eda207e9d647d898cb8966b26d521d` | 1270 / 0x1 |
| 已撤销工具角色回执 | `0x5854a49449397f9f3dc30c389acd868495e568f05ee2605b9a79c9597e5a00d7` | 1272 / 0x0 |

完整receipt文件为`results/phase5/besu-run-01/tx-01-...json`至`tx-27-...json`，明确包含status=0的真实预期拒绝，不把回滚当未发送。链上三份预约最终均为FINALIZED_REJECTED且nonce持续使用；相同回执再次提交成功但没有新审计事件。UNKNOWN原因保留，禁止finalize绕过reconcile。

**回执边界：** 本阶段签名回执是合约密码学测试夹具；Besu使用REJECTED表示没有派发邮件/删除，所有result/evidence承诺是测试输入。真实的是合约代码、签名验签、预约/回滚/状态和链receipt；没有声称真实mail.send/doc.delete已经通过C组链核验。OK/ERROR转换在本地EVM用签名夹具覆盖。真实工具结果签名和链下证据持久化仍是后续模块。

## 失败、限制与后续依赖

- 首次审计重放测试因夹具executedAt早于另一个意图issuedAt，先得到InvalidReceipt，而断言预期InvalidToolSigner。保留audit-test.initial-failure.txt；在两个动作建立后重新签原动作回执再篡改ID，8项重跑通过。未为迁就测试削弱合约时间校验。
- 普通exec启动继续报helper_unknown_error；按工具权限流程在获准运行后完成必要检查/测试/本地链交易。这是进程沙箱初始化问题，不是合约测试失败。没有自动审批拒绝遗留项。
- 测试角色私钥仅存忽略目录`.local/phase5/<run>/accounts.private.json`，现有测试链资金私钥仍在`.local/phase4`。无私钥/API Key提交或明文敏感参数上链。该目录的Windows ACL/独立组织密钥托管仍需部署方治理。
- 四验证节点同宿主，批准者测试密钥由同机操作员管理，不代表真实机构独立治理、生产安全审计或生产RPC认证。未做压力、性能或LLM攻击指标，不编造实验数据。
- Git仍无HEAD/0跟踪文件，没有自动add/commit；本阶段以新源码/证据清单辅助交接。原阶段4source-manifest是历史源码快照，其中README本阶段有明确更新；不重写旧快照掩盖这一变化，其他历史链源码/证据继续核验。
- 下一阶段依赖：C网关交易确认/错误映射/持久状态；工具独立查链及TaskGrant/参数/撤销再校验、永久幂等claim；真实工具ExecutionReceipt签名队列/加密证据；UNKNOWN原始日志对账。详见[接口依赖](phase5-contracts.md)。这些仍TODO，须用户指定后开始。

## 复现

```powershell
& .\scripts\chain.ps1 -UseWSL -Action up
# 每次建立新证据目录；部署不会清空链、重建验证者或释放旧nonce。
& .\scripts\check_phase5.ps1 -DeployBesu
# 已有部署只读复核（另存验证时间戳）与回归：
& .\scripts\check_phase5.ps1 -VerifyRun results/phase5/besu-run-01
```

重新部署会生成新的本地测试身份、合约地址和hash；协议和验收条件可复现，不承诺随机值逐字相同。若链离线先恢复原四节点，不用Hardhat替代实际Besu部署。等待用户验收阶段5。
