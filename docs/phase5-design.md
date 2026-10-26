# 阶段5实施前记录

范围：仅实现 PolicyRegistry、ExecutionRegistry、AuditRegistry、必要治理协议、测试与本地 Besu 部署。不实现 C 网关、工具查链执行、Agent 或前端。用户已授权阶段5；此前交接中的“未授权阶段5”是历史状态。

输入：六份上下文文件、原始完整设计、冻结的 spec/eip712.json、risk-rules.json、identifiers.json、state-machines.json、三个只读/执行接口及 ProtocolTypes.sol；OpenZeppelin 5.4.0、Solidity 0.8.28、Hardhat 2.26.3，实际 Besu chainId=20261026。不改21份原规范或8份共用策略输入。

计划文件：contracts 下新增三个业务合约与共享签名库；spec/phase5 下新增治理契约；tests/solidity 下新增治理/预约/回执安全测试；scripts 下新增部署和验收入口；docs 及 results/phase5 保存设计、命令、原始 receipt、验收与交接。原冻结 ABI 保持实现兼容，新增治理和查询为扩展 ABI。

治理采用独立 EIP-712 GovernanceChange，绑定本 Registry、实际 chainId、完整 ABI 编码变更数组哈希、全局治理纪元、一次性 nonce 和排他期限。所有签名从当前登记恢复；至少两个不同组织的当前 GOVERNANCE_ADMIN 批准。构造时只引入两个不同组织的根批准者，不给任何单方 DEFAULT_ADMIN_ROLE；禁用 AccessControl 的直接 grant/revoke/renounce 路径。单方仅能紧急暂停；解除暂停必须双组织。此为阶段0明确留给合约阶段的治理写协议细化，不修改 ActionIntent/ExecutionReceipt。

链负责当前角色/组织、scope、requester-agent绑定、tool signer绑定、冻结策略组合/epoch、同意图签名、nonce/actionId和状态。TaskGrant、具体收件人/doc_id、完整参数和随机盐继续留链下，未来工具必须独立检查，不将预约等同完整业务执行授权。

验收：修改前建立 pytest/Hardhat基线；每个模块增测并实际运行。覆盖双组织治理/重放/撤销/暂停，R2/R3跨组织与不同账户分配、任一无效附加签名拒绝、请求者/agent/tool signer排除、错域/高s/伪造/篡改/过期/重复nonce/actionId、工具绑定/撤销/晚到回执、UNKNOWN→reconcile及终态不可覆盖。在真实四Besu节点部署，核对代码、链ID、共同区块进展、预约/审计交易receipt与状态；测试夹具回执明确标注为合约测试输入，不冒充真实邮件/删除副作用。
