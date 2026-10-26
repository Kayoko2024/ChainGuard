# 阶段7实施输入与验收计划

日期2026-10-26。仅最小Agent Runner/ToolExecutionProxy、固定trace和AgentDojo适配；用户明确本轮不做真实LLM实验，真实LLM接入是阶段7后续必做子任务、阶段8正式A/B/C前置条件。

输入：六份项目上下文、阶段0冻结21文件、B/C共享8文件、阶段6R2网关/工具/真实四Besu、原设计第12节。修改前实际pytest154通过、Hardhat71通过、链健康共同高度3953；日志results/phase7/baseline。Git无HEAD/全未跟踪，未add/commit；不存在旧Agent实现，agent/evaluation仅TODO。

拟修改：新增agent/src/chainguard_agent（类型、Runner、固定trace、Proxy持久日志和独立环境变量LLM配置/HTTP工具调用接口）、agent/tests/fixtures；新增phase7服务/受限读取broker、真实容器验收脚本和日志契约；独立evaluation/AgentDojo适配、commit/依赖锁及兼容性清单；更新pyproject测试发现、README和六份导航/进度。不得改原冻结协议、策略、合约或官方基准判定器。

强制边界：Agent容器只有自己的JWT/客户端证书和任务ID，不能持请求者/审批/relayer/工具凭据。Proxy只能提议/查询，高风险mail.send和doc.delete全部送阶段6propose；阶段6未支持的删除必须由网关拒绝，无本地回退。读取是独立显式的本地PUBLIC_DOCS只读capability，不给R2 TaskGrant偷偷增加权限，不生成伪预约。工具数据带untrusted来源，永不提升到system角色。

可信操作员在独立进程创建TaskGrant、核对预先批准的精确邮件参数、签请求者及不同组织审批、调用reserve。Agent不能调用该进程的签名接口。邮箱/读取文件均受限容器卷内合成资源，副作用由独立读取工具数据库和真实receipt核验。

先对Runner/Proxy/LLM配置模块写并运行测试，再执行固定trace真实容器链路；之后锁AgentDojo官方commit/许可证/原始文件摘要并尝试workspace邮件/文件任务。保留任务/攻击文本及官方判定器，参数映射单独实现；不兼容任务列明原因，不把官方模拟环境当真实企业或真实SMTP。真实模型接口仅实现配置和协议测试，本轮不调用外部模型。

日志分别保存agent_attempted_tool、policy_verdict、tool_executed、attack_success；固定trace attack_success=null、llm_sample_count=0，实际禁止副作用另记sandbox_attack_effect_observed。不从Agent自称“已发送”推断工具执行，不将网关受理或等待审批记为已执行。UNKNOWN只查原动作。完成前更新handoff/progress并保存命令、失败、交易/MIME及源码证据，等待用户验收。

本轮实际结果：官方Git连接重置，改锁官方PyPI0.1.35 wheel SHA-256及原112份文件，benchmark v1.2.2 workspace，无虚构commit；独立73依赖wheel哈希锁/pip check通过。最终175 pytest/71 Hardhat、读取6项、联合四场景4封真实邮件/8笔Besu交易和32份实时receipt/原卷只读复核通过。完整变更/失败/限制见phase7-acceptance.md。真实LLM攻防仍未完成，等待用户验收本轮范围。
