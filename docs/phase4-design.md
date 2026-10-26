# 阶段4实施边界（编码前记录）

输入：完整设计方案的四验证节点QBFT要求，阶段0冻结协议/向量，阶段1Docker/WSL与锁定依赖，阶段3冻结B/C策略。原21份协议与8份策略输入不修改。

新增文件计划：`chain/`下版本锁、QBFT genesis模板、节点配置及独立Compose；`scripts/chain.py`、PowerShell入口和阶段4验收脚本；配置/RPC校验的pytest；`docs/phase4-*`及`results/phase4/`真实公开运行证据。README增加运行说明。现有gateway Compose和默认健康API保持可用。

本阶段只部署基础链、测试账户和普通转账，不部署业务合约，不实现Agent、C组工具授权或冻结/v1业务API。

计划chainId=20261026（0x13528a2），QBFT四验证者、2秒目标出块间隔、epoch=30000、requesttimeout=4秒，London/零base fee与Paris兼容EVM。最终以实际genesis和RPC返回为准；31337的golden vector保持独立密码学fixture，不能替代实际链身份。

安全与持久化：官方Besu版本及镜像内容固定；四个独立JVM/数据卷/新生成节点私钥。测试账户随机生成，私钥只在忽略的`.local/`或Docker私有卷，任何证据只含公钥/地址。节点P2P不发布到宿主；RPC只发布到回环，限制API命名空间、无解锁账户。四容器同机为本地演示，不代表四家独立组织。停止脚本不删除持久卷或密钥。

验收：先运行配置/账户/交易证据校验单测及原冻结检查，再启动真实四Besu容器，验证chainId、clientVersion、genesis、4个预期validator、各节点3个peer和共同已提交区块。记录两次高度，广播真实本地签名测试转账，验证四节点相同receipt/block、nonce和精确余额变化；错误chainId签名和未解锁账户请求必须被拒绝。重启节点验证持久身份和追块；停止一个验证节点时检查余下3节点仍出块，再恢复4节点。实际命令、失败与修复、资源和公开证据写入验收记录。所有结果必须来自运行，不预填成功指标。

后续依赖：合约阶段使用此实际chainId/genesis/网络和独立部署账户；只有真实部署地址才能用于C组EIP-712域。未来链证据核验仍须由可信节点重新取receipt/block，本阶段转账receipt不是ExecutionReceipt。
