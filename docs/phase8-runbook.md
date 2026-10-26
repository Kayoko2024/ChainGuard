# 阶段8复现

真实模型轨现已实现并通过首轮验收；一条命令 `& .\.venv\Scripts\python.exe scripts/run_phase8.py --track real_llm` 会先做API/C前置，再依次运行真实A/B/C及独立协议轨。完整说明见 [live-experiments.md](live-experiments.md)。下文仅对应原协议轨，末尾“real_llm拒绝/前置未完成”是历史状态，已由真实实现替代。

在D:\CCF的PowerShell，一条命令生成新结果目录，实际执行A/B/C、读取四节点真实receipt、以无网络readonly挂载原工具卷重新验证，再导出报告：

```powershell
& .\.venv\Scripts\python.exe scripts/run_phase8.py
```

依赖：Windows已有锁定Python虚拟环境、Ubuntu WSL2的Docker Engine、阶段3本地哈希核验wheel缓存、原阶段5部署与本地测试签名材料、原四Besu在线。脚本不下载新依赖，不重置链，不部署替代mock。链停机时使用`& .\scripts\chain.ps1 -UseWSL -Action up`恢复原卷。不能并发运行另一个共享资金relayer的验收。

默认采用固定计划3次场景重复/10次性能重复、单并发、10次每动作网关重放、1000次bootstrap。完整计划、固定seed和实际顺序进入manifest。需要特定路径时追加`--out results/phase8/一个未存在的目录`；已有目录拒绝覆盖。每次会有新的真实hash/MIME时间和性能值；“可重放”指相同输入、方法、可核查行为，不要求随机ID或时延相同。

只读复核（输出选择新文件，不广播交易、不再执行邮件）：

```powershell
& .\.venv\Scripts\python.exe scripts/verify_phase8.py results/phase8/run-04 --out results/phase8/recheck-01.json
& .\.venv\Scripts\python.exe -m pytest evaluation/tests -q
```

运行时会离线构建专用镜像和新建唯一Docker测试卷。非root uid10001、只读根、cap-drop ALL/no-new-privileges、无主机目录挂载/公共端口；只有可信实验harness接入原QBFT网，邮件落入新卷的本地SQLite，无SMTP外发。停止新容器但保留卷、加密状态和本地测试密钥，便于新会话复核；不要prune或删除原链卷。私钥仅经stdin进入私有卷，构建/公开证据不含密钥、salt或明文真实数据。

`execution.txt`保留逐案例实际状态。程序错误不丢弃样本：完整/部分trace与manifest FAIL保留，原始失败目录不可改写。某次失败后修复必须使用新目录。UNKNOWN可能有真实副作用，查看原邮箱/回执证据，不重发动作。

`--track real_llm`目前明确拒绝运行；阶段7真实模型与适用官方判定器前置未完成。不能用本命令的固定协议trace填写ASR、官方基准攻击率或真实模型任务成功率。用户已指定DeepSeek，安全配置及最小预检见[deepseek-runbook.md](deepseek-runbook.md)。必须先通过真实API/ToolCalling，再完成真实正常任务/注入与判定器适配，保持三组模型及输入一致后才能正式验收模型轨。
