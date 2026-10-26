# 阶段1工程与运行环境

范围：monorepo、依赖与测试框架、环境模板、Compose、最小健康检查。此文描述当前工程，阶段0文档保持历史原样；原协议和业务接口没有改变。

## 模块布局

- 根目录是一个Git仓库和npm workspace根；Python由pyproject.toml统一定义可编辑安装包和pytest配置。
- gateway/src/chainguard_gateway 是可安装Python包。main.py只有两个健康端点，config.py校验环境，integrity.py核对阶段0指纹，__main__.py按实际配置启动Uvicorn。
- contracts/package.json定义@chainguard/contracts，复用根Hardhat配置与锁定工具链；接口、测试合约和既有测试路径不移动。
- spec中的所有原有文件与contracts/interfaces都保持原字节；config/phase0-freeze.json记录21个原文件指纹。新运维端点使用独立自动生成的OpenAPI，不修改冻结的11个业务API。
- Agent、sandbox_tools、evaluation、dashboard仅有明确TODO说明。Compose没有这些服务，也没有未实现的Besu节点。

## 版本与兼容性

| 组件 | 固定/验证版本 | 锁定位置 |
|---|---|---|
| Windows开发Python | 3.14.4 | .python-version、config/toolchain.json |
| FastAPI / Starlette | 0.119.1 / 0.48.0 | gateway/requirements.txt、两类Python锁 |
| Pydantic / AnyIO / Uvicorn | 2.14.1 / 4.11.0 / 0.38.0 | 同上 |
| pytest / httpx | 8.4.2 / 0.28.1 | requirements-dev.lock |
| Node / npm | 22.23.1 / 10.9.8 | .node-version、package.json engines、toolchain.json |
| Hardhat / Solidity / OpenZeppelin | 2.26.3 / 0.8.28 / 5.4.0 | package-lock.json、hardhat.config.cjs |
| Docker Engine / Compose / Buildx | 29.1.3 / 2.40.3 / 0.30.1 | toolchain.json中的Ubuntu软件包精确版本 |
| Linux运行镜像Python | 3.14.4-slim-bookworm | Dockerfile与.env.example：ECR镜像+sha256 digest |

Python包声明支持3.11–3.14；本阶段实际验证3.14.4，其他版本尚未测试。运行时锁由测试环境实际依赖闭包生成，不带本地绝对路径；开发锁包含测试和构建依赖，项目本身另行editable安装。包安装仍需PyPI访问。Node使用22.x约束并记录实际精确版本；不升级阶段0的Hardhat、OpenZeppelin或Solidity。

首轮AnyIO4.15.1与Starlette测试端的BlockingPortal别名产生弃用提示，已明确固定AnyIO4.11.0并复验；不屏蔽该警告。pytest禁用可选缓存插件，避免本机历史缓存目录写权限干扰，真实测试结果仍写JUnit和日志。npm旧传递依赖的弃用提示保留；本阶段没有宣称完成依赖漏洞审计。

## 健康语义

| 地址 | 成功 | 失败语义 |
|---|---|---|
| GET /health/live | 200、status=alive、真实进程PID与monotonic uptime | 无响应代表进程/连接不可用；不查询业务依赖 |
| GET /health/ready | 200、status=ready；实际生命周期已启动且冻结文件指纹一致 | 文件丢失/变化或未启动返回503 not_ready；启动时校验失败直接终止启动 |
| GET /operations/openapi.json | 只有两个运维健康操作 | 不是业务OpenAPI；不暴露静态成功的业务路由 |
| /v1/* | 当前全部未实现，404 | 不能把API契约存在当业务功能可用 |

指纹检查用于发现意外漂移，不是抵抗攻击者同时修改代码和manifest的密码学信任根。readiness不检查或宣称Besu、任务授权、外部工具可用。

## 环境模板与凭据

.env.example只有COMPOSE_PROJECT_NAME和CHG_APP_ENV/HOST/PORT/LOG_LEVEL/SHUTDOWN_TIMEOUT/PYTHON_IMAGE。没有私钥、JWT密钥、邮件口令或API Key。未来真实密钥必须在相应实施阶段另定secrets注入边界，不能交给Agent。

bootstrap仅在.env不存在时复制模板。本地启动支持模板中简单KEY=VALUE、空行、整行注释；拒绝重复/未知键、引号和shell插值；进程环境变量优先。Compose通过--env-file显式读取项目.env。WSL命令默认Ubuntu/root，只用于管理Engine，没有提升普通用户组权限。bootstrap默认只检查Windows本机开发环境；WSL的Docker就绪结果以-UseWSL完整验收为准。

## 安装、启动与验收命令

在仓库根目录PowerShell运行：

```powershell
& .\scripts\bootstrap.ps1
& .\scripts\start_gateway.ps1
```

WSL Docker已安装时：

```powershell
& .\scripts\compose.ps1 -UseWSL -Action validate
& .\scripts\compose.ps1 -UseWSL -Action up
& .\scripts\compose.ps1 -UseWSL -Action status
& .\scripts\compose.ps1 -UseWSL -Action down
```

完整验收：`& .\scripts\check_phase1.ps1 -UseWSL`。仅本地检查省略-UseWSL；原生Docker完整验收用-RequireDocker。环境结果明确区分local_status和container_environment，缺少Docker不能报告容器启动成功。

smoke_gateway.py启动真实子进程并访问HTTP；Windows虚拟环境可能存在启动器/服务两个PID，按Uvicorn实际日志验证服务PID，清理自己创建的完整进程树并确认端口释放。Windows烟测清理使用taskkill，不将其称作优雅关闭测试。

smoke_compose.py拒绝替换已有项目容器，实际构建、up --wait、检查Docker健康状态和HTTP、读取容器内包版本、pip check，然后down。不会删除镜像或用户数据卷。容器只读、非root、无宿主目录挂载、drop ALL capabilities、禁止提权；gateway使用正常bridge网络且只在回环发布8000，允许出网。本阶段没有敏感工具或凭据；工具服务的独立内部网络在后续实施。构建过程需要外网下载依赖。

本机WSL从NTFS仓库直接传输BuildKit上下文时，对历史.pytest_cache读取扩展属性被拒，即使目录已被.dockerignore排除也会失败。Windows/WSL包装脚本因此使用build_gateway_image.py：只把冻结文件、网关Python源码、依赖锁和Dockerfile打成确定性tar，通过标准Docker stdin上下文真正构建镜像，再Compose up --no-build。它不读取或打包.env、密钥、.git、虚拟环境或缓存，也不修改目录ACL。字节可复现及敏感文件排除有自动测试。Linux原生Compose可直接使用普通build上下文。

.gitattributes禁止自动换行转换，确保Windows/Linux检出后的冻结文件字节指纹一致。

首次容器内健康检查虽通过，宿主HTTP未通过：Docker29在仅连接internal网络时没有实际发布配置的端口。已将gateway网络明确为普通bridge，仍只绑定127.0.0.1；验收同时检查真实宿主HTTP，不能只看Docker healthy。没有修改Windows/WSL全局网络设置。

## 镜像拉取网络处理

本机直接访问registry-1.docker.io超时。已从Docker Official Images公共ECR镜像分发入口拉取同版本，记录实际RepoDigest并固定：`sha256:fc74d22ffd0d5ac395a4b7bdda75a4539758862c49ebf3005647084631e63789`。不配置不可信镜像站，不禁用TLS，不修改系统代理或WSL网络模式。首次失败日志保留在results/phase1/compose-up.txt。

## 下一阶段依赖

真实业务实现仍需：身份/JWT与TaskGrant、确定性权限、完整治理写协议、真实业务合约、四节点QBFT、工具端独立核验与持久幂等、加密证据和回执对账。当前健康通过不满足这些业务安全验收。阶段1只提供后续模块的运行与测试基础。
