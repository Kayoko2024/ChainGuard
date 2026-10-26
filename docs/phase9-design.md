# 阶段9范围与编码前计划

输入：阶段0/3冻结协议、原三个合约/ABI、已有真实阶段8两轨证据、四Besu网络、既有只读验证器。本轮基线212pytest/71Hardhat；Git无HEAD、全仓库未跟踪，不能以空diff认定源码未变。

只新增独立审计展示层，不改变执行权。拟新增gateway审计投影/只读查链/HTTP模块；dashboard React及独立npm锁、Compose/Dockerfile；scripts部署、导出、冒烟、演示和干净重建；docs匿名设计/测试报告及交接导航。原业务/合约/冻结文件逐文件hash对比。

控制台只接收经原验证器复核的公开投影，不挂载工具私有卷、不读取API Key或签名私钥。按白名单导出动作状态/原意图及承诺/组织审批签名/工具回执/真实链证据与来源摘要。页面与API不提供签名、approve、reserve、execute、finalize或通用RPC代理。

验收：模块自动测试→原证据/原卷/真实四节点复核→React锁定构建→受限容器Compose启动→真实HTTP和浏览器交互冒烟→篡改/链失联/UNKNOWN明确展示→新源码目录、新venv/node_modules重建并执行测试→匿名报告和文件检查。历史文件与当前链结论分别标注；无链时明确UNAVAILABLE，不使用UI状态替代证据。干净重建复用已有本地链的边界须如实标明，不重置原链或删卷。
