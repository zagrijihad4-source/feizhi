#ifndef WX_BRIDGE_OFFSETS_H
#define WX_BRIDGE_OFFSETS_H

/* Weixin 4.1.9.23 only. */
#define WX_OFF_DOADDMSG          0x166A6BF
#define WX_OFF_SEND_CALL1_TEXT   0x6A35B0
#define WX_OFF_SEND_HC1_TEXT     0x805E4E8
#define WX_OFF_SEND_CALL2        0xDB40
#define WX_OFF_SEND_CALL2_HC1    0x83661E8
#define WX_OFF_SEND_CALL2_HC2    0x8366128
#define WX_OFF_SEND_CALL2_HC3    0x8366068
#define WX_OFF_SEND_CALL3        0x160EBE0

/* 0xDB40 的三个委托：文本消息与收藏表情各有一组。
 * 文本组（wxb_send_text 长期在用）：0x83661E8 / 0x8366068 / 0x8366128
 * 信封组（frida 实测于用户手动发送收藏表情时抓取，2026-10-13 18:41）：
 *     0xDB40 的 rdx = 0x83677E8、r8 = 0x8367888、r9 = 0x8367928
 * 两组都是「空捕获的内联 std::function」（存储区为 0xAA，+0x38 为自指针），
 * 因此只需换 vtable 即可，无需伪造捕获数据。
 * 用文本组去投递信封元素时，pack 正常返回但消息不出现在对端 —— 这正是
 * 之前 type=8 失败的根因。 */
#define WX_OFF_STK_HC1           0x83677E8
#define WX_OFF_STK_HC2           0x8367888
#define WX_OFF_STK_HC3           0x8367928

/* 委托的「文本组」：顺序经 frida 实测确认（2026-10-13 19:29，0xDB40 入口抓取）
 *   d1 = 0x83661E8, d2 = 0x8366128, d3 = 0x8366068
 * 注意 d2/d3 与旧代码相反 —— 旧代码用了 (HC1, HC3, HC2)，文本恰好也能发，
 * 但顺序对其它消息类型可能重要，故统一改为实测顺序。 */
#define WX_OFF_SEND_CALL2_HC2    0x8366128
#define WX_OFF_SEND_CALL2_HC3    0x8366068

/* ------------------------------------------------------------------
 * 图片消息模型（2026-10-13 19:29 frida 实测，用户真实发图时抓取）
 *
 * pack 元素的 vtable = 0x82CB658，由 0x1702E50(block, &content_sp) 写入
 * （其内部先经 0x1702FC0 初始化为基类 vtable 0x805E708，再覆盖为派生值）。
 * 与文本模型 0x805E578 相比，body 坐标下的差异只有：
 *     +0xD0 = 1                  （文本为 0）
 *     +0xD8 = 3                  ★ 消息类型码（文本 1 / 图片 3 / 收藏表情 0x2F）
 *     +0xE0 = UTF-16 路径指针     ★ 内容本体（实测形如 C:\Users\...\Pictures\...）
 *     +0xF0 = 105, +0xF8 = 111   （与路径长度/尺寸相关，实测值随图而变）
 * 字符串槽 +0xB0/+0xC0/+0xC8 布局与文本完全一致。
 * 注意 +0xD8 在 block 坐标下即 +0xE8 —— 与 wxb_send_model 写类型码的位置相同。 */
#define WX_OFF_IMG_MODEL_VT      0x82CB658
#define WX_OFF_IMG_MODEL_BASE_VT 0x805E708
#define WX_OFF_IMG_MODEL_CTOR    0x1702E50

#define WX_MSG_LOCAL_ID_OFF      0x104
#define WX_MSG_ID_OFF            0x108
#define WX_MSG_RUNTIME_TYPE_OFF  0x00C
#define WX_MSG_SUBTYPE_OFF       0x010
#define WX_MSG_TS_OFF            0x110
#define WX_MSG_FROM_OFF          0x018
#define WX_MSG_TO_OFF            0x038
#define WX_MSG_CONTENT_OFF       0x160
#define WX_MSG_SIGNATURE_OFF     0x180

/* ------------------------------------------------------------------
 * 图片消息（发送本地图片文件 → 微信自行上传）
 *
 * 来源：aixed/WeChat-Hook 的开源实现（支持 3.9.10.16 / 4.1.10.27）。
 * 已在本机 4.1.9.23 的 Weixin.dll 上逐项校验：全部指向有效函数/vtable。
 * 关键点：这条路径【不需要我们自己上传 CDN】——只填本地路径 + 文件大小，
 *        上传由微信内部完成。
 * ------------------------------------------------------------------ */
#define WX_OFF_IMG_MSG_VTBL      0x84F96B8   /* 图片消息 vtable */
#define WX_OFF_IMG_MSG_VTB2      0x84F9748
#define WX_OFF_SEND_MESSAGE      0x1677A30   /* 发送入口 struct2, paramStruct */
#define WX_OFF_PARAM1_VTABLE     0x84EC9C8
#define WX_OFF_PARAM2_GLOBAL     0xA0CE0B0   /* 需解引用的全局值 */
#define WX_OFF_PARAM2_1          0x8595F58
#define WX_OFF_PARAM2_2          0x8595E98
#define WX_OFF_PARAM2_3          0x8595DD8
#define WX_OFF_CREATE_PARAM2     0xDF40

/* 图片消息结构内的字段偏移（msgBuf 起） */
#define WX_IMG_OFF_RECEIVER      0xC0
#define WX_IMG_OFF_FILETYPE      0xE8   /* 3=png/jpg 图片, 47=动画表情 */
#define WX_IMG_OFF_PATH          0xF0   /* Unicode 字符串 */
#define WX_IMG_OFF_FILESIZE      0x198
#define WX_IMG_OFF_GUID          0x6B8
#define WX_IMG_MSG_BUF_SIZE      0x7C0

/* ------------------------------------------------------------------
 * 收藏表情（发送本地表情库里已有的表情）
 *
 * 构造链（三者均为函数入口，已用 capstone+.pdata 逐一验证）：
 *   0x15f35c0  内容对象构造  void f(shared_ptr<Content>* out)
 *              operator new(0x70)：前 0x10 是 shared_ptr 控制块，
 *              对象体自 +0x10 起，vtable = 0x82bcc28
 *   0x17040a0  信封构造      void f(shared_ptr<Envelope>* out, shared_ptr<Content>* in)
 *              对象体 vtable = 0x82cb8d8
 *   0x160ebe0  提交          void f(rcxs, result)  (= WX_OFF_SEND_CALL3)
 *
 * 内容对象字段（来自运行时 dump，vt 0x82bcc28）：
 *   +0x020 md5            +0x060 规格md5
 *   +0x0e0 CDN(20401)     +0x100 CDN(20403)     +0x120 规格md5     +0x140 CDN(20402)
 * 信封字段（vt 0x82cb8d8）：
 *   +0x0b0 接收方 wxid    +0x600 消息 UUID      +0x668 内容子对象(shared_ptr)
 *
 * 注意：这些 CDN 链接是微信内部状态里的值（本地表情库只有加密文件、没有链接），
 *      所以只能从"用户实际发过的表情"中采集。实测同一表情重复发送时
 *      md5/filekey/storeid 逐字节相同，说明可复用。
 * ------------------------------------------------------------------ */
#define WX_OFF_CONTENT_CTOR      0x15F35C0
#define WX_OFF_ENVELOPE_CTOR     0x17040A0
#define WX_STK_CONTENT_VTBL      0x82BCC28
#define WX_STK_ENVELOPE_VTBL     0x82CB8D8

#define WX_STK_CONTENT_MD5       0x020
#define WX_STK_CONTENT_MD5B      0x060
#define WX_STK_CONTENT_URL20401  0x0E0
#define WX_STK_CONTENT_URL20403  0x100
#define WX_STK_CONTENT_MD5C      0x120
#define WX_STK_CONTENT_URL20402  0x140

#define WX_STK_ENV_RECEIVER      0x0B0
#define WX_STK_ENV_UUID          0x600
#define WX_STK_ENV_CONTENT       0x660   /* 内容对象 shared_ptr：+0x660=_Ptr, +0x668=_Rep */

/* ------------------------------------------------------------------
 * 收藏表情模板发送（2026-10-13 晚，静态 + 运行时双证，见 TASK_LOG 第九~十一节）
 *
 * 更正上一段的错误：内容对象的【控制块】vtable 是 0x83DCC28（不是 0x82BCC28），
 * 业务对象体 vtable 是 0x8755528。两者关系：
 *   block = operator_new(0x1B0)
 *   [block+0x00] = base + 0x83DCC28   控制块 vtable
 *   [block+0x08] = 0x1_0000_0001      _Uses | _Weaks<<32
 *   [block+0x10] = base + 0x8755528   对象体 vtable（对象体 = block+0x10）
 *   memset(block+0x18, 0, 0x158)
 *   12 个 std::string，buf 从 block+0x20 起 stride 0x20
 *   [block+0x168] = -1
 *
 * 大量实测确认：
 *   - 用户真实发送时走的【不是】WX_OFF_CONTENT_CTOR(0x15F35C0) 那条链
 *     （0x3D67DA0 零触发），实际信封由 0x1AFE710 造、发送由 0x16D4450 发起。
 *   - 每个收藏表情的三条 CDN URL 各含独有 md5（7 个表情的 md5 交集为空），
 *     无法用「一套模板换 md5」泛化，必须逐表情持有模板。
 *     模板库：reports/sticker_templates.json → include/wx_sticker_templates.h
 * ------------------------------------------------------------------ */
#define WX_OFF_STK_OP_NEW           0x64A7D1C   /* operator new(size_t) */
#define WX_OFF_STK_CONTENT_CTL_VT   0x83DCC28   /* 控制块 vtable（_Ref_count_obj2） */
#define WX_OFF_STK_CONTENT_BODY_VT  0x8755528   /* 对象体 vtable */
#define WX_OFF_STK_ENV_FACTORY2     0x1AFE710   /* void f(shared_ptr<Envelope>* out) */
#define WX_OFF_STK_ENV_INIT2        0x1B0E960   /* 被上面调用，new(0x698) 后初始化 */
#define WX_OFF_STK_SEND             0x16D4450   /* void f(&out, &env_sp, r9) —— 仅校验并原样返回信封，非发送 */
#define WX_OFF_STK_SEND_ENTRY       0x16A60D0   /* ★ 真正的发送入口 f(rcx=ctx, rdx=&out, r8=&shared_ptr<TaskContext>) */
#define WX_OFF_STK_CTX_VTBL         0x82C74F8   /* 发送上下文的 vtable（用于运行时扫描定位） */

/* 委托捕获的共享上下文对象（2026-10-13 19:52 frida 实测）
 * 文本组与信封组的 d2/d3 捕获的是同一组指针，其中之一的 vtable =
 * base + 0x8365848（该 vtable 的槽 [+5] = 0x1AFEA70，紧邻信封工厂 0x1AFE710）。
 * 因为它跨消息类型、跨多次发送保持不变，属长生命周期共享对象，
 * 故可用与 send_ctx 相同的运行时扫描方式定位，不必伪造。 */
#define WX_OFF_STK_DELEGATE_CTX_VT  0x8365848

/* ------------------------------------------------------------------
 * 任务上下文 TaskContext（2026-10-13 17:06 定位，静态 + 运行时交叉验证）
 *
 * 实测（frida_dump_send_args.py）：0x16A60D0 的 R8 指向的 shared_ptr，
 * 其 _Ptr 的 vtable 为 0x865DEC8 —— 是【任务上下文】，不是信封。
 * 此前一直传 &env_sp（信封 0x82CB8D8）是调用即崩的直接原因。
 *
 * 构造序列（唯一调用者 0x33FA754 处的原生形态）：
 *   block = operator_new(0xF0)                  ; 0x033fa6f5 mov ecx,0xf0
 *   [block + 0x00] = base + 0x864E018           ; 控制块 vtable
 *   [block + 0x08] = 0x1_0000_0001              ; _Uses=1, _Weaks=1
 *   body  = block + 0x10                        ; 0x033fa738 add rdi,0x10
 *   0x34F0A70(body, &shared_ptr<Envelope>)      ; 基类+派生类两段式构造
 *   ; 结果写入父对象 +0x178/_Rep +0x180
 *
 * body 大小 = 0xE0（与析构路径 0x34F1299 读 [rcx+0xd8] 吻合）
 * ------------------------------------------------------------------ */
#define WX_OFF_STK_TASK_SIZE        0xF0         /* 含 0x10 控制块头 */
#define WX_OFF_STK_TASK_CTL_VT      0x864E018    /* 控制块 vtable */
#define WX_OFF_STK_TASK_CTOR        0x34F0A70    /* f(rcx=body, rdx=&shared_ptr<Envelope>) */
#define WX_OFF_STK_TASK_BASE_VT     0x865DEC8    /* 基类 vtable（运行时实测命中） */
#define WX_OFF_STK_TASK_DERIVED_VT  0x865DEF0    /* 派生类 vtable（基类 +0x28） */
/* ★ 真实发送任务上下文「控制块」的 vtable（TASK_LOG §20.5 实测、§27 用作存活判据）。
 * 注意与上面的 WX_OFF_STK_CTX_VTBL(0x82C74F8) 不是一回事：
 *   0x82C74F8 —— 0x16A60D0 的 rcx，持久「发送器」对象（enable_shared_from_this 风格）
 *   0x7F5F398 —— 0xDB40 第 5 参数指向对象的**控制块** vtable，即每次发送的任务上下文
 * 该 vtable 在一个进程里并非唯一（实测 14+ 个同类实例），因此不能用扫描定位，
 * 必须由 pack 入口捕获。 */
#define WX_OFF_STK_TASKCTX_CTRL_VT  0x7F5F398

#define WX_STK_CONTENT_SIZE         0x1B0
#define WX_STK_STRIDE               0x20
#define WX_STK_FIRST_STR            0x20
#define WX_STK_STR_SLOTS            12
#define WX_STK_ENV_SIZE             0x698

#endif /* WX_BRIDGE_OFFSETS_H */
