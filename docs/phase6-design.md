# 阶段6实施前记录

范围：只实现R2 mail.send首个完整C场景，复用实际四Besu及阶段5合约。不给R3/delete、Agent、React或评测扩展授权；不修改冻结协议和业务合约。

输入：六份上下文文档、阶段5合约与真实部署报告、spec/schema/API/EIP-712/状态机、冻结B/C策略、现有CentralStore与沙箱Store/LocalTestTools。修改前实际回归另存results/phase6/baseline；旧check_phase5脚本拒绝phase6输出目录，改用相同直接命令，不修改其边界。

计划：新增chain_crypto/chain_rpc/chain_store/chain_service/chain_api、独立工具chain_mail、TLS传输与服务入口；新增独立容器运行/测试脚本、配置和验收/交接。原A/B API与冻结8份共享策略输入不改；新增服务实现冻结/v1的R2子集，其余接口明确未实现。

网关持有仅本地链relayer及JWT/任务服务密钥；工具独占工具签名私钥，独立RPC和独立SQLite卷。Agent只能持有propose所需JWT，不接触relayer/审批/工具签名凭据。请求者和两个组织的审批私钥由可信测试签名器操作，不由Agent代签。工具API强制真实mTLS证书指纹+独立Bearer；原文/盐仅在受控内部通道及加密存储。

网关在广播前持久保存签名交易hash/raw/nonce；未知广播结果只查同一hash/动作，不新建预约或重发动作。工具自己重取成功reserve receipt、规范区块/事件/调用数据，核对预约/所有签名与当前角色、组织/scope/策略epoch、时钟/TaskGrant/原子配额、JCS加盐承诺，再在同一SQLite事务中消费actionId、投递本地MIME邮箱并保存真实工具签名回执/加密证据。完成结果幂等查询不需要重新执行或有效期延长。

UNKNOWN只读工具日志并找回原回执；不盲目dispatch。明确回执先持久排队，再finalize/reconcile；链不可用保留待提交。终态只由成功交易receipt、匹配事件和链状态确认；不把HTTP202/txhash当完成。

验收：每个模块自动测试并实际运行；真实服务和四Besu至少覆盖合法邮件、越权拒绝、相同action/nonce重放、承诺篡改、无预约/错证据/撤销/链失联拒绝、丢失或篡改回执后的UNKNOWN原记录恢复、audit广播/确认丢响应与重启补提交。导出真实交易receipt、区块、签名和MIME/邮箱计数，私钥/token/盐不进入公开报告。生产接口不添加故障开关，故障注入只在测试传输代理。

实施结果以phase6-acceptance.md及run-06为准。真实合法、越权、两类重放、承诺/无预约/服务身份、回执篡改、工具链失联、审计送达前后恢复均已验收；撤销/错证据分支沿用阶段5合约测试和冻结策略测试，本阶段没有单独注入工具执行前撤销竞态实验，不将计划清单冒充全部实测。草稿发现的SENDING无法补投和提前EXECUTING语义已按D020/D021修复；原规范不变。
