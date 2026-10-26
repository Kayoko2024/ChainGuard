# DeepSeek 最小真实预检与阶段7前置

**最新状态2026-10-26：密钥已配置，真实预检05、C组真实前置02和正式模型A/B/C01均PASS。** 配置位置是 `D:\CCF\.env.local`，模板密钥为空；不再缺Key。完整命令、实际结果、官方基准兼容边界及小样本限制见 [live-experiments.md](live-experiments.md)。下文缺Key描述为保留的早期过程，不能作为当前阻塞。

用户于本轮指定DeepSeek、`deepseek-flash`、`https://api.deepseek.com`和OpenAI-compatible协议；不切换模型兜底。配置固定在`evaluation/deepseek_config.json`：temperature=0、top_p=1、thinking.type=disabled、max_tokens=256、parallel_tool_calls=false；provider不保证seed，明确null，保存实际provider model/usage/时间及配置摘要。不声称已验证模型名称或参数兼容性。

最初检查`D:\CCF\.env.local`不存在，当前进程`CHAINGUARD_LLM_API_KEY`未设置；用户两次说重新填写后仍未检测到。已创建无真实密钥的`D:\CCF\.env.local.example`；随后为避免路径混淆，**仅在缺失时独占创建`D:\CCF\.env.local`空密钥文件**并请求编辑器打开，不覆盖已有配置。请直接在这个确切文件中填写并保存，或在启动命令所在进程设置环境变量。不要把密钥发到聊天或填入可提交模板。`.env.local`由gitignore排除，模板允许跟踪；程序仅读取白名单字段的字面值，不执行shell/插值，不覆盖进程现有值，不记录密钥。

```powershell
& .\.venv\Scripts\python.exe scripts/check_deepseek.py
```

预检顺序：安全加载本地配置→检查密钥→真实GET /models→真实POST /chat/completions要求一次diagnostic_echo→校验实际模型返回的工具参数→本地执行无敏感副作用的echo→把真实结果回传模型。只有全部成功才PASS；HTTP错误保存脱敏状态/响应，网络错误明确FAIL，不伪造响应、不自动降级模型。provider若不支持指定名称/参数也如实失败。

请求使用固定HTTPS地址、禁用重定向、API Key仅在Authorization头；证据不包含该头，递归剔除密钥字串。只发送合成诊断文本，不发送TaskGrant明文、真实工具凭据、私钥或本地文档。该预检只验证实际模型诊断工具协议，不计入AgentDojo、正常邮件/注入攻防或ASR。

本轮实际预检deepseek-preflight-01/02/03均返回BLOCKED/LLM_API_KEY_MISSING（程序预期非零退出），api_called=false、tool_executed=false；原件preflight.json可查。配置/脱敏与协议单测22项通过；这些不是实际DeepSeek连通性成功证据。

后续仍必须：先在真实密钥配置后通过上述预检，再通过原Runner/Proxy/C网关运行正常任务与提示词注入，保存脱敏模型请求/响应、Agent尝试、策略结果、实际MIME/交易；然后扩展官方AgentDojo兼容任务并使用原判定器，统一模型/参数/数据/评价运行正式A/B/C。上述尚未完成，不能标记阶段7或阶段8完整通过。保留固定协议轨与独立统计，不将其替代真实模型结果。
