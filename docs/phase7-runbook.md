# 阶段7运行与恢复

前提：阶段1宿主Python/Node依赖、原四Besu和阶段5合约、原测试密钥与阶段3离线wheel缓存。Docker在Ubuntu WSL2；验收不会重置链、部署替代合约或删除原卷。

```powershell
Set-Location D:\CCF
& .\scripts\chain.ps1 -UseWSL -Action up
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe -m pytest -q
& npm.cmd test
# 新目录：创建四个受限服务/专用卷，真实邮件与链交易。
& .\.venv\Scripts\python.exe scripts/run_phase7.py --out results/phase7/my-run --fixture agent/fixtures/acceptance.json --stop-after
# 只读链RPC、原工具卷只读挂载；输出必须为新文件。
& .\.venv\Scripts\python.exe scripts/verify_phase7.py results/phase7/my-run --out results/phase7/my-verification.json
```

Agent/操作员在agent internal网络；工具在独立tools网络；只有网关同时连接两侧，网关和工具分别从节点1/3、2/4独立查原链。四容器均uid10001、只读根、drop ALL、no-new-privileges、专属Docker卷，无主机文件挂载/公开端口。Agent卷只有自身JWT、mTLS证书和私有Journal；没有审批、工具、JWT签发或relayer密钥。可信操作员与Agent使用不同证书和卷。

验收先在无网络临时容器运行ReadBroker六项测试，再跑normal/document-injection/mail-injection/agentdojo-goal-replay，最后重启Runner重放第一条trace、验证作用域和角色拒绝、DNS与工具/节点真实IP直连失败、导出实际MIME及四节点receipt。`agent_attempts.jsonl`、`policy_decisions.jsonl`、`tool_effects.jsonl`分别记录尝试、判断和效果。`report.json`、逐场景JSON及receipt/MIME原件保留。末尾状态失败的运行不能冒充整体通过。

`--stop-after`停止本轮四容器，保留卷供只读复核，原Besu继续运行。恢复验收用新目录；勿并行启动两套验收共享原relayer。JWT最多15分钟，证书2天，过期后新建测试运行。旧运行只读验收无需有效JWT。不要prune/down -v或清理历史失败卷。若只看历史证据，原工具容器可以停止，verify脚本会用无网络临时容器挂载其准确卷readonly并用SQLite mode=ro核验。

独立基准环境：

```powershell
# 本机Windows CPython3.14独立环境；--download从PyPI下载哈希锁依赖。
& .\.venv\Scripts\python.exe evaluation/setup_agentdojo.py --download
# 已有缓存时离线安装/核对。
& .\.venv\Scripts\python.exe evaluation/setup_agentdojo.py
& .\.local\phase7-agentdojo-venv\Scripts\python.exe evaluation/check_agentdojo.py --out results/phase7/my-agentdojo-check.json
# 可选导出独立新fixture；--export目标必须不存在，不覆盖已有验收输入。
# ... check_agentdojo.py --out results/phase7/new-check.json --export agent/fixtures/new-ad.json
```

`agentdojo.lock.json`固定官方PyPI0.1.35、wheel哈希、v1.2.2 workspace和112份原文件摘要，MIT许可证随归档保留。73依赖wheel的完整哈希锁仅针对Windows x86_64 CPython3.14；其他平台需要另生成并审查锁。网关/工具Linux依赖仍沿用原阶段3锁，不混装。原版加载器/判定器自检只操作官方内存环境，无真实SMTP/OS删除；不要把其正负控制当真实工具结果。

本轮无真实模型调用。后续模型进程通过环境变量读取`agent/.env.example`中的配置，Backend可替换，Proxy/原/v1网关保持一致。实际模型网络连通、工具schema/调用协议兼容、端到端正常任务与注入攻防以及原判定器整合都是阶段7后续必做；完成前不开展阶段8正式A/B/C统计。
