# 隔离可信复核请求边界

`ReviewBoundary(workspace, ledger_copy, request_db, authorizer=None)`；`prepare(candidate_key)`；`apply(request_id)`；`get_packet(request_id)`；只读`inspect(request_id)`。

这是当前实验中的可执行调用边界，不是通用生产授权库。workspace必须是当前集成目录下的专用子目录，不能是集成根、文件系统根或fixtures/runtime/ledger_code/coordinator/review代码目录；review/test_work下的合成测试子目录例外。ledger和request数据库均须位于该workspace，路径互异，禁止原fixtures与F盘生产state。root的真实待复核演练应先复制ledger到real_review目录。

## Prepare 与 Apply 分离

prepare只为当前pending候选生成登记在request数据库里的packet：随机request_id、原候选及完整candidate hash、完整当前evaluation hash、证据/上下文、策略与来源快照版本、decision=null。它不调用authorizer或resolve_review，不批准真实候选。返回packet为副本，调用方修改它不会更改登记内容。

apply仅接受已登记request_id，不接收actor、is_human或decision字段。默认authorizer为DenyAll，任何模型/请求自报“我是人类”不能调用resolve_review。宿主必须在构造时从可信代码注入回调；回调在事务锁外取得packet副本，并仅能从**已经验证的真人决定**生成TrustedDecision，绑定request_id、candidate_key、candidate/evaluation/packet三个hash及明确approve/reject、principal、reason、非秘密authorization_ref、authorized=True。原始dict、缺决定、continue、错主体或错hash一律拒绝。

**回调本身不等于真人认证。** 本模块无法判断人类是否真的说过话；宿主必须从受信任的人类答复/认证UI获取该事实，不能反射请求字段或根据继续工作指令伪造receipt。authorization_ref仅为宿主审计引用，不是天然有效的密码学证明。本轮真实A6/A14/A19/B20不得被自动批准，所有通过apply的测试都使用显式synthetic-test-operator。

## 消费与跨存储顺序

1. 持久登记request attempt，消费request_id；重复apply永不自动resolve。
2. 核对当前pending及hash，调用锁外authorizer，再次进入ledger事务核当前状态。
3. 在ledger外层事务内nested resolve（尚未commit），先提交request receipt，然后才commit ledger。
4. receipt写入失败会回滚ledger；receipt已保存但ledger未commit的崩溃只能留下待对账请求。receipt明确标`ledger_commit_proven_by_receipt=False`，不能仅凭其存在当成批准。

成功返回后无需再写一个必需UI回执，避免ledger已放行后才因写receipt失败而无审计凭证。inspect读取当前ledger与唯一request标记/reviewer/hash核对效果，不修改或重试；当前评估改变会令旧receipt不再匹配。处于attempting/uncertain或效果未证实的receipt请求禁止重复apply，同快照也不会自动重新prepare；需可信调用方人工排查两个存储，不提供自动重批/补批准。

这不是跨SQLite原子事务；回调认证、跨主机并发、断电、磁盘损坏和人类答复真实性不由本模块证明。锁次序要求调用方不能在已有ledger事务内调用boundary；本模块不会在request事务中调用ledger，避免逆序持锁。

## 已覆盖的合成行为

默认拒绝/自报人类无效；明确批准与拒绝；陈旧及异主体/hash拒绝；重复request不重批；authorizer期间评估变化再次拒绝；仅pending可处理；receipt失败ledger回滚；receipt落盘后ledger事务异常不当成批准；packet副本不泄漏；approve→新评估失效→重新授权及重新生成kind绑定。

重分类测试使用合成kind结果，没有真实模型调用，也没有对四条实际pending做决定。代码不导入生产memory或访问真实聊天/生产state。
