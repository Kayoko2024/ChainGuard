# 阶段 2：本地测试工具实施边界

输入：阶段 0 的冻结工具参数、作用域、actionId 与 UNKNOWN 语义，以及阶段 1 的 Python/Docker 工程。冻结文件不修改。

本阶段新增 sandbox_tools/src/chainguard_sandbox 的参数校验、私有资源目录、SQLite 日志、本地邮箱、独立本地测试许可；新增对应测试、隔离镜像、scripts/check_phase2.ps1 和真实副作用验收脚本。README、pyproject.toml 仅接入当前阶段说明与测试路径。gateway 和业务 HTTP 路径不接入工具。

## 本地授权与业务协议的边界

这些是本地测试工具原语，不是已经完成的链上 R2/R3 执行链。隔离测试由可信操作员生成精确绑定 action_id、tool_name、参数摘要、调用主体、资源集合、到期时间的一次性 LocalTestPermit；工具从自己的 SQLite 中独立读取许可并强制校验，拒绝调用者自行声明已批准。操作员密钥只存于容器私有目录，不进入 Agent、源码或验收输出。许可支持撤销和到期，不代表 TaskGrant、EIP-712 批准或 RESERVED。

正式 execute_reserved 入口在真实链核验尚未接入时始终 CHAIN_UNAVAILABLE，不提供本地许可降级。冻结 /v1/tools/execute 不开放。本阶段只保存 LocalExecutionRecord，不生成 ExecutionReceipt、签名、交易或最终链状态；参数中的 doc_id、to、subject、body 直接遵守冻结 Schema。内部 request_sha256 仅用于本地请求比较，不冒充 params_commit。

## 数据、事务与文件边界

- 每次沙箱仅在 Linux 容器 /sandbox 下新建随机私有目录；只创建新的测试文件，不导入主机文件。文档用不透明 doc_id 映射到随机单层文件名，同时登记 scope、组织、disposable、设备/inode、内容 SHA-256。
- 固定目录描述符 + O_NOFOLLOW + 普通文件/单硬链接/inode/内容校验；拒绝路径、符号链接、硬链接、设备、FIFO、被替换或被修改的文件。Agent 无私有目录写权限；同 UID 恶意工具进程不在可信工具假设内。
- mail.send 直接向 SQLite 本地邮箱写入每个收件人的独立消息记录，保存真实 MIME 字节；没有 SMTP、DNS 或外部发送实现。邮箱、许可消费和执行结果同一 SQLite 事务提交。
- doc.read 真实读取字节并记录结果与哈希；doc.delete 只 unlink 登记为 disposable 的新建测试文件，记录删除前哈希、inode 和实际时间。
- action_id 全库唯一；相同主体/工具/参数返回原记录，改变参数或主体拒绝。邮件单事务提交；文件操作先持久 CLAIMED 再执行。文件副作用与数据库不能原子提交，崩溃遗留 CLAIMED 对外观察为 UNKNOWN，禁止自动重执行。文件不存在不能独自证明成功。
- SQLite 的持久本地记录没有防管理员篡改或加密保证；本阶段只存合成测试数据，后续加密证据存储和签名待实现。

## 验收方法

参数与冻结 Schema 交叉验证；分别实际运行资源/持久化/工具测试。隔离容器采用非 root、network=none、只读根、cap_drop=ALL，无主机文件挂载。验收核对实际文档内容与哈希、邮箱 MIME/新增条数、测试文件消失及外部哨兵仍在；测试错误 scope/组织/收件人、穿越/绝对路径/链接、过期/撤销/伪造许可、并发与重复 actionId、跨进程重启和崩溃窗口。两个先后启动的容器共享仅本次创建的 Docker 数据卷，证明持久化与重启去重；结束只移除本次容器和测试卷。

后续依赖：可信 TaskGrant、当前策略/身份、真实合约预约与二次核验、参数承诺、工具签名回执、加密证据、mTLS/服务身份和对账。未接入前不得宣称业务 R2/R3 已可用。
