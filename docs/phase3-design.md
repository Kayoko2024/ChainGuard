# 阶段3实施边界（编码前记录）

输入：阶段0冻结字段、参数Schema、权限/签名门槛；阶段1健康网关；阶段2真实隔离工具及SQLite幂等。21份冻结文件不修改。

待新增：gateway/src/chainguard_gateway下canonical、crypto、identity、policy、central_store、audit、central_service、central_api、central_server；sandbox_tools下中心化工具适配器；gateway/tests与容器集成测试；阶段3构建/验收脚本、依赖闭包和独立HTTP契约；config/phase3-policy-freeze.json。修改main.py以显式注入中心化服务，默认健康实例保持无凭据；更新运行说明。业务合约、Agent、QBFT、React不进入本阶段。

## A/B与未来C

A仅常规账号权限与同一沙箱安全上限；不强制任务级ABAC或动作签名，普通数据库日志。B使用TaskGrant、同一确定性策略、多组织真实EIP-712审批、一次执行、签名哈希链日志。A同时记录策略的shadow决策，不把shadow拒绝算作实际阻断。两组部署配置写入各自持久库，HTTP调用不能切换组别。请求者与Agent均无工具/审计签名私钥。

B/C共用policy.py和冻结risk-rules.json；任务/账号资源、风险、删除默认拒绝、批准角色、时效和参数承诺相同。C后续仅增加真实链预约/共同历史，不通过弱化B制造差异。本阶段无Agent/模型或统计实验，不编造攻击成功率和性能指标。

## API与状态

新增/central/v1下的任务、提议、审批、中心化执行、结果查询、trace及审计检查点。任务/提议/审批字段复用冻结Schema，错误遵守冻结错误映射。中心化响应为CentralActionRecord，状态与链状态分开，所有链证据/ExecutionReceipt均未生成。冻结/v1链执行API不伪装成中央执行；未来C接入时保持原契约。真实成功结果由阶段2工具持久结果证明。

ActionIntent结构及params_commit完全按冻结EIP-712/JCS构造。B签名域使用chainId=0和本部署审计公钥地址作为verifyingContract标识，domain.name/version与冻结结构相同；该地址不是已部署合约。未来C必须配置真实非零chainId和合约地址；B签名不用于C。请求者和业务/安全/人工批准者私钥只在独立测试签名端，网关仅恢复地址并读取当前登记角色/组织。

## 持久与审计

身份/任务/完整参数/盐加密保存在中央SQLite，密钥仅私有本地数据目录。JWT使用固定HS256、issuer/audience/时间/subject校验，角色与组织由服务登记表给出。配额和动作幂等资格在事务中原子消费；工具重新读取当前任务/策略/签名并检查参数承诺。先写签名dispatch日志再调用工具。跨数据库崩溃窗口保留UNKNOWN，禁止盲目重发。

ActionTrace不记录正文、收件人、资源路径、盐或私钥，只记录随机ID、策略版本/承诺、判定、实际结果和观测时间。B每个事件用前项哈希链接并真实签名；SQLite触发器禁止普通UPDATE/DELETE；检查点由独立持有者保存才能发现合法尾部截断。B仍由一个运营方治理，不能声称抵抗拥有日志私钥/数据库和全部检查点的管理员。

## 验收

先运行纯模块参数/策略/身份/签名/日志测试，再在非root、无网络、只读根且无主机目录挂载的容器中运行真实FastAPI+工具集成。正常邮件核对实际邮箱/MIME，越权和默认删除核对副作用为零；缺签、同组织、错域、调包、撤销、过期、额度、并发/幂等、审计篡改/尾截断均测试。实际Uvicorn HTTP烟测与重启后回放验证持久性；保留真实SQLite/trace/检查点证据和测试报告。最后冻结B/C共用策略代码/规则指纹并检查原21文件、原Python/Hardhat及工具回归。
