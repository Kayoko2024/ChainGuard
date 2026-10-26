# 阶段4验收记录

日期：2026-10-26（Asia/Shanghai）。状态：**真实四验证节点Besu QBFT验收通过，等待用户验收；不进入下一阶段。** 本阶段没有部署业务合约或Agent。

## 修改文件与实现

输入为原完整设计方案、阶段0的21份冻结协议文件、阶段1Docker/WSL环境、阶段3的8份B/C共用策略输入。编码前范围见phase4-design.md。原协议、golden vector、B/C策略和现有gateway Compose未修改。

| 文件 | 实现内容 |
|---|---|
| chain/compose.yaml | 四个独立Besu JVM、静态P2P网络、四个external持久卷、4个回环RPC、非root/只读根/资源限制/liveness |
| chain/genesis-template.json、node.toml | chainId=20261026、QBFT四验证者、2秒目标出块、Berlin/London、零base fee、静态节点/关闭discovery、受限RPC命名空间 |
| chain/image.lock.json | 官方Besu25.10.0的index/平台manifest/config摘要及本机Docker29实际导入ID；不是Hardhat镜像 |
| scripts/pull_besu_image.py、read_qbft_reference.py | 官方registry内容下载/逐项SHA-256校验、官方QBFT常量的只读核实；无镜像代理替换或下载代码执行 |
| scripts/chain.py、chain.ps1 | 镜像/环境核验、官方Besu生成genesis/验证者、私有测试账户、幂等初始化、部署/停止/日志/健康/交易和故障验收；维持并释放专属WSL会话 |
| scripts/check_phase4.ps1、check_phase4_lifecycle.py、write_phase4_report.py | 一键回归/真实RPC验收、完整down/up恢复测试、独立公开证据/私钥排除与源文件摘要核验 |
| tests/python/test_phase4_chain.py | 16项配置/官方内容摘要/真实密码学签名/receipt拒绝逻辑测试；单测fixture与真实链证据明确分开 |
| README.md、docs/phase4-*、results/phase4/* | 使用说明、阶段边界、原始运行证据、失败/修复记录及本验收报告 |

## 实际链与交易

| 项目 | 实测结果 |
|---|---|
| 客户端 | besu/v25.10.0/linux-x86_64/openjdk-java-21 |
| Docker / Compose | 29.1.3 / 2.40.3，Ubuntu24.04.1 WSL2；16 CPU，Docker可见约7.61GiB内存 |
| chainId | **20261026 / 0x13528a2** |
| Genesis block hash | `0xcb4778cbcf96b2891907209e06448c518e82f7fa633c376efe4621761e072173` |
| 四节点出块 | 共同已提交高度 **83 → 85**，共同高度的block hash一致 |
| 停止node4 | Docker确认node4不运行；剩余3节点各2个peer，继续提交 **90 → 92** |
| 节点恢复 | node4重启后原交易receipt不变；恢复4节点各3个peer，enode对应原验证者身份 |
| 完整停止/重建 | Compose down后0个项目容器、专属WSL会话已退出；up创建4个全新容器，身份/genesis/历史/原交易receipt保留，高度 **144 → 149** |
| RPC | http://127.0.0.1:8545、8546、8547、8548；P2P不发布宿主端口 |

四个真实验证者地址（node1至node4）：

1. `0x017055439600a355DfC7d2e1B263f320914c68a5`
2. `0x2105704a958DD2b1c022B1daAA56506F763D2028`
3. `0x34469F4f27e61bEd15416EbA9aFF871A39614953`
4. `0x70e24dc35E5894A6c3b0f6A1Ee45f5cbdafA7e3e`

验收转账hash：`0x143c04d176e0ef4c5031fb70405ec58e6513cb9dba54b4887d88da0b32bfabdf`。

以下为实际receipt的核心字段；完整原文在results/phase4/transaction-receipt.json，四节点独立查询及所属完整区块在network-acceptance.json：

```json
{
  "transactionHash": "0x143c04d176e0ef4c5031fb70405ec58e6513cb9dba54b4887d88da0b32bfabdf",
  "status": "0x1",
  "blockNumber": "0x57",
  "blockHash": "0x7cab778197b684383101edfe0a7336ceb1cfc9c400c847a81df084ccfb6b521d",
  "from": "0x291f1c15185451b0c0b77a5d2ddbf9a4836cb9ad",
  "to": "0xa41ff6d2de4d5a8a6910cbbf515e1408c29a385f",
  "gasUsed": "0x5208",
  "effectiveGasPrice": "0x0",
  "contractAddress": null
}
```

blockNumber=87，gasUsed=21000；此次value=10^15 wei、nonce=1。四份receipt逐字段一致，本地签名hash与RPC hash一致，区块交易列表包含该hash，四节点在该区块查询sender/receiver余额均精确减少/增加10^15 wei，sender nonce增加1。更早一次基础设施故障验收也提交过一笔真实转账，因此当前sender余额为999999998000000000000000 wei、receiver为2000000000000000 wei；没有回滚或重置来隐藏这次已发生的副作用。

status只表示以太坊转账执行成功；blockHash/number定位实际提交区块；from/to为测试账户；此交易不创建合约，contractAddress为null。它不是工具ExecutionReceipt，也不产生业务RESERVED/FINALIZED状态。

## 运行命令与测试结果

```powershell
# 第一次下载/加载；仅从官方registry获取固定版本并校验内容
& .\.venv\Scripts\python.exe scripts/pull_besu_image.py
wsl.exe -d Ubuntu -u root -- docker load --input /mnt/d/CCF/.local/besu-download/besu.docker.tar
# 完整阶段验收，包含原冻结检查、pytest、真实四节点/转账/停机恢复/完整down-up、Hardhat
& .\scripts\check_phase4.ps1 -UseWSL
# 本次在完整链验收后新增/实际单独执行了完整down-up验收
& .\.venv\Scripts\python.exe scripts/check_phase4_lifecycle.py --wsl-distro Ubuntu
# 独立校验所有原始证据和生成摘要
& .\.venv\Scripts\python.exe scripts/write_phase4_report.py
# 日常查询和停链；保留密钥与数据库
& .\scripts\chain.ps1 -UseWSL -Action health
& .\scripts\chain.ps1 -UseWSL -Action down
```

| 验收 | 结果 |
|---|---|
| 本阶段初始模块测试 | **16 passed**，unit-initial.xml |
| 最终宿主pytest（含原协议/网关/策略/阶段2参数回归及新增16项） | **144 passed，0失败/错误/跳过**，pytest.xml/pytest.txt |
| Hardhat原ABI/EIP-712/golden vector | **41 passing**，hardhat.txt；该本地EVM测试与Besu网络验收分别报告 |
| 原规范与B/C策略 | Schema/OpenAPI检查通过；共用8份策略检查通过；原21份冻结指纹由宿主回归校验 |
| 实际QBFT网络/RPC | **PASS**，4个不同容器/身份/数据卷、正确chainId和genesis、peer/验证者集合、共同区块增长 |
| RPC负例 | 错误chainId签名被真实RPC以-32000 Wrong chainId拒绝；未签名eth_sendTransaction以-32604不支持拒绝 |
| 实际转账/重启/一节点停机 | **PASS**，四节点相同receipt/余额/nonce、重启receipt不变、3/4节点仍提交、恢复4节点 |
| 完整Compose down/up与会话清理 | **PASS**，lifecycle.json；4个容器ID全部更新，私有卷/身份/交易历史保留 |
| 私钥与公开证据 | 2个账户及4个节点私钥只在忽略目录/私有卷；自动检查当前6个私钥未出现在本阶段源码/公开结果，Git忽略.local |

最终总计**185项Python/Hardhat回归通过**，另有真实网络、RPC及生命周期验收通过；不把重复运行同一套测试累加成样本量。没有运行Agent、业务合约实验或统计性能测试，没有编造TPS/攻击成功率。

## 失败、限制与后续依赖

原始失败和修复见results/phase4/failure-history.json，上一份失败网络验收保存在network-acceptance.previous.*.json，错误genesis和日志另有保留。主要问题是WSL无法直连Docker Hub、Docker29导入ID区别、初始化权限顺序、YAML tmpfs选项、tmpfs默认noexec、错误QBFT mixHash及WSL空闲关闭。均通过实际重跑修复；失败或被拒绝的操作未计为通过。WSL会话首次校验因额外shell展开失败，改用--exec并实际验证down关闭/up恢复。未修改全局代理、WSL或防火墙设置。

本机4容器共享一个宿主和管理员，不代表现实4家独立组织。RPC限定本机可信操作员，无生产RPC认证、mTLS、节点/账户准入治理；host allowlist不是认证。健康检查核对共同已提交高度，不宣称同一瞬间所有节点tip完全相同。Besu native临时库需要容器tmpfs允许exec；根文件系统仍只读且无额外权限。其它CPU架构和旧Docker导入方式未验收；系统关闭或WSL手动终止会停止本地链。

下一阶段依赖：本阶段实际chainId/genesis/4个RPC、保留的本地测试账户与固定Besu环境。业务合约部署和组织/角色配置仍TODO；C组必须使用实际部署地址构造EIP-712域，不能复用golden vector的31337 fixture域或B组chainId=0域。网关链确认、工具端独立查链、真实工具签名ExecutionReceipt和最终审计状态机均等待后续阶段实现。**本阶段结束等待用户验收。**
