# Agent

阶段7已实现AgentRunner、ToolExecutionProxy、固定trace与独立LLM配置/HTTP工具调用接口。高风险调用只经原阶段6网关提议；批准、reserve及工具执行凭据由独立服务持有。工具观察保留untrusted来源和tool角色，Journal加密并持久去重。

联合验收：`python scripts/run_phase7.py --out results/phase7/new-run --fixture agent/fixtures/acceptance.json --stop-after`。只读复核：`python scripts/verify_phase7.py results/phase7/new-run --out results/phase7/new-verification.json`。宿主模块测试：`python -m pytest -q agent/tests`；真实工具/读取测试在受限容器运行。

模型配置模板在`.env.example`；`configured_backend('real_llm')`读取环境变量，替换Backend后沿用原Proxy与网关。当前只运行固定trace与本地HTTP协议fixture。**真实LLM攻防测试尚未完成**，必须作为阶段7后续子任务在阶段8正式A/B/C前完成。不能将trace的预设越权调用计为模型攻击率。

详见[字段与状态](../docs/phase7-contracts.md)、[复现](../docs/phase7-runbook.md)、[实际验收/限制](../docs/phase7-acceptance.md)。
