# ChainGuard 匿名设计报告

版本：阶段9竞赛原型；日期：2026-10-26。作者、机构、联系方式及设备身份不在本报告中提供。

## 研究问题与范围

Agent读取文档或邮件中的恶意指令后，可能尝试调用超出用户任务授权的敏感工具。ChainGuard将模型推理与执行权限分离，把高风险动作绑定到具体任务、工具、资源作用域、完整参数承诺和短时许可；多组织审批、一次性链上预约、工具端独立核验共同约束真实副作用。

原型使用Python/FastAPI、Solidity/Hardhat/OpenZeppelin、四验证节点Hyperledger Besu QBFT、Docker Compose、pytest和React。已经贯通的C组业务场景仅为R2 mail.send。邮件写入隔离容器的本地SQLite MIME邮箱，不访问外部邮件系统；删除只限测试文件，C组R3删除业务仍未集成。四节点在同一宿主机，不代表四机构独立运营。

## 威胁模型与信任边界

攻击者可以修改Agent读取的外部文本，诱导越权工具参数，提交伪造或重放签名，修改审计导出副本，制造网络或回执故障。攻击者不能同时获取所有受信审批密钥、替换独立审计检查点，或控制联盟链共识多数。

模型不持有请求者、组织审批者、工具签名人或relayer私钥。网关授权不会代替工具端再次检查；链上预约也不代表邮件已经发送。UNKNOWN不解释为未执行，不能盲目重发。单组织完全互信环境下，可信数据库与签名追加日志可能已足够；原型不主张所有中心化方案都不安全。

## 冻结协议和真实执行路径

ActionIntent的schema版本、actionId、taskId、requester、agent、toolId、resourceScope、paramsCommit、risk、policyId、policyEpoch、nonce、issuedAt、expiresAt均进入同一EIP-712签名结构。uint64/uint256在JSON中使用十进制字符串，结构、字段顺序及域不因控制台变化。完整参数经RFC8785规范化，并使用独立随机盐和域分离keccak256承诺；正文和盐不上链。

请求者与批准者签署同一意图。R2业务审批与安全审批需不同地址和组织；当前角色、资源范围、策略版本及时效都必须有效。ExecutionRegistry消费actionId与nonce并产生真实reserve交易。工具从独立节点读取预约、当前权限和参数承诺，持久幂等地执行一次本地副作用，并用工具私钥签署ExecutionReceipt。

ExecutionReceipt绑定schemaVersion、actionId、paramsCommit、resultCommit、evidenceIndexCommit、executedAt和outcome。AuditRegistry验签并finalize；UNKNOWN只能在原证据恢复后reconcile。回执丢失时查询原执行日志，审计待提交保留原交易字节/hash，不以新动作重发邮件。普通转账回执和合约夹具不作为工具业务回执。

## 最小审计控制台

独立React应用由独立FastAPI只读服务提供。部署前，原验证器实际检查四节点回执、签名、承诺及原工具卷；投影器按白名单导出动作状态、意图/回执承诺、原批准签名、交易hash、区块信息和来源摘要。浏览器不获得正文、参数盐、工具数据库、私钥或模型Key。

历史业务状态、当前链状态、历史物理副作用观测和本次审计结论分别展示。实时核验读取四节点共同高度和合约代码，核对reserve calldata、同意图签名、预约时组织与角色、nonce、AuditRegistry receiptHash/receiptSigner、工具签名和finalize/reconcile交易。组织当前撤销状态另列，不用当前角色覆盖历史授权事实。

无预约记录显示NO_RESERVATION；有预约但无回执显示PENDING_RECEIPT；节点失联或缺少历史权限状态显示UNAVAILABLE；证据篡改显示INVALID。A/B中央记录标记HISTORICAL_ONLY，不伪造链上状态。页面颜色、动画或截图都不是执行证明。

只读API没有approve、reserve、execute、finalize或通用RPC转发。容器非root、只读根、cap-drop ALL、no-new-privileges，唯一挂载是只读公开证据卷，端口只绑定本机回环；采用同源资源和内容安全策略。该界面仅面向本机可信评审者；尚无生产级多用户认证、机构隔离或对恶意运营方的独立取证服务。

公开catalog与摘要由本地操作员选择，因此摘要只能发现意外变更，不能抵抗同时替换文件和摘要的管理员。C组签名和链锚定可以重新独立核验；链承诺不能自动恢复原文，也不能证明工具签名人一定如实描述现实。物理副作用仍依赖受信工具及原卷取证。

## 实验和可复现性

A组常规账号权限并记录任务策略shadow；B组强制任务ABAC/RBAC、独立审批和签名追加日志；C组在相同冻结B业务策略上增加链预约、独立查链和链回执。三组输入配对，机制不适用项单列，不通过削弱B制造收益。

真实DeepSeek实验与确定性协议回放分目录统计。真实模型固定deepseek-flash、temperature=0、top_p=1、thinking disabled、parallel tool calls=false；模型未提出越权调用不等于网关阻断。AgentDojo使用锁定原版判定器的明确目标适配；完整官方utility不兼容，不声称完整排行榜成绩。原实验只有少量任务，ASR为0仍报告非零置信区间上界。

部署、HTTP/浏览器冒烟、负向审计、网络失联、演示、源码与依赖重建均提供脚本。新环境重建复用已声明的OS/WSL/Docker/原链、公开证据卷和经哈希核验的wheel缓存；不把新venv或无缓存镜像构建称为空白机器/新创世链验收。

## 已知工程限制

旧区块回执可读，但旧权限状态eth_call可能返回真实RPC错误，使完整历史授权核验不可用。原QBFT读取还曾返回null导致原客户端TypeError。本阶段不修改核心源码：独立演示传输适配器只把缺失验证者结果转为CHAIN_UNAVAILABLE，由已有有限查询流程处理；绝不合成节点数据或执行成功。原未适配入口的间歇异常仍为已知未修复项。

本地数据库的一次性提交不能外推第三方SMTP的exactly-once保证。单worker/专属relayer、生产RPC认证、机构独立密钥托管、全官方基准与更大实验样本仍待后续工作。本报告仅说明实际原型与明确边界，不给出未测实验指标。

## 公开参考

- Hyperledger Besu QBFT文档：https://besu.hyperledger.org/private-networks/how-to/configure/consensus/qbft
- EIP-712：https://eips.ethereum.org/EIPS/eip-712
- OpenZeppelin Contracts：https://docs.openzeppelin.com/contracts/5.x/
- AgentDojo：https://github.com/ethz-spylab/agentdojo
