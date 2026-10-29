# 阶段4：本地四验证节点 Besu QBFT

部署输入/验收边界见[实施前记录](history.zip)。链与已有gateway分别使用`chainguard-chain`、`chainguard` Compose项目。RPC由4个独立Besu JVM提供；Hardhat只运行原有协议回归。

## 首次启动与复验

在仓库根目录Windows PowerShell执行。先完成阶段1bootstrap，使用已有Ubuntu WSL2 Docker，不重新安装系统软件。

```powershell
# 官方Docker Hub直连可用时可直接pull；本机WSL下载超时，采用下面的官方字节校验下载。
& .\.venv\Scripts\python.exe scripts/pull_besu_image.py
wsl.exe -d Ubuntu -u root -- docker load --input /mnt/d/CCF/.local/besu-download/besu.docker.tar
# 完整验收：原冻结检查、pytest、环境/镜像核验、幂等初始化、真实网络及交易/恢复测试、Hardhat。
& .\scripts\check_phase4.ps1 -UseWSL
```

源仓库固定`chain/image.lock.json`中的官方index、linux/amd64 manifest、config摘要，以及本机Docker29导入后的内容ID。下载器逐项校验manifest及blob的SHA-256；preflight额外核验导入后配置和各层diff ID，Compose使用已校验的内容ID且禁止自动pull。缓存位于忽略目录`.local/besu-download/`。适用已实测的Docker29.1.3/Compose2.40.3、Linux x86_64、Besu25.10.0/OpenJDK21；其它架构和旧Engine的导入ID行为尚未验收。

原生Docker与Linux也可直接使用`python scripts/chain.py <action>`；Windows/WSL使用`--wsl-distro Ubuntu`。PowerShell包装器默认健康检查，可分步执行：

```powershell
& .\scripts\chain.ps1 -UseWSL -Action preflight
& .\scripts\chain.ps1 -UseWSL -Action init
& .\scripts\chain.ps1 -UseWSL -Action up
& .\scripts\chain.ps1 -UseWSL -Action health
& .\scripts\chain.ps1 -UseWSL -Action status
& .\scripts\chain.ps1 -UseWSL -Action logs
# 结束演示：保留全部数据卷与身份；再次up沿用同一链。
& .\scripts\chain.ps1 -UseWSL -Action down
```

`init`在已有deployment时只校验，不生成新密钥、不重置余额。发现数据卷存在而部署清单丢失时拒绝初始化，必须恢复原`.local/phase4`资料；不得用新密钥覆盖已有链。初始化中断留下部分卷时同样停止，由操作员确认其内容并恢复。不要执行`docker volume prune`，不要删除原目录后盲目重新init。

本机WSL的systemd Docker服务本身不能维持发行版会话：最后一次WSL命令结束后，空闲退出曾同时关闭剩余3个验证节点。因此`up`维持一个隐藏的WSL运行会话，`down`在停链后关闭带专属标记的会话进程；不修改全局WSL、代理、防火墙或系统服务设置。手动关闭Windows/WSL会停止本地链，重新up使用原数据恢复。

## 配置、身份与端点

| 项目 | 值/用途 |
|---|---|
| chainId / networkId | 20261026 / 20261026；RPC chainId为0x13528a2 |
| 共识 | QBFT，4个初始验证者，提交需3个签章；epoch 30000 |
| 时间 | 目标出块2秒；request timeout初值4秒；这是配置，不是测量TPS |
| EVM/Gas | Berlin/London在0激活；zeroBaseFee，minGasPrice=0；gasLimit=30000000 |
| node1 | 容器172.30.44.11；宿主http://127.0.0.1:8545 |
| node2 | 容器172.30.44.12；宿主http://127.0.0.1:8546 |
| node3 | 容器172.30.44.13；宿主http://127.0.0.1:8547 |
| node4 | 容器172.30.44.14；宿主http://127.0.0.1:8548 |
| P2P | 容器30303，静态enode，关闭discovery；P2P端口不发布到宿主 |
| 数据 | 4个external Docker卷chainguard_chain_node1至node4；每卷独立节点密钥和数据库 |
| 私有客户端账户 | `.local/phase4/accounts.private.json`；只用于本地测试链，不能用于公链 |
| 公开部署资料 | `.local/phase4/network`及`results/phase4/deployment.json`、`genesis.json`；genesis不含私钥 |

测试sender与receiver首次初始化随机生成，sender在genesis获得10^24 wei；实际地址见deployment.json。validator由官方`besu operator generate-blockchain-config`生成，客户端账户不等于验证者或业务批准者。fresh init得到不同测试密钥/地址/genesis hash/交易哈希；算法、共识、链ID与验收条件可复现，不能承诺随机身份逐字相同。

每节点以UID1000、只读根、cap_drop=ALL及no-new-privileges运行；内存上限1536MiB，Java堆上限768MiB/direct256MiB。Besu/RocksDB/JNA要求临时目录允许加载原生库，因此仅容器tmpfs `/tmp`显式exec；不增加主机挂载或容器特权。链配置只读挂载不含私钥。账户私钥不传入命令行、RPC、不输出到证据、不提交Git。

## 健康与交易证据

Compose liveness仅确认HTTP进程存活。`chain.py health`进一步核验4个Besu版本、正确chainId/genesis、准确验证者集合、每个运行节点的enode身份、各3个peer、非syncing、共同高度的相同区块哈希。`acceptance`必须观测至少2个新共同已提交区块；不以HTTP200或广播成功作为链验收。

真实转账采用本地eth-account签名、eth_sendRawTransaction广播，链上不含工具原文。完整验收先提交错误chainId签名并验证被拒绝，验证eth_sendTransaction没有解锁账户，再广播正确交易。核对本地签名hash、4份相同成功receipt、所属区块交易列表、精确余额差和nonce+1；receipt.status=0x1、gasUsed=21000。`write_phase4_report.py`独立检查genesis RLP四验证者和交易区块至少3个65字节commit seal的结构，**未声称实现独立区块签章密码学验证器**。

验收还实际重启node4并重新查询相同receipt、停止node4观测剩余3节点继续提交，最后恢复4节点。完整原始证据在network-acceptance.json，单份receipt在transaction-receipt.json；summary.json只是从这些实际证据校验生成的索引。验收重跑保留上一份network-acceptance.previous.*.json；先前已经提交的测试交易不会被撤销。

## 边界与后续依赖

四容器在同一WSL宿主，信任本地Docker管理员；这不是四个独立组织的生产部署。RPC只绑定回环，关闭WS/GraphQL/ADMIN/PERSONAL，未实现RPC认证/mTLS、节点/账户准入治理。ETH/QBFT接口仍供可信本地操作员使用，不得暴露给Agent或不可信网络；host allowlist不是身份认证。静态peer不是对恶意Docker管理员的安全边界。

只有基础链和普通转账在本阶段完成。业务合约、组织/角色初始化、链上预约/finalize、可信网关链确认、工具端独立查链、工具ExecutionReceipt、Agent和React均为TODO。下一阶段使用实际chainId=20261026、此genesis和真正部署地址构造C组EIP-712域；冻结31337 golden vector、B组chainId=0域均不改写。本阶段转账receipt属于以太坊交易回执，不能作为已实现工具执行回执或FINALIZED状态的证明。
