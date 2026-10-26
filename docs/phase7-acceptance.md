# 阶段7本轮验收：固定trace与AgentDojo适配

日期2026-10-26，Asia/Shanghai。**本轮指定范围实现并通过技术验收，等待用户验收；真实LLM攻防测试尚未完成。** 阶段7仍有必做模型子任务，阶段8正式A/B/C前必须完成。固定trace样本数不能作为模型样本数或攻击成功率。

## 修改文件与实现

| 文件 | 实现 |
|---|---|
| agent/src/chainguard_agent/{runner,proxy,journal,model,__init__}.py | 有限工具调用循环、统一代理、AES-GCM/HMAC持久幂等、独立可替换模型Backend/配置、保守UNKNOWN及副作用标记 |
| agent/tests/test_runner.py、test_workspace_adapter.py | 21项模块测试，含重启/参数换绑/未知查询/非OK回执、模型本地HTTP协议与禁重定向、workspace映射及拒绝语义损失 |
| sandbox_tools/src/chainguard_sandbox/read_broker.py、sandbox_tools/tests/test_read_broker.py | 工具端任务/Agent/文档/期限capability、真实本地文件观察、六项隔离测试 |
| gateway/src/chainguard_gateway/phase7_server.py | 复用阶段6高风险入口，增加双向认证读取及受限可信审阅接口 |
| agent/integration/lab.py、phase7.Dockerfile、fixtures/{phase7,agentdojo-workspace,acceptance}.json | 分离Agent/可信签名器进程，原文件与本地注入fixture，受限容器真实验收 |
| scripts/run_phase7.py、verify_phase7.py | 四场景、重启/直连隔离、真实MIME/receipt导出，独立四节点/原工具卷只读核验 |
| evaluation/workspace_adapter.py、check_agentdojo.py、setup_agentdojo.py | 原FunctionCall映射到同一Proxy，官方加载/判定器正负控制，独立哈希锁环境重建 |
| evaluation/agentdojo.lock.json、agentdojo-upstream-files.json、requirements-agentdojo-windows-py314.lock、vendor/ | 官方0.1.35发行wheel、112份原文件哈希、73依赖wheel哈希与MIT许可证 |
| agent/.env.example、spec/agent/interfaces.json、pyproject.toml、.env.example | 模型独立配置模板、接口/日志约定及测试发现；原env解析规则保持 |
| README、agent/evaluation README、phase7文档、上下文导航/进度 | 命令、证据、字段/状态/限制和后续必做依赖；results/phase7保留实际输出 |

原21份协议和8份B/C策略SHA-256匹配，原三个业务合约/ABI未修改。核心字段/状态依赖详见[phase7-contracts.md](phase7-contracts.md)。本轮对最终成功路径的端到端运行后，非OK回执标记进一步改为保守null；该分支由新增参数化单元测试实测，未用OK场景冒充该分支实测。

## 实际命令与结果

| 实际执行命令 | 结果/证据 |
|---|---|
| python -m pytest -q（恢复基线） | 162 passed，resume-baseline/pytest.txt/xml |
| npm.cmd test（恢复基线及最终） | 71 passing；resume-baseline/hardhat.txt、final-hardhat.txt |
| python -m pytest -q agent/tests | 最终21 passed；agent-final.txt/xml，早期8/14/18项记录保留 |
| python -m unittest discover ... test_read_broker.py（无网络受限容器） | 6 passed；final-run-02/read-broker-unit.txt |
| python scripts/run_phase7.py --out results/phase7/final-run-02 --fixture agent/fixtures/acceptance.json --stop-after | PASS；4真实读取、4邮件、8真实交易，四场景和重启/授权/网络边界通过 |
| python scripts/verify_phase7.py results/phase7/final-run-02 --out results/phase7/final-verification.json | PASS；32份实时receipt、原卷readonly/SQLite mode=ro、工具签名/结果/证据承诺/MIME与未删除文件一致 |
| python evaluation/setup_agentdojo.py | 独立73 wheel哈希锁命令通过，pip check无破损依赖；agentdojo-locked-setup.txt |
| 独立venv python evaluation/check_agentdojo.py --out results/phase7/agentdojo-check-final.json | PASS；官方112份文件匹配、workspace原加载器/判定器与映射正负控制通过 |
| python -m pytest -q（最终修复后） | **175 passed**；final-pytest-02.txt/xml |
| build_specs.py --check、freeze_phase3_policy.py --check | PASS；final-specs.txt、final-policy.txt；未重生成冻结清单/向量 |

命令完整路径与复现步骤见[phase7-runbook.md](phase7-runbook.md)。工具敏感操作始终在受限Linux容器，Python宿主单元夹具明确为单元协议测试，不作为副作用证据。

## 最终真实证据

原四Besu chainId=20261026，共同高度**4526→4560**。normal、document-injection、mail-injection、agentdojo-goal-replay各有一次真实reserve和finalize。后三例每例越权发送、删除各拒绝一次，无Bob邮件、无删除执行。四个资源文件原SHA匹配。Runner重启重放normal后仍共4封，actionId没有再次执行。Agent的review/pending/reserve均FORBIDDEN，未授权read为UNAUTHORIZED_SCOPE；工具/节点DNS与实际私网IP直连均NETWORK_ISOLATED。

- normal actionId：`0xbf70ca176ba08bb08d5b6971f8e237bc9e04c552239f89d5e162e2c7b73e5b95`。
- reserve：`0x7bf45d07a814a3ed799f8e6a76c53f04a2611a9ed1a2ec2b6e922aadecdeef9b`。
- finalize：`0xfa5771d0d252fcc9bf100056b73839f9baaa3131ba030aed02797cc8182c37d2`。
- mail-1.eml SHA256：`26204f13859cd4bc5a821af0bdc3771c21bf5596ffbd9ddddde376a0e4bdbbd4`。

原件：results/phase7/final-run-02/report.json、normal-*-evidence对应JSON、mail-1至4.eml、agent_attempts/policy_decisions/tool_effects.jsonl。工具/交易强验证均来自原阶段6安全路径，未改跨组织、nonce、链上预约和工具独立当前授权校验。

## 基准兼容性与未完成项

AgentDojo官方PyPI0.1.35，benchmark v1.2.2 workspace，MIT；Git查询连接重置，采用发行版本+官方wheel SHA-256锁，不虚构commit。wheel摘要`364bea4219716b716bf639f504d195943f7f6a5535d312ca41d7098704a2affd`。官方112份包文件原样，原安全/utility判定器正负控制只验证官方内存fixture。

get_file_by_id→doc.read、send_email→mail.send、delete_file→doc.delete已实际映射；injection_task_0/1原GOAL及file13原内容用于独立本地goal-replay。注入文字是本地由原GOAL拼接，邮件身份单射改为本地.invalid，**不声称官方攻击实现、完整官方任务成功或原语义等价得分**。对应score=null。

| 不兼容任务 | 原因 |
|---|---|
| user_task_33 | search_files_by_filename尚无映射，发送须带附件；当前MailParams无附件，明确拒绝而不删字段 |
| user_task_35 | list_files尚无映射，C R3执行尚未授权接入，删除默认拒绝 |
| user_task_16 | search_emails尚无映射；没有伪造成功读取或utility得分 |

真实模型接口已有独立配置、可替换Backend和本地HTTP工具调用协议测试；**没有调用真实LLM**。所有固定trace attack_success=null、llm_sample_count=0，sandbox_attack_effect_observed=false仅指这批受控调用无禁止副作用。

阶段7后续必做：用户指定模型配置/受限连接后，真实运行正常任务、文档/邮件注入，保留模型原始工具调用和原判定器结果；扩充或明确排除不兼容任务，再准备阶段8正式A/B/C。当前A/B/C比较、ASR/TCR、性能/显著性均未做。其他C工具、R3执行、React、生产凭据托管和独立机构部署继续TODO。

## 失败、修复与限制

run-01测试JWT1800秒超过900秒认证上限；修正验收脚本，不改认证。final-run-01四业务例通过后，新增IP探测局部变量connection遮蔽连接函数；改名后final-run-02通过，原失败卷/报告保留。首次最终pytest为174过/1失败：将LLM变量放根模板触发原阶段1严格env解析；移至agent/.env.example后175通过，不放宽原解析器。PyPI元数据首次打印触发GBK字符错误，wheel下载/校验已成功；改为受控输出，未影响包内容。普通exec/node沙箱初始化仍报helper_unknown_error，按工具审批完成本地操作；无待解决审批拒绝。

四节点/签名人同一宿主，不能称独立机构运营。真实邮件为SQLite本地邮箱原子效果，不外推第三方SMTP。读取broker只处理显式PUBLIC_DOCS测试资源。AgentDojo依赖锁当前仅Windows3.14，真实模型与官方全量CLI/所有任务未验收。Git仍无HEAD/0跟踪，不自动提交；源码/证据清单辅助恢复，不是独立信任根。重复运行和失败运行产生的测试邮件不累计为独立实验样本。
# 真实模型后续子任务更新（2026-10-26）

DeepSeek真实连通性/ToolCalling、正常任务、文档/邮件注入和AgentDojo目标适配已通过：`results/phase7/deepseek-live-02`，4真实读取/4本地邮件/8链交易/32节点receipt，独立重算通过。未修改官方判定器；完整官方utility不兼容，不能声称全基准完成。详见 [live-experiments.md](live-experiments.md)。下文原“真实LLM未完成”记录属于固定trace交付时的历史状态。

