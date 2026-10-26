# Sandbox tools：阶段2本地工具

状态：本地原语已实现；真实链预约、TaskGrant、EIP-712工具回执、加密证据和网络服务认证TODO。这里只提供Python内部库和容器测试入口，不开放HTTP端口，不接入Agent。正式execute_reserved永远拒绝CHAIN_UNAVAILABLE，不能用测试许可绕过。

```powershell
# 完整验收，Docker在Ubuntu WSL2
& .\scripts\check_phase2.ps1 -UseWSL
# 分模块真实容器测试
& .\.venv\Scripts\python.exe scripts/run_phase2_container.py --wsl-distro Ubuntu --suite resources
& .\.venv\Scripts\python.exe scripts/run_phase2_container.py --wsl-distro Ubuntu --suite tools
& .\.venv\Scripts\python.exe scripts/run_phase2_container.py --wsl-distro Ubuntu --suite evidence
```

默认宿主pytest只收集本模块无副作用的参数测试；文件/邮箱测试必须运行以上容器套件。Store在Windows、非容器或root身份下拒绝创建；工具只能打开/sandbox下由可信操作员新建的测试数据。无主机文件导入或路径参数。

## 内部调用约定

仅可信操作员在受限容器内使用Store.create()，读取该新沙箱自己的operator.key，调用Resources.create_document创建新测试文件。LocalTestTools.issue_permit需要该密钥，持久保存服务端精确授权，再返回随机令牌。执行进程调用：

```python
record = tools.execute(action_id, "gateway", "doc.read", {"doc_id": "doc-public"}, token)
record = tools.execute(action_id, "gateway", "mail.send", {
    "to": ["test@inbox.chainguard.invalid"], "subject": "test", "body": "synthetic data"
}, token)
record = tools.execute(action_id, "gateway", "doc.delete", {"doc_id": "doc-trash"}, token)
record = tools.status(action_id, "gateway", token)  # 只查询，不执行
```

上述为各自不同actionId/许可的三种调用格式，token不互换。action_id沿用冻结的非零小写bytes32；principal是本地登记的调用标签，必须匹配工具数据库许可；调用者自报标签本身不提供权限，仍须持有精确许可。测试许可不得交给Agent。所有原语仍必须通过工具端资源校验，持有令牌不能扩大文档/收件人范围。

LocalTestPermit持久字段：token_hash、action_id、request_sha256、principal、scope、organization、documents、recipients、allow_delete、expires_at、revoked、consumed。令牌仅保存SHA-256，密钥/原始令牌不进入源码、导出快照或日志。许可最长120秒，删除最长60秒；可撤销；消费和幂等记录协同写入。

## LocalExecutionRecord

这是本地合成测试数据记录，不是冻结ExecutionReceipt或ActionRecord。

| 字段 | 含义 |
|---|---|
| action_id / principal / tool_name | 永久幂等ID、获许可调用标签、冻结工具名 |
| request_sha256 | 对ID/主体/工具/完整参数的本地比较指纹；不是params_commit |
| state | CLAIMED持久占位；对外观察为UNKNOWN；COMPLETED表示原语真实完成；REJECTED表示执行前确认拒绝；UNKNOWN禁止重执行 |
| started_at / completed_at | Unix秒字符串；未知结果的completed_at为空 |
| result / error_code | 真实读取内容base64+哈希、本地邮箱记录ID+MIME哈希，或删除前哈希/inode；异常仅返回固定错误码 |
| record_type / authorization_kind | 固定LocalExecutionRecord / LOCAL_TEST_PERMIT，明确测试边界 |

mailbox逐收件人保存真实MIME BLOB并关联action_id；邮件只投递此本地SQLite邮箱，没有SMTP/网络发送路径。events保存CLAIMED和结果状态。查询不存在动作返回NOT_FOUND，不伪造“未执行”证明。

状态：新动作授权通过→持久CLAIMED→COMPLETED/REJECTED/UNKNOWN；mailbox和完成记录同一事务，无中间可见半提交；文件操作先提交CLAIMED。CLAIMED崩溃遗留/正在进行均保守观察为UNKNOWN。没有自动UNKNOWN→成功恢复操作，后续对账须依据原始证据追加，不能重做副作用。

后续只有在真实授权、签名日志/ExecutionReceipt落盘后，才可映射为冻结READ_OK或EXECUTION_RECORDED；本阶段不提前推进任何链/业务状态。

## 持久化与边界

数据保存在新建私有目录的state.sqlite3，重开Store和重启容器都从相同数据库去重。容器验收以新建Docker命名卷跨两次启动验证，导出真实SQLite快照后移除该测试卷。单个邮箱操作与日志同事务；不将本地事务保证外推到第三方邮件系统。文件系统与SQLite不原子，强制终止进程后保留UNKNOWN，不凭目标缺失宣布成功。

Linux实现用目录描述符、O_NOFOLLOW、单硬链接/普通文件检查、登记inode/设备/内容哈希；目录仅工具OS身份可写。工具进程、操作员和Docker管理员可信，同UID恶意并发修改或卷被管理员恶意替换不在此隔离保证内。SQLite快照未加密、未签名且不防管理员篡改，只存合成测试数据。
