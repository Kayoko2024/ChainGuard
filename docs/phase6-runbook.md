# 阶段6 本地运行与恢复

前提：Windows现有`.venv`和Node依赖、Ubuntu WSL2 Docker、已初始化四Besu、阶段5原部署及忽略目录中的原测试身份仍在。脚本不重新部署合约、不重置链卷、不安装系统软件。镜像从固定Python3.14.4基础与既有哈希校验wheel缓存离线构建，沿用依赖锁，无新运行库。

```powershell
Set-Location D:\CCF
& .\scripts\chain.ps1 -UseWSL -Action up
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
# 必须用尚不存在的新目录；真实交易/本地合成邮件会写入新的专用卷。
& .\.venv\Scripts\python.exe scripts/run_phase6.py --out results/phase6/my-new-run
# 只读复核既有证据与四节点实时receipt，不广播新交易或POST工具执行。
& .\.venv\Scripts\python.exe scripts/verify_phase6.py results/phase6/my-new-run --tool-volume --out results/phase6/my-new-verification.json
```

`--tool-volume`额外以SQLite mode=ro打开原工具卷，重算MIME SHA-256、结果/证据承诺；只输出核验结论。省略时仍验证公开MIME/链/签名，但不声明实时检查了原邮箱数据库。验证输出文件必须是新的results/phase6文件。需要复核的测试容器必须仍存在；通过report的准确container ID核对，拒绝复用同名其他容器。

验收创建独立internal网络和gateway/tool/qa三卷，运行非root、只读根、cap-drop ALL、no-new-privileges，无宿主目录挂载、无发布端口。QA是可信测试签名器及故障代理，持独立审批测试密钥；它额外加入原链网络，只转发到真实Besu，完全不伪造RPC结果。实际Agent尚未实现，测试中agent身份只有propose权限；不要将QA签名器当作Agent进程。mTLS证书/服务令牌在各自私有卷，生成源在忽略`.local/phase6/<stamp>`；不打印/提交这些文件。

可通过`report.json`中的准确容器名重启同一服务，保留卷：

```powershell
# 名称从本次报告读取；不要重置/删除卷。
$lab = Get-Content -Raw results/phase6/my-new-run/report.json | ConvertFrom-Json
wsl.exe -d Ubuntu -u root -- docker restart $lab.containers.gateway
wsl.exe -d Ubuntu -u root -- docker restart $lab.containers.tool
# 停止只影响本轮三服务；可在完整验收命令添加--stop-after自动停止。
wsl.exe -d Ubuntu -u root -- docker stop --timeout 2 $lab.containers.gateway $lab.containers.tool $lab.containers.qa
```

默认保留服务供查看，`--stop-after`和失败仅停止本轮容器，保留卷/网络/证据及原Besu。不要docker prune/down -v。旧运行可以停止自身三服务释放资源；不能把多轮重跑累计成独立实验样本。新运行使用原relayer，不能同时启动两个验收进程。

本地测试JWT约15分钟、证书2天；过期后创建新运行以重发测试身份。重启不会重新签名审批、增加许可或改变原回执。若工具无原记录且网关UNKNOWN，保持未知，停止新执行；NOT_FOUND不是“未执行”的最终证明。审计补提交只来自原持久回执；原nonce/hash冲突需操作员核查，不能生成替代交易掩盖。

运行报告包含：5条核心场景、每条ActionRecord、工具公开签名/digest、交易hash与四节点完整receipt、测试故障事件、4份合成MIME及SHA-256、隔离/资源状态。实际数量须以对应运行报告为准；旧run-03只含3封邮件和7笔业务交易，不代表后来新增场景。失败运行的原日志和卷保留，不用成功摘要覆盖。
