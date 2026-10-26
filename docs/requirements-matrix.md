# ChainGuard MVP 需求与验收矩阵

阶段：0；协议：1.0.0；状态：**设计与接口已定义，业务模块全部 TODO**。

依据：《ChainGuard 智能体区块链 完整设计方案与实施计划》V1.0（2026-10-25）。原始文件 SHA-256：`A5016C9A302728D3B0BCCA50BA32992C1CF7AF5B04D26855DA49F6822EAAEA53`。原方案的日期计划和目标指标是参考输入，不是已完成工作或实测结果。阶段 0 只冻结需求、协议与测试夹具。

“SPECIFIED”表示已有本阶段规范；“TODO”表示尚无业务实现。测试通过不将 TODO 转为已实现。

| ID / 来源 | MVP 要求 | 规范 / 接口 | 本阶段证据 | 后续实现与验收（均 TODO） |
|---|---|---|---|---|
| MVP-01 §3、6 | 一个 Agent，仅提出三种已登记工具意图 | HTTP ProposeRequest、identifiers.json | Schema 拒绝未知工具及额外参数 | Agent：真实 tool calling；无敏感工具凭据 |
| MVP-02 §4、9 | 确定性 ABAC/RBAC；禁止模型提升权限 | permissions.md、TaskGrant | 权限判定验收表 | 网关与工具分别校验任务、资源、配额、时效 |
| MVP-03 §5、10 | 精确参数承诺；敏感原文不上链 | protocol.md、eip712.json | JCS/盐/Keccak 跨语言向量 | 网关与工具独立计算并拒绝调包 |
| MVP-04 §8 | 三合约职责清晰；真实状态预约 | 三个 Solidity interface | 接口编译；ABI 字段顺序检查 | Policy/Execution/AuditRegistry；无伪交易 |
| MVP-05 §5、8 | R2 至少业务+安全、不同组织批准 | permissions.md、ActionIntent | 真实 ECDSA 公开签名向量 | 合约角色/组织去重；同组织双签失败 |
| MVP-06 §7、8 | actionId 唯一；requester/nonce 一次性消费 | protocol.md、IExecutionRegistry | 整数边界及签名绑定测试 | 合约并发预约最多一次；nonce 不因过期而释放 |
| MVP-07 §9 | R2/R3 工具端不可绕过的二次核验 | ExecuteRequest、威胁模型 | API 内部 mTLS AND 服务身份声明 | 网络隔离、工具独立查链、非法调用无副作用 |
| MVP-08 §3 | 邮件只进入本地测试邮箱；删除只作用一次性沙箱 | 参数 Schema、permissions.md | 外部收件地址/路径穿越结构测试 | 容器出网限制与真实副作用计数 |
| MVP-09 §7、9 | 持久幂等、未知态、回执队列和对账 | state-machine.md、state-machines.json | 图完整性及禁止转换测试 | 数据库唯一约束、故障注入、重启恢复 |
| MVP-10 §8、10 | 工具独立签署结果；审计不可覆盖历史 | ExecutionReceipt、IAuditRegistry | Python/ethers/Solidity 验签 | 校验工具与工具ID绑定、回执冲突/晚到回执 |
| MVP-11 §6、14 | 四节点 Besu QBFT；确认交易后执行 | 威胁模型、链状态契约 | TODO：阶段0未部署链 | 真正四节点出块、交易查询、停一个节点测量 |
| MVP-12 §10 | 独立密钥、链下认证加密、日志脱敏 | 威胁模型、.gitignore | 向量只含公开地址和签名 | secrets 注入、AES-GCM、密钥轮换与泄漏扫描 |
| MVP-13 §8、10 | 至少两个独立组织治理；撤销与暂停 | IPolicyRegistry 只读接口 | TODO：治理写 ABI 与签名协议待单独评审 | 任一普通管理员不得独自添加批准者/解除暂停 |
| MVP-14 §11 | 统一 API、状态和错误码 | openapi.json、errors.json | OpenAPI 3.1 与 Schema 自动校验 | FastAPI 按契约实现；真实鉴权和状态一致性 |
| MVP-15 §12、13 | A/B/C 公平评测、固定来源和模型、真实 trace | requirements-matrix.md | TODO：未下载数据、未做实验 | B/C 同策略；UER/TCR/签名/故障数据自动导出 |
| MVP-16 §14、19 | 可复现启动、测试、报告与匿名交付 | README、依赖锁、阶段验收报告 | 阶段0本机实际测试 | Compose 全新环境重建；无手填实验指标 |
| MVP-17 用户要求 | React 前端延后 | 本表 | TODO：本阶段无前端 | 后续消费稳定 HTTP API 和 proof DTO |

阶段 0 交付边界：没有 FastAPI 服务、策略引擎、实际 Agent、业务合约、Besu、Docker Compose、邮件/删除实现、基准评测或 React 页面。`ProtocolHashHarness` 是有真实哈希与验签逻辑的测试合约，不能作为授权合约部署。全部 HTTP 地址仅为契约声明。

## 阶段 0 验收对应

| 交付模块 | 必须检查 |
|---|---|
| 需求与威胁 | 每项需求有来源、状态、后续责任模块及可观测证据 |
| 权限与状态 | R2/R3 禁止离线放行；R3 默认拒绝；UNKNOWN 不推断失败或重新执行 |
| 统一字段 | JSON / EIP-712 / Solidity 类型、顺序、整数精度一致 |
| HTTP 契约 | 每个 operation 有输入输出、权限与错误；内部工具同时要求两种认证 |
| 密码学 | 同一文件中完整公开向量，Python/ethers/Solidity 重算并验签；篡改测试失败 |
| 可复现性 | 锁定依赖；测试不依赖外部邮件、真实文件删除、在线模型或 Besu |

## 后续模块依赖顺序

1. 网关/策略：依赖 TaskGrant、权限表、规范化和错误码；不能把 Schema 校验当作授权。
2. 合约/链：依赖类型、签名域、角色/组织规则、时效和 nonce；实现前完成治理写协议与合约安全测试。
3. 沙箱工具：依赖已部署真实合约、独立链读取、持久幂等存储、作用域解析、独立工具签名密钥。
4. 审计/对账：依赖工具真实回执、链事件、加密证据、可信身份历史；必须支持 PARTIAL 和 UNKNOWN。
5. Agent/评测：依赖真实沙箱和网关；AgentDojo 版本、许可证和映射方案须先锁定。
6. 前端/比赛材料：依赖已实现 API 和实测数据；不提前填入通过率、吞吐或延迟。

下一阶段由用户指定；此依赖顺序不自动授权继续开发。
