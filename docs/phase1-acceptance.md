# 阶段1验收记录

范围：monorepo、依赖兼容性、启动配置、最小健康检查。冻结的业务字段/签名/状态/API保持原样；业务合约和Agent未开始。

日期：2026-10-25（Asia/Shanghai）。状态：**完整阶段1验收通过，等待用户验收；不进入下一阶段。** 机器证据为results/phase1/summary.json，acceptance=FULL_PHASE1_PASS。

## 输入与修改清单

输入：阶段0设计与21份冻结文件、现有协议测试和Hardhat工具链、用户阶段1范围；另获用户明确授权在现有Ubuntu WSL2安装Docker Engine与Compose。

| 新增/修改 | 实现内容 |
|---|---|
| .git/、.gitattributes、.gitignore | 初始化单仓库、保留字节级换行、排除私钥/环境/构建缓存 |
| package.json、package-lock.json、contracts/package.json | npm workspace接入；原Hardhat/OZ/solc版本与源文件路径保持不变 |
| pyproject.toml、.python-version、.node-version、requirements-dev.* | Python包、pytest、版本约束和完整开发依赖锁 |
| gateway/src/chainguard_gateway/{__init__,__main__,config,integrity,main}.py | 实际FastAPI进程、校验配置、生命周期和协议指纹健康检查 |
| gateway/requirements.txt、gateway/requirements.lock | 精确运行时依赖及实际依赖闭包 |
| gateway/tests/test_health.py、tests/environment/test_scaffold.py | 健康/失效/配置/锁定/workspace/构建上下文测试 |
| .env.example、.dockerignore、gateway/Dockerfile、compose.yaml | 无凭据模板、固定镜像digest、隔离gateway容器与健康探针 |
| config/{phase0-freeze,toolchain}.json | 21个原文件指纹、实测工具链与Ubuntu软件包版本 |
| scripts/bootstrap.ps1、start_gateway.ps1、run_gateway.py、local_env.py | 安装锁定依赖、前台启动、安全解析本地模板 |
| scripts/compose.ps1、build_gateway_image.py、smoke_compose.py | Compose操作、可复现白名单tar构建、真实容器启动/健康/清理 |
| scripts/check_environment.py、check_phase1.ps1、smoke_gateway.py、lock_runtime.py、write_phase1_report.py | 环境检查、完整回归、真实HTTP启动、依赖闭包、机器结果和源文件指纹 |
| agent/、sandbox_tools/、evaluation/、dashboard/README.md | 仅明确TODO的模块边界，没有空业务函数 |
| README.md、docs/phase1-environment.md、本文件 | 当前阶段操作说明、兼容性、失败修复和验收 |
| results/phase1/* | 实际日志、JUnit、环境/启动结果与SHA-256清单 |

## 运行命令

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\check_phase1.ps1 -UseWSL
& .\scripts\compose.ps1 -UseWSL -Action up
& .\scripts\compose.ps1 -UseWSL -Action down
```

完整验收脚本包含Schema生成漂移检查、pytest、Hardhat、真实本地HTTP进程启动/停止、Docker/Compose环境检查及真实容器启动/停止。单独运行本地服务：`& .\scripts\start_gateway.ps1`。

## 已实际发现并处理的问题

1. Windows虚拟环境启动器PID与Uvicorn服务PID不同；首次启动烟测断言失败。已改为校验真实服务日志PID和健康响应PID，清理自己启动的整个进程树，并确认端口释放；失败日志保留。
2. Starlette0.48与AnyIO4.15.1测试API产生弃用提示，已固定AnyIO4.11.0复验；pytest可选缓存因本机权限警告而禁用，不屏蔽测试失败。
3. Docker Hub元数据请求超时；同版本官方公共ECR镜像已成功下载并固定实际digest，保留TLS校验。
4. WSL/NTFS目录扩展属性读取被拒导致BuildKit失败；改用确定性白名单tar上下文，不读取缓存、凭据或修改目录ACL。该构建路径有内容排除和可复现性测试。
5. 本地沙箱执行器多次在进程创建前返回setup refresh错误；获准在沙箱外运行相同项目命令进行实际验收，未据此把未运行的测试记为通过。
6. Docker29在仅连接internal网络时没有实际发布端口，导致容器healthy而宿主HTTP失败。gateway现使用正常bridge，仍仅在127.0.0.1发布端口；后续敏感工具单独隔离，当前没有工具凭据。未更改全局网络配置。

## 依赖、启动结果与边界

| 实际检查 | 最终结果 |
|---|---|
| 阶段0冻结文件/生成规范 | 21份原文件SHA-256全部一致；Schema/OpenAPI生成检查通过 |
| pytest | **57 passed；0失败、0错误、0跳过**。含原33项协议测试、13项健康测试、11项工程/上下文测试 |
| Hardhat workspace | **41 passing**；原Solidity接口、哈希与签名向量回归通过 |
| bootstrap | 锁定Python依赖、editable包与npm ci实际完成；Git已初始化、未自动提交 |
| Python本机依赖 | pip check通过；Python3.14.4、FastAPI0.119.1、Starlette0.48.0、AnyIO4.11.0、Pydantic2.14.1、Uvicorn0.38.0 |
| Node工具链 | Node22.23.1、npm10.9.8；Hardhat2.26.3、Solidity0.8.28、OpenZeppelin5.4.0兼容实测通过 |
| WSL运行环境 | Ubuntu24.04；Docker29.1.3、Compose2.40.3、Buildx0.30.1，Compose配置校验退出码0 |
| 真实本地Uvicorn | live/ready均200、真实服务PID一致；业务/v1/tasks返回404；自己的进程树已停止、端口释放 |
| 真实Compose网关 | 31个白名单文件构建真实镜像，Docker healthy；Windows回环访问WSL发布端口的live/ready均200，业务路由404 |
| Linux容器内依赖 | 实际Python/五个核心包版本与本机一致；pip check为No broken requirements found |
| 清理 | Compose down退出码0；最终ps无项目容器；不删除镜像或数据卷 |
| Git忽略/换行 | .env、.local、node_modules、.venv确实被忽略；冻结JSON的text属性unset，保留字节指纹 |

实际版本与原始响应在results/phase1/environment.json、startup-local.json、startup-compose.json、summary.json；JUnit、Hardhat日志、构建日志和源文件清单均保留SHA-256。首次失败记录也保留，最终通过没有覆盖其问题说明。

Windows本地烟测使用taskkill停止自己创建的进程树，因此启动器退出码1是该清理方式的结果，不是应用启动失败；不据此宣称已验证Windows优雅关闭。容器由Compose正常停止并移除测试网络。

## 已知限制

- 本机直接Docker Hub访问仍超时，当前使用已验证的官方公共ECR入口和固定digest；首次安装/构建需要镜像仓库和PyPI网络访问，不是完整离线发行包。
- npm旧传递依赖仍输出弃用提示；依赖兼容与测试通过不代表已完成漏洞审计。
- Windows完整开发测试与Linux运行镜像已验证；其他Python版本、其他OS的完整开发测试没有宣称通过。
- WSL/NTFS构建使用项目提供的tar上下文包装脚本；不支持把已知失败的原始WSL目录构建命令冒充为通过。原生Linux Compose使用普通上下文。
- gateway当前使用允许出网的bridge，发布端口仍仅回环；本阶段无敏感工具或凭据，工具隔离和强制授权属于后续业务实施。

业务/v1路径当前返回404；ready只证明进程生命周期和冻结文件一致，不证明授权、区块链或工具可用。没有业务交易、伪回执、邮件发送、删除操作、Agent或性能指标。

后续依赖：真实身份/TaskGrant、确定性权限、治理写签名协议、业务合约与四节点QBFT、沙箱工具端强制授权和幂等回执；具体下一阶段由用户指定。
