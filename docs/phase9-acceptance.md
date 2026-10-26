# 阶段9验收记录

2026-10-26。只读控制台、部署/冒烟/演示、匿名设计/测试报告和受控干净重建技术验收通过，等待用户验收。没有进入其他业务范围；空白OS完整重建和生产部署仍未验收。

## 修改文件与实现

| 文件组 | 内容与边界 |
|---|---|
| `gateway/src/chainguard_gateway/audit_projection.py` | 白名单公开投影，不含完整参数、盐、MIME正文或凭据 |
| `audit_verify.py`、`audit_console.py` | 独立只读API/四节点核验；原审批区块角色/组织、签名、calldata、事件、nonce、工具回执/当前状态；无执行入口 |
| `gateway/tests/test_audit_console.py` | 隐私字段、目录摘要、host/CSP、只读路由、断链与不一致测试 |
| `spec/audit/openapi.json`、`docs/phase9-contracts.md` | 从真实服务导出的7条GET接口，独立于原冻结业务契约 |
| `dashboard/` | React界面、独立npm锁、Dockerfile/Compose、格式测试与真实Edge冒烟 |
| `scripts/export_audit.py`、`smoke_audit.py`、`deploy_phase9.py` | 原验证器/原工具卷复核后导出；真实协议→构建→受限容器→HTTP/浏览器一键启动 |
| `scripts/check_phase9_observer.py`、`demo_phase9.py` | 实际链证据篡改检测、审计容器断网恢复、只读演示及新真实运行入口 |
| `scripts/rebuild_phase9.py` | 新源码/venv/node_modules、锁定安装、无缓存镜像、独立8081验收 |
| `evaluation/audit_demo.py`、`scripts/run_phase9_protocol.py`、`evaluation/tests/test_audit_demo.py` | 仅演示测试进程将缺失的真实validator读取视为CHAIN_UNAVAILABLE，原成功值不变；不修改原核心逻辑 |
| `scripts/check_phase9_integrity.py` | 原116份源码及21+8冻结条目（25个不同文件）比较，不重生成锁 |
| `scripts/build_phase9_reports.py`、`docs/reports/`、`output/pdf/` | 匿名Markdown及可复现PDF生成、空作者/文字检查、3+4页报告 |
| `docs/phase9-design.md`、`phase9-contracts.md`、`demo-phase9.md`及导航/交接 | 范围、接口、演示、实际验收、限制与下一步依赖 |

原ActionIntent/ExecutionReceipt、两个EIP-712域/golden vector、状态机、三业务合约、冻结策略、核心Agent/网关/工具执行逻辑和原依赖锁均未改。`integrity-final.json`相对阶段8实际manifest检查116份原源码和25个不同冻结文件，changed=[]；新只读层不产生任何执行权。

## 实际命令与结果

```powershell
& .\.venv\Scripts\python.exe -m pytest -q --junitxml=results/phase9/final-checks/pytest.xml
npm.cmd test
& .\.venv\Scripts\python.exe scripts/build_specs.py --check
& .\.venv\Scripts\python.exe scripts/freeze_phase3_policy.py --check
& .\.venv\Scripts\python.exe scripts/deploy_phase9.py --out results/phase9/deploy-final --port 8080
& .\.venv\Scripts\python.exe scripts/check_phase9_observer.py --deployment results/phase9/deploy-final --out results/phase9/observer-final.json
& .\.venv\Scripts\python.exe scripts/demo_phase9.py --out results/phase9/demo-final
& .\.venv\Scripts\python.exe scripts/rebuild_phase9.py --deployment results/phase9/deploy-final --out results/phase9/clean-final
& .\.venv\Scripts\python.exe scripts/check_phase9_integrity.py --out results/phase9/integrity-final.json
```

上述固定`--out`均已使用；再次运行要用新目录/文件或省略可选out。现有8080运行时，第二次部署用空闲回环端口`--port 8083`，或先用原部署的compose.env明确停止该审计实例；不要停止/重置Besu或删除卷。

- 最终全量231pytest通过（8.98s），71Hardhat通过（13s）；冻结生成/共享策略check通过。日志在final-checks。
- 阶段9新增19pytest（audit-unit-04.xml），前端3tests通过。真实Edge无拦截/替身网络，合法两组织核验/UNKNOWN/搜索/分组/移动视口/0JS错误通过。
- deploy-final退出0/PASS，`http://127.0.0.1:8080`，138条公开投影；HTTP证明和browser.json分别保存。非root/只读根/公开卷只读、回环端口，容器不持API Key或签名私钥。
- observer-final PASS：意图、审批、回执、区块和actionId五类证据副本篡改均INVALID；只断开审计容器网络后返回UNAVAILABLE，恢复后VERIFIED；没有写链或工具执行。
- clean-final退出0/PASS，17步全部0：新源码/venv/root及前端node_modules、pip check、231pytest/71Hardhat/3前端tests、无缓存镜像、公开卷预检、8081真实HTTP/Edge通过。原卷/OS/链复用边界如下；clean-02同样通过，不当额外独立实验样本。
- PDF由bundled ReportLab4.4.9/pypdf6.10.0及本机simhei字体生成；3页设计、4页测试，空Author，Poppler全部7页渲染人工检查无裁切/重叠。脚本运行需报告依赖，不把它加入网关运行时。

## 真实交易与副作用

本轮最终源`results/phase8/phase9/b5b09af5ea`，manifest/verification均PASS。四Besu chainId20261026共同高度22651→22722，138案例、93本地MIME、59笔真实交易、236份实时节点receipt；原卷readonly/SQLite mode=ro、原签名/承诺/calldata/事件/nonce/状态及CSV统计重算通过。原始逐case JSON、traces.jsonl、cases.csv、aggregated_metrics.csv、tx-receipts.json完整保存，不能只凭网页状态或下列hash声称执行。

正常C动作`protocol-0000`：reserve `0xb50108147ae9660bf863059f4dc17c5d1450275b40b9421d23e012dd3837a00b`，block22656；finalize `0x3ea909c6740b973b7e253d58c731722bc5c6cb4f09fffa614d303ba306c0aea5`，block22657。两组织同意图批准和真实工具签名通过，HTTP共同高度22760核验每笔4节点receipt。UNKNOWN`protocol-0006`缺回执且链仍RESERVED，PENDING_RECEIPT；越权`protocol-0043`无预约，NO_RESERVATION。A/B只HISTORICAL_ONLY，不伪造链拒绝交易。

本轮是确定性协议轨，ASR未测；阶段8真实DeepSeek三组正式轨单列且保持原判定器。模型各ASR0/3、95%上界56.15%，无越权调用，不算网关阻断。协议共同UER A6/9、B/C0/9；UBR A3/9、B/C9/9。完整区间/性能/故障结果见匿名测试报告与原CSV，不池化历史重复。

## 失败、已知问题及未完成项

1. deploy-01/02真实协议FAIL：RPC验证者读取缺失导致原TypeError，全部原目录保留。只新增演示进程读取适配，将缺失观测失败为CHAIN_UNAVAILABLE供既有有限轮询处理，无合成validator/receipt，无核心源码变更；deploy03/final真实执行通过。
2. clean-01 FAIL：旧流程引用空公开卷，容器缺catalog.json，HTTP连接失败。新增成功来源/摘要/实际卷预检、就绪等待和容器诊断，clean02/final通过。
3. 旧块历史权限查询曾Besu Internal error，historical-state-failure.json保留；历史快照不保证现在可查，失败必须UNAVAILABLE，需近期真实证据或未来独立归档节点。临时报表读取GBK错误改显式UTF-8，未改数据。
4. 干净重建复用当前Windows/WSL/Docker、四Besu和已核验Linux wheels/公开证据卷。没有复制.env.local、签名私钥、工具库或旧node_modules；不等于空白OS/全新genesis完整重建。首次机器准备依赖阶段4/5说明，仍未完整演练。
5. 同机四节点/测试签名密钥不等于独立机构托管；仅R2本地SQLite邮箱闭环，不外推真实SMTP一次性效果。其他C工具/R3、生产RPC认证/密钥管理、完整官方AgentDojo utility和大样本多模型仍TODO。
6. Git无HEAD/0跟踪，无Release Commit，不自动提交。匿名PDF和报告源已去身份化；历史日志含宿主路径，全仓库/发布ZIP/正式提交未匿名验收，不能直接把全部results上传为匿名材料。
7. 最终操作员隐私扫描首次使用`\s*`正则跨行吞入空模板的下一配置行而误判，改逐行读取后PASS；模板与干净源码快照摘要一致，未改写密钥。privacy-final.json确认当前Key未进入所扫公开文件和构建上下文、模板空、.env.local受Git忽略；只输出布尔值，不记录Key或其摘要。runtime-final.json确认仅最终8080审计及四Besu运行，8082辅助实例和8081重建实例已停，所有卷保留。

## 下一阶段依赖

本阶段结束等待用户验收；不自动进入新阶段。若用户指定部署扩展，需独立归档节点/组织机器、密钥托管与准入方案及空白环境验收；若指定评测扩展，需完整工具映射/官方兼容性方案与更大配对样本。所有后续工作继续遵守原冻结字段/策略、跨组织审批、工具二验、nonce与链预约，不因控制台增加授权路径。
