# ChainGuard 只读审计控制台

React19.1.1/Vite6.3.6，独立package-lock。页面显示动作历史状态、跨组织审批/角色/签名、真实交易hash/区块、工具签名和当前审计核验结论。搜索和A/B/C过滤不改变原数据；未知副作用保持未知。

从项目根目录运行`python scripts/deploy_phase9.py`可完成真实协议证据生成、原工具卷/四节点复核、公开导出、锁定构建、受限Compose部署和实际HTTP/Edge冒烟。需要Windows/Ubuntu WSL2 Docker、原阶段4/5部署及本地受控测试签名材料；详见根README。无模型调用需求，不能把此协议演示记作LLM ASR。

单独构建：`npm.cmd --prefix dashboard ci --ignore-scripts --no-audit --no-fund`，然后`npm.cmd --prefix dashboard test`和`npm.cmd --prefix dashboard run build`。Vite dev仅用于静态开发；正式演示由独立FastAPI提供同源页面和只读API。

API见`docs/phase9-contracts.md`；没有签名或执行入口。容器uid10001、只读根、公开证据只读卷、回环端口；无工具私有卷/API Key。四节点同机、可信操作员、历史状态保留和生产限制均在报告中明确说明。Playwright使用已安装Microsoft Edge；无Edge时真实浏览器验收失败，不替换成静态结果。
