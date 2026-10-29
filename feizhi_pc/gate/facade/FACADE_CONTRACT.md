# GateMemory 隔离 facade v1.0

此模块只写新副本环境，不修改原 coordinator、v6 三模块、ledger、kind raw 或生产 state。没有网络、抽取、真人批准入口，不能启动生产链路。实际 `autoreply` 的默认 memory 实例化/抽取/渲染链仍未替换；新增 facade 不等于生产已接入。

## 初始化与消费入口

`GateMemory(workspace, ledger_path=..., journal_path=..., memory_path=..., capacity={"facts":60,"events":40})` 只接受独立、显式 workspace 内的三个不同存储路径。review ledger 必须是已经初始化的真实副本，不能缺失或空文件；生产 state、越界路径、硬链接共享存储拒绝。已有 memory/journal 仍须满足 coordinator 的路径与head契约。

`render()`、`render_existing()`、`query(text="",kind=None,limit=None)`、`stats()` 每次调用都先执行新的 coordinator `guarded_read()`。失败抛固定、不含聊天正文的 `GateUnavailable`，没有任何旧内容缓存或 legacy 回退。ledger/journal 路径缺失、替换或句柄不可用也拒绝。

旧 `FeizhiMemory` 通过 `__new__` 构造纯内存 renderer，不执行 `__init__`、`_load`、`save`；其data只由当次guarded records生成，path为None。query返回深拷贝。stats分开报告stored_count与recallable_count，不等同于聊天render窗口的展示条数。

依赖文件按源码SHA256固定加载。memory所依赖的memrec/schema以私有模块实例绑定，临时导入映射结束即恢复宿主sys.modules；宿主先加载旧memrec不会偷偷切换renderer规则。这只约束正常可信调用方，Python私有属性不是抵御同进程任意恶意代码的权限边界。

## 保存分类的完整绑定

`commit_saved_kind(plan_path=...,result_path=...,kind_ledger_snapshot_path=...,expected_plan_sha256=...,expected_result_sha256=...,batch="A",ledger_batch_key=...)` 只接受已冻结 `eligible-kind-v1.0` 格式。两个expected哈希必须由可信root的固定归档清单提供；不得从待验文件本身现算后当作真实性证明。plan内request_payload_sha256只是完整性/一致性校验，不是认证签名。

步骤如下：

1. 核对plan/results固定文件哈希、版本、results._meta.plan_sha256与引用标签未发送声明；核对请求payload自哈希以及原候选、完整来源和participants未替换。
2. 用逐字冻结的 `classification/kind_core.py.validate` 重新验证保存raw，严格本批cid双射；不相信results中自报validation/joined，也不按缺失kind填默认值。保存joined必须与重新生成joined完全相同。
3. 只读打开分类当时的ledger snapshot，文件哈希须与plan.ledger_snapshot_sha256一致。每条候选、当前评估、完整来源快照与分类当时值一致；**绝不将旧kind补绑为当前新评估哈希**。新评估后即使再次获批，旧kind仍无效。
4. 本facade v1采用较旧coordinator更严格的契约：所选完整receipt中的当前eligible集合必须与该批分类一一对应，而且member eval须与分类时/current eval相同。检查在coordinator已有operation/journal/ledger锁内再次执行，避免批准并发变化时悄悄接收subset。这是新的保守策略，不把旧coordinator有意允许“旧完整批+新单项评估”的兼容行为称作漏洞。
5. 交给coordinator稳定key映射、来源快照绑定、容量和崩溃恢复协议；receipt只返回计数/哈希/intent，不吐正文。

新入eligible候选、待复核、来源变化、分类过期或旧receipt不满足新策略均拒绝；需要新一轮冻结分类及相应完整receipt。调用者不能只改metadata解禁。

## 边界

每次消费者获得的是当次ledger锁定快照的内容。返回之后发生的撤权要由下次消费重新检查，已返回字符串不能当作持续授权或长期缓存。跨存储仍由旧coordinator恢复协议保证收敛，不能宣称单个跨JSON/SQLite原子事务；直接绕过facade调用旧memory/render也不在本契约内。

测试仅用合成fixture。合成人审test_operator验证“再批准不刷新旧分类”；真实人审批准数仍为0。新自然留出集、生产部署和真实人审身份认证仍须另行验收。
