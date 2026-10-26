# 阶段8输入、计划与验收边界

2026-10-26，Asia/Shanghai。输入为AGENTS及六份上下文、原设计§13两条实验轨道/指标定义、冻结21+8文件、原A/B中央服务/工具及阶段6 C服务/四Besu。Git无HEAD/全部未跟踪，空diff不能证明无变化。开始前运行本轮pytest/Hardhat/冻结检查并恢复原链，结果保存results/phase8/baseline。

拟增evaluation/plan.json、metrics.py、replay.py（受限容器真实服务/工具实验）、tests、运行与证据验证脚本、阶段8文档及进度/交接。只做实验/统计，不修改冻结协议/策略/合约，不进入React或其他业务工具开发。

两轨明确分开：protocol_replay只衡量预构造调用的真实工具/链效果；固定trace无模型，LLM样本=0、ASR未测。real_llm轨必须完成阶段7真实模型前置，且模型名称/API/密钥独立环境配置；当前未配置，已询问用户，不用fixture冒充模型。在未满足前置时，框架可生成protocol报告但不能宣称正式LLM A/B/C完成。

A/B/C共用case_id、任务文本、参数、Agent输入数据、账号角色/组织及冻结策略摘要。A原实现只账号检查、任务策略shadow；B/C强制同一任务ABAC与审批，不伪称三组强制门槛一样。域/动作ID/nonce按组独立生成，语义相同且不复用跨域签名。

验收：真实本地MIME/SQLite计数与签名/参数承诺；原B签名追加日志和独立checkpoint；C真实四节点receipt/区块成员/审计状态。新增伪造、重放、参数/审计篡改、工具执行前/后断响应及性能计时。所有敏感副作用限非root/只读根/无主机目录挂载的专属容器卷。测试签名器在可信实验harness，Agent调用适配器不接触私钥。服务层同进程集成测量明确不包含HTTP/mTLS传输，不把它当网络部署延迟或独立进程隔离证明。

输出traces.jsonl、cases.csv、aggregated_metrics.csv、run_manifest.json及原始证据。比率报告k/n和95% Wilson与scenario cluster bootstrap；UNKNOWN/超时保留、未知结果给界限而不判零；性能报告线性插值P50/P95/P99与固定工作负载trial bootstrap区间、均值/标准差/最大值和失败率。重复运行按场景聚类解释，不能宣称总体风险绝对零；无数据的指标为NOT_MEASURED/NOT_APPLICABLE。

最终协议轨run-04完整PASS，证据与真实指标见phase8-acceptance.md。用户后续指定DeepSeek/deepseek-flash并要求先API/ToolCalling；安全配置/预检已实现，当前两次预检均缺Key，模型前置仍未完成，不能改称正式模型A/B/C通过。
