/* 收藏表情模板发送器。
 *
 * 依据（见 TASK_LOG_发送收藏表情.md 第九至十一节，全部为静态反汇编 + 运行时双证）：
 *
 *   内容对象（Content）：
 *     block  = operator_new(0x1B0)
 *     [block+0x00] = base + 0x83DCC28   控制块 vtable（含 _Uses/_Weaks 释放协议）
 *     [block+0x08] = 0x1_0000_0001      _Uses=1, _Weaks=1
 *     memset(block+0x18, 0, 0x158)
 *     [block+0x10] = base + 0x8755528   对象体 vtable；对象体 = block + 0x10
 *     12 个 std::string，buf 从 block+0x20 起 stride 0x20：
 *       0x20 md5        0x60 spec md5   0xe0 url 20401
 *       0x100 url 20403 0x120 aux md5   0x140 url 20402
 *     [block+0x168] = -1
 *
 *   信封（Envelope）：0x1AFE710(&out_sp) 内部 new(0x698) 并初始化，
 *     输出 shared_ptr{_Ptr = block+0x10, _Rep = block}。
 *     字段（相对 body = block+0x10）：
 *       +0xd8 = 0x2F（收藏表情类型码）
 *       +0xb0 = 接收者 wxid（std::string）
 *       +0x600 = UUID（std::string）
 *       +0x660 = 内容对象体指针，+0x668 = 内容对象控制块指针（一对 shared_ptr）
 *
 *   发送入口：0x16D4450(rdx = &out_sp, r8 = &env_sp, r9 = ?)
 *     r9 含义未定性，先传 NULL 并以 stage 码回报结果。
 *
 * 内存归属：内容对象与信封都由微信自己的 operator new 分配，
 *           其 std::string 缓冲同样用微信 operator new，
 *           保证微信析构时 free 到合法堆块上。
 */
#include "../include/wx_bridge_memory.h"
#include "../include/wx_bridge_native_call.h"
#include "../include/wx_bridge_offsets.h"
#include "../include/wx_bridge_runtime.h"
#include "../include/wx_bridge_send_text.h"
#include "../include/wx_bridge_wechat_string.h"
#include "../include/wx_sticker_templates.h"
#include "../include/wx_bridge_protocol.h"
#include "../include/wx_bridge_paths.h"
#include "../include/wx_bridge_file_io.h"

/* 定义在 send_runtime.c，与 send_text.c 的用法一致 */
void wxb_retain_send_arena(void *arena);

/* 0xDB40 实际接收六个参数（rcx/rdx/r8/r9 + 两个栈槽）。
 * 早期只传五个 —— 第六个（原生为递增计数）缺失，故不能把旧的失败
 * 归因于委托或第 5 参数。 */
typedef int64_t (*WxbFn6)(int64_t, int64_t, int64_t, int64_t, int64_t, int64_t);

/* 把诊断写进独立文件，避免被 outbox.c 的 status 覆盖 */
static void tpl_dbg(const char *text) {
    WCHAR path[MAX_PATH];
    if (!wxb_paths_ready()) return;
    wsprintfW(path, L"%s\\tpl_debug.txt", CONTROL_DIR);
    append_file_bytes(path, text, lstrlenA(text));
}

/* ------------------------------------------------------------------
 * 发送上下文（session context）定位
 *
 * 由运行时捕获确认（TASK_LOG 第十三节）：
 *   - 0x16A60D0(rcx = ctx, rdx = &out, r8 = &env_sp) 才是真正的发送入口
 *     （0x16D4450 只校验并原样返回信封；0x34F01F0 只比较并记日志）
 *   - ctx 是持久对象：vtable = base+0x82C74F8，发送后依然存活（已用
 *     ReadProcessMemory 复读验证 vtable 未变）
 *   - ctx 的强特征：+0x00 = vtable，+0x08 = 指向自身，
 *     +0x10 = 自身 - 0x10（enable_shared_from_this 风格）
 *   - ctx 地址随进程重启变化，故不能硬编码，改为运行时扫描定位
 * ------------------------------------------------------------------ */
static int64_t g_send_ctx = 0;

static int64_t wxb_find_send_ctx(int64_t base) {
    MEMORY_BASIC_INFORMATION mbi;
    BYTE *addr = NULL;
    const int64_t want_vt = base + WX_OFF_STK_CTX_VTBL;

    if (g_send_ctx) return g_send_ctx;

    while (VirtualQuery(addr, &mbi, sizeof(mbi)) == sizeof(mbi)) {
        BYTE *p, *end;
        /* 只扫「已提交 + 可读 + 非保护页」的私有内存（堆） */
        if (mbi.State == MEM_COMMIT &&
            mbi.Type == MEM_PRIVATE &&
            (mbi.Protect & (PAGE_READONLY | PAGE_READWRITE |
                            PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE)) &&
            !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))) {
            p = (BYTE *)mbi.BaseAddress;
            end = p + mbi.RegionSize;
            for (; p + 0x18 <= end; p += 8) {
                if (*(const int64_t *)p == want_vt &&
                    *(const int64_t *)(p + 8) == (int64_t)p &&
                    *(const int64_t *)(p + 0x10) == (int64_t)p - 0x10) {
                    g_send_ctx = (int64_t)p;
                    return g_send_ctx;
                }
            }
        }
        addr = (BYTE *)mbi.BaseAddress + mbi.RegionSize;
        if (addr <= (BYTE *)mbi.BaseAddress) break;   /* 防溢出/死循环 */
    }
    return 0;
}

/* 委托捕获的真实地址由 frida 在【自然发送】时抓取，写入
 *   control\delegate_caps.txt    格式：
 *     A=<hex>          d2/d3 的共享对象（vtable 0x8365848）
 *     B=<hex>          d2/d3 的第二个捕获（类型未定）
 *     D1_08=<hex>      d1 的 +0x08（堆指针）
 *     D1_18=<rva hex>  d1 的 +0x18（析构函数，相对 RVA，例如 a3e5）
 * A/B 是跨消息类型、跨多次发送保持不变的持久对象，因此抓一次即可复用
 * （进程重启后失效，需重抓）。
 *
 * 为什么必须这样做：0x160DF80 内部只用静态常量 0x7F5E280 初始化三个委托的
 * 内联存储，真实捕获来自它的第 5 个栈参数 [r14+0x38] —— 来源在上层 UI 调用链。
 * 其中 d1 的 +0x10 是【栈地址】（指向调用者的临时对象），天然无法跨调用复用，
 * 故显式跳过；+0x08 与 +0x18 可复用（+0x18 经反汇编确认为 scalar deleting
 * destructor 的非删除分支 0xA3E5）。 */
static unsigned long long strtoull_hex(const char *s);
static int64_t g_cap_d1_08 = 0;
static int64_t g_cap_d1_18_rva = 0;

static void wxb_load_delegate_caps(int64_t *outA, int64_t *outB) {
    char buf[512];
    int n;
    const char *p;
    WCHAR path[MAX_PATH];

    if (outA) *outA = 0;
    if (outB) *outB = 0;
    g_cap_d1_08 = 0;
    g_cap_d1_18_rva = 0;
    if (!wxb_paths_ready()) return;
    wsprintfW(path, L"%s\\delegate_caps.txt", CONTROL_DIR);
    n = read_file_bytes(path, buf, sizeof(buf) - 1);
    if (n <= 0) return;
    buf[n] = 0;
    for (p = buf; *p; ) {
        if ((p[0] == 'A' || p[0] == 'a') && p[1] == '=') {
            if (outA) *outA = (int64_t)strtoull_hex(p + 2);
        } else if ((p[0] == 'B' || p[0] == 'b') && p[1] == '=') {
            if (outB) *outB = (int64_t)strtoull_hex(p + 2);
        } else if (p[0] == 'D' && p[1] == '1' && p[2] == '_' &&
                   p[3] == '0' && p[4] == '8' && p[5] == '=') {
            g_cap_d1_08 = (int64_t)strtoull_hex(p + 6);
        } else if (p[0] == 'D' && p[1] == '1' && p[2] == '_' &&
                   p[3] == '1' && p[4] == '8' && p[5] == '=') {
            g_cap_d1_18_rva = (int64_t)strtoull_hex(p + 6);
        }
        while (*p && *p != '\n') p++;
        if (*p == '\n') p++;
    }
    {
        char dbg[256];
        wsprintfA(dbg,
                  "caps: n=%d A=%p B=%p D1_08=%p D1_18rva=%p\n",
                  n, (void *)(outA ? *outA : 0), (void *)(outB ? *outB : 0),
                  (void *)g_cap_d1_08, (void *)g_cap_d1_18_rva);
        tpl_dbg(dbg);
    }
}

/* 极简十六进制解析（避免引入 CRT 依赖） */
static unsigned long long strtoull_hex(const char *s) {
    unsigned long long v = 0;
    int i;
    for (i = 0; i < 16 && s[i]; i++) {
        char c = s[i];
        int d;
        if (c >= '0' && c <= '9') d = c - '0';
        else if (c >= 'a' && c <= 'f') d = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') d = c - 'A' + 10;
        else break;
        v = (v << 4) | (unsigned)d;
    }
    return v;
}

/* ---- 真实任务上下文的读取与校验（免点击的关键，TASK_LOG §27） ----
 *
 * 背景：0xDB40 会把第 5 参数 d4 处的 [d4] / [d4+8] 原样搬进 cfg[0] / cfg[8]。
 * 我们自造的 d4 是 ZeroMemory 过的空块 ⇒ cfg 里是空上下文 ⇒ 消息被判「发送失败」
 * （§27.2 把它定位到了具体代码行）。自然发送时这两个值是真实的
 * shared_ptr<TaskContext>，由 frida 侧在 pack(0x160EBE0) 入口捕获并落盘为
 *   control\ctx_override.txt   格式： BODY=<hex>\nCTRL=<hex>\nPID=<dec>\n
 *
 * 本函数读取该文件并做**存活校验**——地址只在微信进程存活期内有效，
 * 微信重启或对象被回收后必须拒绝，否则就是把悬空指针喂给 0xDB40。
 * 校验项与 frida 侧一致：
 *   ① body == ctrl + 0x10      （MSVC _Ref_count_obj2 的对象体紧邻控制块）
 *   ② [ctrl] == base + 0x7F5F398（控制块 vtable，§20.5 实测值）
 * 返回 1 表示可用（并回填 outBody/outCtrl），0 表示不可用。 */
static int wxb_load_ctx_override(int64_t base, int64_t *outBody, int64_t *outCtrl) {
    char buf[256];
    int n;
    const char *p;
    WCHAR path[MAX_PATH];
    int64_t body = 0, ctrl = 0;

    if (outBody) *outBody = 0;
    if (outCtrl) *outCtrl = 0;
    if (!wxb_paths_ready()) return 0;
    wsprintfW(path, L"%s\\ctx_override.txt", CONTROL_DIR);
    n = read_file_bytes(path, buf, sizeof(buf) - 1);
    if (n <= 0) return 0;
    buf[n] = 0;
    for (p = buf; *p; ) {
        if (p[0] == 'B' && p[1] == 'O' && p[2] == 'D' && p[3] == 'Y' && p[4] == '=')
            body = (int64_t)strtoull_hex(p + 5);
        else if (p[0] == 'C' && p[1] == 'T' && p[2] == 'R' && p[3] == 'L' && p[4] == '=')
            ctrl = (int64_t)strtoull_hex(p + 5);
        while (*p && *p != '\n') p++;
        if (*p == '\n') p++;
    }
    if (!body || !ctrl) return 0;
    if (body != ctrl + 0x10) return 0;
    if (r64((void *)ctrl) != base + WX_OFF_STK_TASKCTX_CTRL_VT) return 0;
    if (outBody) *outBody = body;
    if (outCtrl) *outCtrl = ctrl;
    return 1;
}

#define WXB_TPL_CONTENT_SIZE   0x1B0

/* 委托捕获的共享上下文对象：文本组与信封组的 d2/d3 捕获同一组指针，
 * 其中之一的 vtable = base + 0x8365848（跨消息类型、跨发送保持不变）。
 * 定位方式与 send_ctx 相同：扫描私有堆找 vtable 匹配的实例。 */
static int64_t g_delegate_ctx = 0;

static int64_t wxb_find_delegate_ctx(int64_t base) {
    MEMORY_BASIC_INFORMATION mbi;
    BYTE *addr = NULL;
    const int64_t want_vt = base + WX_OFF_STK_DELEGATE_CTX_VT;

    if (g_delegate_ctx) return g_delegate_ctx;

    while (VirtualQuery(addr, &mbi, sizeof(mbi)) == sizeof(mbi)) {
        BYTE *p, *end;
        if (mbi.State == MEM_COMMIT &&
            mbi.Type == MEM_PRIVATE &&
            (mbi.Protect & (PAGE_READONLY | PAGE_READWRITE |
                            PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE)) &&
            !(mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))) {
            p = (BYTE *)mbi.BaseAddress;
            end = p + mbi.RegionSize;
            for (; p + 0x18 <= end; p += 8) {
                if (*(const int64_t *)p == want_vt) {
                    g_delegate_ctx = (int64_t)p;
                    return g_delegate_ctx;
                }
            }
        }
        addr = (BYTE *)mbi.BaseAddress + mbi.RegionSize;
        if (addr <= (BYTE *)mbi.BaseAddress) break;
    }
    return 0;
}
#define WXB_TPL_STRIDE         0x20
#define WXB_TPL_FIRST_STR      0x20
#define WXB_TPL_STR_SLOTS      12

/* 模板字段 -> 内容对象内的槽位序号（0 基，槽 i 在 block + 0x20 + i*0x20） */
#define WXB_TPL_SLOT_LIB_MD5   0   /* 0x20  */
#define WXB_TPL_SLOT_SPEC_MD5  2   /* 0x60  */
#define WXB_TPL_SLOT_URL_20401 6   /* 0xe0  */
#define WXB_TPL_SLOT_URL_20403 7   /* 0x100 */
#define WXB_TPL_SLOT_AUX_MD5   8   /* 0x120 */
#define WXB_TPL_SLOT_URL_20402 9   /* 0x140 */

/* ============ 表情包（表情商店添加）表情 ============
 * 与收藏表情走同一条发送链路、同一个对象类型，但内容对象的字段落点不同
 * （TASK_LOG §29 逐字段实测）：
 *
 *                       收藏表情            表情包表情
 *   body+0x08           3                   5
 *   slot0               lib_md5             该表情 md5
 *   slot1               空                  专辑 ID
 *                                           com.tencent.xin.emoticon.person.stiker_<…>
 *   slot2/6/7/8/9       md5 ×3 + 3 条 URL  空（地址由微信自行解析）
 *   slot10              —                   名字（如「空降」）
 *   body+0x150          0x12 << 32          0
 *   body+0x158          5                   -1
 *
 * 控制块/对象体尺寸与 vtable 与收藏表情完全相同（0x1B0 / 0x158 / 0x8755528）。
 * 专辑 ID 在同专辑内所有表情上完全相同，且跨多次发送不变 ⇒ 是固有 ID，可预先构造。 */
typedef struct {
    const char *md5;        /* 该表情的 md5（slot0） */
    const char *album_id;   /* 专辑 ID（slot1），同专辑相同 */
    const char *name;       /* 名字（slot10），可为 NULL */
} wxb_pack_tpl;

#define WXB_PACK_SLOT_MD5      0    /* body+0x010 */
#define WXB_PACK_SLOT_ALBUM    1    /* body+0x030 */
#define WXB_PACK_SLOT_NAME     10   /* body+0x160（注意不是 0x10+10*0x20） */

static const wxb_pack_tpl g_wxb_pack_tpls[] = {
    { "1b09ef505de4501c4f77569207864e4b",
      "com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd",
      "\xe7\xa9\xba\xe9\x99\x8d" },   /* 空降 */
    { "a6d3a7abb8d7084bff4540c7e5676184",
      "com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd",
      "\xe7\xa9\xba\xe9\x99\x8d" },
    { "ebd98e27c7fc8b50a19496d188d359e4",
      "com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd",
      "\xe7\xa9\xba\xe9\x99\x8d" },
    { "ca9d0631d936ad6fd5893f663d98650d",
      "com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd",
      "\xe7\xa9\xba\xe9\x99\x8d" },
};
#define WXB_PACK_TPL_COUNT ((int)(sizeof(g_wxb_pack_tpls) / sizeof(g_wxb_pack_tpls[0])))

/* 用微信 operator new 分配，返回值直接可用；失败返回 0 */
typedef void *(*WxbOpNew)(size_t);

static WxbOpNew wxb_op_new(int64_t base) {
    return (WxbOpNew)(base + WX_OFF_STK_OP_NEW);
}

/* 在微信堆上构造一个 std::string（buf 指向微信堆，保证析构安全）。
 *   sp      : std::string 的地址
 *   text    : UTF-8 文本
 *   len     : 文本长度
 *   op_new  : 微信 operator new
 *
 * 容量约定（与原生逐字段对齐，见 TASK_LOG 第十五节）：
 *   原生 dump 中 len=32 → cap=47，len=324 → cap=335，即 cap = len | 0xF。
 *   MSVC 的 capacity 不含结尾 NUL，故实际需分配 cap+1 字节。
 *   早期版本只分配 len+1 却声明 cap=len|0xF，容量与真实分配不符（已修正）。
 */
static int wxb_heap_string(int64_t sp, const char *text, int len, WxbOpNew op_new) {
    char *buf;
    int cap;
    if (!text || len <= 0) {
        /* 空串：SSO，cap=0xF，len=0 */
        w64((void *)(sp + 0x10), 0);
        w64((void *)(sp + 0x18), 0xF);
        return 1;
    }
    cap = len | 0xF;
    /* 短串必须抬到 SSO 阈值之上：MSVC 的 std::string 以 cap <= 0xF 判定「内联存储」，
     * 若 len <= 15 时仍写 cap = len|0xF（必然 <= 0xF），而 buf 却是堆指针，
     * 读取方就会把指针字节当成文本解析 —— 静默读到垃圾。
     * 收藏表情的槽都是 32/324 字节，不会触发；表情包表情的名字只有 6 字节，正好会踩到。 */
    if (cap <= 0xF) cap = 0x1F;
    buf = (char *)op_new((size_t)cap + 1);
    if (!buf) return 0;
    ZeroMemory(buf, (SIZE_T)cap + 1);
    CopyMemory(buf, text, (SIZE_T)len);
    buf[len] = 0;
    w64((void *)sp, (int64_t)buf);          /* buf  */
    w64((void *)(sp + 0x10), (int64_t)len); /* len  */
    w64((void *)(sp + 0x18), (int64_t)cap); /* cap：与真实分配一致 */
    return 1;
}

/* 12 个 std::string 槽位相对 block 的偏移。
 * 前 10 个连续（0x20 + slot*0x20），第 11/12 个跳过分隔的元数据区。 */
static int64_t wxb_slot_offset(int slot) {
    if (slot < 10) return (int64_t)(WXB_TPL_FIRST_STR + slot * WXB_TPL_STRIDE);
    if (slot == 10) return 0x170;
    return 0x190;
}

/* 分配并初始化一个内容对象；成功返回 block，失败返回 0。 */
static int64_t wxb_build_content(const wxb_stk_tpl *tpl, int64_t base, WxbOpNew op_new) {
    BYTE *block;
    int i;

    block = (BYTE *)op_new(WXB_TPL_CONTENT_SIZE);
    if (!block) return 0;

    /* 控制块头 */
    w64(block + 0x08, 0x100000001LL);            /* _Uses=1, _Weaks=1 */
    w64(block, base + WX_OFF_STK_CONTENT_CTL_VT); /* 控制块 vtable */
    ZeroMemory(block + 0x18, 0x158);             /* 覆盖 [0x18, 0x170) */

    /* 对象体 vtable（对象体起点 = block + 0x10） */
    w64(block + 0x10, base + WX_OFF_STK_CONTENT_BODY_VT);

    /* 12 个 std::string 初始为 SSO 空串。
     * 注意：它们【不是全程连续】——原生布局（见 ctor_3d67da0.asm）为
     *   前 10 个 @ block+0x20 .. 0x140（stride 0x20）
     *   block+0x160..0x16F 是元数据区（其中 +0x168 为 int32 = -1）
     *   第 11 个 @ block+0x170（len@0x180, cap@0x188）
     *   第 12 个 @ block+0x190（len@0x1A0, cap@0x1A8）
     * 早期实现按 0x20+i*0x20 连续跑 12 次，会把第 11 个 string 的 buf
     * （0x170/0x178）写坏 —— 已按原生偏移表修正。
     *
     * 并且必须【连同 16 字节 buf 一起清零】：
     * 前面的 memset 只覆盖 [0x18,0x170)，尾部两项的 buf
     * （0x170..0x17F、0x190..0x19F）不在其中，而 operator new 返回的
     * 存储不保证清零。原生工厂对这 16 字节 buf 是显式清零的。 */
    for (i = 0; i < WXB_TPL_STR_SLOTS; i++) {
        int64_t sp = (int64_t)block + wxb_slot_offset(i);
        w64((void *)sp, 0);             /* buf[0..7]  */
        w64((void *)(sp + 0x08), 0);    /* buf[8..15] */
        w64((void *)(sp + 0x10), 0);    /* len        */
        w64((void *)(sp + 0x18), 0xF);  /* cap = SSO  */
    }
    /* 运行时对比修正（compare_content.py，2026-10-13 18:34）：
     * 把「我们构造的内容对象」与「微信自己在 pack 时持有的内容对象」
     * 逐字段比对后发现，12 个 std::string 槽完全一致（len/cap 全同），
     * 但下面三个整数字段原生有确定值，而早期静态分析给的是 0/0/-1：
     *     body+0x008 = 3            业务类型/状态
     *     body+0x150 = 0x12 << 32   （低 32 位为 0，高 32 位 18）
     *     body+0x158 = 5            （静态初值为 -1，运行时被改写）
     * 对应到 block 坐标即 +0x018 / +0x160 / +0x168。
     * 这三个字段极可能就是「这条消息被当成收藏表情投递」的判据，
     * 缺失时表现为：pack 被正常调用、对端收不到、也不报错。 */
    w32(block + 0x018, 3);
    w64(block + 0x160, 0x12LL << 32);
    w32(block + 0x168, 5);

    /* 填入模板字段 */
    {
        struct { int slot; const char *text; } fill[] = {
            { WXB_TPL_SLOT_LIB_MD5,   tpl->lib_md5 },
            { WXB_TPL_SLOT_SPEC_MD5,  tpl->spec_md5 },
            { WXB_TPL_SLOT_AUX_MD5,   tpl->aux_md5 },
            { WXB_TPL_SLOT_URL_20401, tpl->url_20401 },
            { WXB_TPL_SLOT_URL_20403, tpl->url_20403 },
            { WXB_TPL_SLOT_URL_20402, tpl->url_20402 },
        };
        for (i = 0; i < (int)(sizeof(fill) / sizeof(fill[0])); i++) {
            int64_t sp = (int64_t)block + wxb_slot_offset(fill[i].slot);
            int n = fill[i].text ? lstrlenA(fill[i].text) : 0;
            if (!wxb_heap_string(sp, fill[i].text, n, op_new)) return 0;
        }
    }
    return (int64_t)block;
}

/* 构造「表情包型」内容对象。骨架与 wxb_build_content 相同（控制块 0x1B0、
 * 对象体 0x158、vtable 0x8755528），差异只在三个整数字段与字符串槽的落点。 */
static int64_t wxb_build_content_pack(const wxb_pack_tpl *tpl, int64_t base,
                                      WxbOpNew op_new) {
    BYTE *block;
    int i;

    if (!tpl || !tpl->md5 || !tpl->album_id) return 0;
    block = (BYTE *)op_new(WXB_TPL_CONTENT_SIZE);
    if (!block) return 0;

    w64(block + 0x08, 0x100000001LL);
    w64(block, base + WX_OFF_STK_CONTENT_CTL_VT);
    ZeroMemory(block + 0x18, 0x158);
    w64(block + 0x10, base + WX_OFF_STK_CONTENT_BODY_VT);

    for (i = 0; i < WXB_TPL_STR_SLOTS; i++) {
        int64_t sp = (int64_t)block + wxb_slot_offset(i);
        w64((void *)sp, 0);
        w64((void *)(sp + 0x08), 0);
        w64((void *)(sp + 0x10), 0);
        w64((void *)(sp + 0x18), 0xF);
    }

    /* ★ 这三处是表情包表情与收藏表情的实质差异（§29.2 实测） */
    w32(block + 0x018, 5);           /* body+0x08 = 5（收藏为 3） */
    w64(block + 0x160, 0);           /* body+0x150 = 0（收藏为 0x12<<32） */
    w32(block + 0x168, -1);          /* body+0x158 = -1（收藏为 5） */

    {
        struct { int slot; const char *text; } fill[] = {
            { WXB_PACK_SLOT_MD5,   tpl->md5 },
            { WXB_PACK_SLOT_ALBUM, tpl->album_id },
            { WXB_PACK_SLOT_NAME,  tpl->name },
        };
        for (i = 0; i < (int)(sizeof(fill) / sizeof(fill[0])); i++) {
            int64_t sp = (int64_t)block + wxb_slot_offset(fill[i].slot);
            int n = fill[i].text ? lstrlenA(fill[i].text) : 0;
            if (!wxb_heap_string(sp, fill[i].text, n, op_new)) return 0;
        }
    }
    return (int64_t)block;
}

/* 只构造内容对象并把它 dump 成十六进制，不做任何发送。
 * 用途：外部复核指出「已有差异表只打印旧原生样本，从未读取新手工构造的对象」，
 *       本函数补上这一环 —— 构造后落盘，供离线做真实的逐字段核验。
 * 安全性：不调用任何发送入口，无副作用风险。
 * 返回：1 成功；负数表示失败阶段。 */
int wxb_dump_content_tpl(int tpl_index) {
    int64_t base;
    WxbOpNew op_new;
    int64_t block;
    WCHAR path[MAX_PATH];
    char hex[WXB_TPL_CONTENT_SIZE * 2 + 1];
    const BYTE *p;
    int i;

    if (tpl_index < 0 || tpl_index >= WXB_STK_TPL_COUNT) return -1;
    if (!wxb_weixin_module() || !wxb_paths_ready()) return -1;

    base = (int64_t)wxb_weixin_module();
    op_new = wxb_op_new(base);
    block = wxb_build_content(&g_wxb_stk_tpls[tpl_index], base, op_new);
    if (!block) return -2;

    p = (const BYTE *)block;
    for (i = 0; i < WXB_TPL_CONTENT_SIZE; i++) {
        hex[i * 2] = "0123456789abcdef"[p[i] >> 4];
        hex[i * 2 + 1] = "0123456789abcdef"[p[i] & 0xF];
    }
    hex[WXB_TPL_CONTENT_SIZE * 2] = 0;

    wsprintfW(path, L"%s\\content_built.hex", CONTROL_DIR);
    write_file_bytes(path, hex, (DWORD)lstrlenA(hex));

    /* 同时记录该模板的关键字段，便于离线核对是否为预期模板 */
    wsprintfW(path, L"%s\\content_built.txt", CONTROL_DIR);
    {
        char info[512];
        wsprintfA(info,
                  "tpl=%d\r\nlib_md5=%s\r\nspec_md5=%s\r\naux_md5=%s\r\n"
                  "url_20401_len=%d\r\nurl_20403_len=%d\r\nurl_20402_len=%d\r\n"
                  "content_size=%d\r\n",
                  tpl_index,
                  g_wxb_stk_tpls[tpl_index].lib_md5 ? g_wxb_stk_tpls[tpl_index].lib_md5 : "(null)",
                  g_wxb_stk_tpls[tpl_index].spec_md5 ? g_wxb_stk_tpls[tpl_index].spec_md5 : "(null)",
                  g_wxb_stk_tpls[tpl_index].aux_md5 ? g_wxb_stk_tpls[tpl_index].aux_md5 : "(null)",
                  g_wxb_stk_tpls[tpl_index].url_20401 ? lstrlenA(g_wxb_stk_tpls[tpl_index].url_20401) : 0,
                  g_wxb_stk_tpls[tpl_index].url_20403 ? lstrlenA(g_wxb_stk_tpls[tpl_index].url_20403) : 0,
                  g_wxb_stk_tpls[tpl_index].url_20402 ? lstrlenA(g_wxb_stk_tpls[tpl_index].url_20402) : 0,
                  WXB_TPL_CONTENT_SIZE);
        write_file_bytes(path, info, (DWORD)lstrlenA(info));
    }
    return 1;
}

/* 只构造「内容对象 → 信封 → TaskContext」全链并 dump，不做发送。
 * 目的：在真正调用 0x16A60D0 之前，先用零风险方式验证
 *       TaskContext（0xF0 字节，基类 vtable 0x865DEC8）能否被正确构造出来。
 * 返回：1 成功；负数表示失败阶段。 */
int wxb_dump_task_tpl(int tpl_index) {
    int64_t base;
    WxbOpNew op_new;
    int64_t block = 0, env_block = 0, env_body = 0, task_block = 0, task_body = 0;
    BYTE *env_sp = NULL, *task_sp = NULL;
    BYTE *arena = NULL;
    const SIZE_T ARENA_SIZE = 0x2000;
    WCHAR path[MAX_PATH];
    int stage = 0;

    if (tpl_index < 0 || tpl_index >= WXB_STK_TPL_COUNT) return -1;
    if (!wxb_weixin_module() || !wxb_paths_ready()) return -1;

    base = (int64_t)wxb_weixin_module();
    op_new = wxb_op_new(base);

    arena = (BYTE *)VirtualAlloc(NULL, ARENA_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!arena) return -1;
    ZeroMemory(arena, ARENA_SIZE);
    env_sp = arena + 0x0000;
    task_sp = arena + 0x0800;

    /* 1) 内容对象 */
    stage = 1;
    block = wxb_build_content(&g_wxb_stk_tpls[tpl_index], base, op_new);
    if (!block) return -(stage);

    /* 2) 信封 */
    stage = 2;
    ((FnCall1)(base + WX_OFF_STK_ENV_FACTORY2))((int64_t)env_sp);
    env_block = (int64_t)r64(env_sp + 8);
    env_body = (int64_t)r64(env_sp);
    if (!env_block || env_body != env_block + 0x10) return -(stage);

    /* 3) 填信封字段（与发送路径完全一致） */
    stage = 3;
    w32((void *)(env_body + 0xD8), 0x2F);
    if (!wxb_heap_string(env_body + 0xB0, "filehelper", 10, op_new)) return -(stage);
    {
        char uuid[37];
        static const char *hx = "0123456789abcdef";
        unsigned long long t = (unsigned long long)GetTickCount64();
        unsigned long long mix = t * 0x9E3779B97F4A7C15ULL ^ (unsigned long long)(uintptr_t)&uuid;
        int i;
        for (i = 0; i < 36; i++) {
            if (i == 8 || i == 13 || i == 18 || i == 23) { uuid[i] = '-'; continue; }
            mix = mix * 6364136223846793005ULL + 1442695040888963407ULL;
            uuid[i] = hx[(mix >> 33) & 0xF];
        }
        uuid[36] = 0;
        if (!wxb_heap_string(env_body + 0x600, uuid, 36, op_new)) return -(stage);
    }
    w64((void *)(env_body + 0x660), block + 0x10);
    w64((void *)(env_body + 0x668), block);
    w32((void *)(block + 0x08), (int32_t)(r32((void *)(block + 0x08)) + 1));

    /* 4) TaskContext：new(0xF0) → 写控制块 → 调 0x34F0A70(body, &env_sp) */
    stage = 4;
    task_block = (int64_t)op_new(WX_OFF_STK_TASK_SIZE);
    if (!task_block) return -(stage);
    w64((void *)(task_block + 0x00), base + WX_OFF_STK_TASK_CTL_VT);
    w64((void *)(task_block + 0x08), 0x100000001LL);
    task_body = task_block + 0x10;
    ((void (*)(int64_t, int64_t))(base + WX_OFF_STK_TASK_CTOR))(
        task_body, (int64_t)env_sp);
    w64((void *)task_sp, task_body);
    w64((void *)(task_sp + 8), task_block);

    /* 5) 落盘：TaskContext 头部 + 关键偏移核对 */
    {
        char hex[WX_OFF_STK_TASK_SIZE * 2 + 1];
        const BYTE *p = (const BYTE *)task_block;
        int i;
        for (i = 0; i < (int)WX_OFF_STK_TASK_SIZE; i++) {
            hex[i * 2] = "0123456789abcdef"[p[i] >> 4];
            hex[i * 2 + 1] = "0123456789abcdef"[p[i] & 0xF];
        }
        hex[WX_OFF_STK_TASK_SIZE * 2] = 0;
        wsprintfW(path, L"%s\\task_built.hex", CONTROL_DIR);
        write_file_bytes(path, hex, (DWORD)lstrlenA(hex));

        wsprintfW(path, L"%s\\task_built.txt", CONTROL_DIR);
        {
            char info[640];
            wsprintfA(info,
                      "tpl=%d\r\n"
                      "task_block=%p task_body=%p\r\n"
                      "task_size=%d (body %d)\r\n"
                      "ctl_vt_rva=0x%x  expect=0x%x\r\n"
                      "body_vt_rva=0x%x expect_base=0x%x expect_derived=0x%x\r\n"
                      "body+0x08=%p expect(env._Ptr)=%p\r\n"
                      "body+0x10=%p expect(env._Rep)=%p\r\n"
                      "refcount=%p\r\n",
                      tpl_index,
                      (void *)task_block, (void *)task_body,
                      (int)WX_OFF_STK_TASK_SIZE, (int)(WX_OFF_STK_TASK_SIZE - 0x10),
                      (unsigned)((r64((void *)task_block) - base) & 0xFFFFFFFF),
                      (unsigned)WX_OFF_STK_TASK_CTL_VT,
                      (unsigned)((r64((void *)task_body) - base) & 0xFFFFFFFF),
                      (unsigned)WX_OFF_STK_TASK_BASE_VT,
                      (unsigned)WX_OFF_STK_TASK_DERIVED_VT,
                      (void *)r64((void *)(task_body + 0x08)), (void *)r64(env_sp),
                      (void *)r64((void *)(task_body + 0x10)), (void *)r64(env_sp + 8),
                      (void *)r64((void *)(task_block + 8)));
            write_file_bytes(path, info, (DWORD)lstrlenA(info));
        }
    }
    return 1;
}

/* ------------------------------------------------------------------
 * 收藏表情发送 · pack 路线（2026-10-13 18:30，frida 实测确定）
 *
 * 决定性证据（reports/frida_pack_models.txt，用户手动发送收藏表情时抓取）：
 *   窗口线程上 0x160DF80(emoji_ctor) 的内部序列为
 *       0xDB40([rbp+0x140], d1, d2, d3, ...)     任务配置（返回值 = 参数1）
 *       0x160EBE0(container, [rbp+0x140])        pack 投递
 *   container->+0x08/+0x10 是 vector<shared_ptr> 的 begin/end，
 *   元素 _Ptr 的 vtable = 0x82CB8D8 —— **就是信封（Envelope）**。
 *
 * 也就是说文本路径与表情路径在 pack 这一层完全同构：
 *   文本元素 = 文本消息模型（vt 0x805E578，+0xD8 = 1）
 *   表情元素 = 信封        （vt 0x82CB8D8，+0xD8 = 0x2F）
 * 两者其余字段布局一致（+0xB0 wxid / +0xC0 len / +0xC8 cap）。
 * 因此只要把文本路径的 vector 元素换成本模块已能构造的信封即可，
 * 完全绕开 0x16A60D0 / TaskContext / 发送上下文扫描。
 *
 * 返回：1 = 已提交 pack；-1 参数非法；-2 内容对象失败；-3 信封失败；
 *      -4 填字段失败；-5 0xDB40 未返回。
 * 注意：pack 无返回值，能否真正送达只能由「对端是否收到」判定。
 * ------------------------------------------------------------------ */
/* is_pack = 0：收藏表情（wxb_stk_tpl 布局）
 * is_pack = 1：表情包（表情商店添加）表情（wxb_pack_tpl 布局，见 TASK_LOG §29）
 * 两者发送链路完全一致（信封 → pack → 真实任务上下文），只有内容对象构造不同。 */
int wxb_send_sticker_pack_ex(int tpl_index, const char *to_wxid, int is_pack) {
    int64_t base;
    WxbOpNew op_new;
    int64_t content_block = 0;
    int64_t env_block = 0;
    int64_t env_body = 0;
    int64_t result;
    BYTE *arena = NULL;
    BYTE *env_sp = NULL;
    BYTE *container = NULL;
    BYTE *elem = NULL;
    BYTE *cfg = NULL;
    BYTE *d1 = NULL;
    BYTE *d2 = NULL;
    BYTE *d3 = NULL;
    BYTE *d4 = NULL;
    BYTE *d1_data = NULL;   /* d1 的外部数据对象（vtable + 捕获） */
    const SIZE_T ARENA_SIZE = 0x8000;

    if (tpl_index < 0 ||
        tpl_index >= (is_pack ? WXB_PACK_TPL_COUNT : WXB_STK_TPL_COUNT)) return -1;
    if (!to_wxid || !to_wxid[0] || !wxb_weixin_module()) return -1;

    base = (int64_t)wxb_weixin_module();
    op_new = wxb_op_new(base);

    arena = (BYTE *)VirtualAlloc(NULL, ARENA_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!arena) return -1;
    ZeroMemory(arena, ARENA_SIZE);

    env_sp = arena + 0x0000;
    container = arena + 0x0100;
    elem = arena + 0x0200;
    cfg = arena + 0x0400;          /* 0xDB40 输出对象，需 >= 0xE8 字节 */
    d1 = arena + 0x0900;
    d2 = arena + 0x0980;
    d3 = arena + 0x0A00;
    d4 = arena + 0x0A80;
    d1_data = arena + 0x0B00;

    /* ---- 1) 内容对象 ---- */
    content_block = is_pack
        ? wxb_build_content_pack(&g_wxb_pack_tpls[tpl_index], base, op_new)
        : wxb_build_content(&g_wxb_stk_tpls[tpl_index], base, op_new);
    if (!content_block) return -2;

    /* ---- 2) 信封：0x1AFE710(&env_sp) ---- */
    ((FnCall1)(base + WX_OFF_STK_ENV_FACTORY2))((int64_t)env_sp);
    env_block = (int64_t)r64(env_sp + 8);
    env_body = (int64_t)r64(env_sp);
    if (!env_block || env_body != env_block + 0x10) return -3;

    /* ---- 3) 填信封字段（与自然发送一致） ---- */
    w32((void *)(env_body + 0xD8), 0x2F);          /* 收藏表情类型码 */
    if (!wxb_heap_string(env_body + 0xB0, to_wxid, lstrlenA(to_wxid), op_new)) return -4;
    {
        char uuid[37];
        static const char *hx = "0123456789abcdef";
        unsigned long long t = (unsigned long long)GetTickCount64();
        unsigned long long p = (unsigned long long)(uintptr_t)&uuid;
        unsigned long long mix = t * 0x9E3779B97F4A7C15ULL ^ p;
        int i;
        for (i = 0; i < 36; i++) {
            if (i == 8 || i == 13 || i == 18 || i == 23) { uuid[i] = '-'; continue; }
            mix = mix * 6364136223846793005ULL + 1442695040888963407ULL;
            uuid[i] = hx[(mix >> 33) & 0xF];
        }
        uuid[36] = 0;
        if (!wxb_heap_string(env_body + 0x600, uuid, 36, op_new)) return -4;
    }
    w64((void *)(env_body + 0x660), content_block + 0x10);
    w64((void *)(env_body + 0x668), content_block);
    w32((void *)(content_block + 0x08), (int32_t)(r32((void *)(content_block + 0x08)) + 1));

    /* ---- 4) pack 容器：vector<shared_ptr<Envelope>>，1 个元素 ----
     * container+0x08 = begin, container+0x10 = end, 元素 16 字节。 */
    w64((void *)(container + 0x00), 0);
    w64((void *)(container + 0x08), (int64_t)elem);
    w64((void *)(container + 0x10), (int64_t)(elem + 16));
    w64((void *)(container + 0x18), (int64_t)(elem + 16));
    w64((void *)(elem + 0x00), env_body);
    w64((void *)(elem + 0x08), env_block);
    w64((void *)(elem + 0x10), 0);

    /* ---- 5) 三个委托 + 0xDB40 任务配置 ----
     * 必须使用「信封组」委托 vtable（WX_OFF_STK_HC1/2/3）。
     * 早期误用文本组的 0x83661E8/0x8366068/0x8366128：pack 会被正常调用、
     * 信封也会被接受，但消息不会出现在对端 —— 因为委托类型不匹配消息种类。
     * 顺序严格对应 0xDB40 的 rdx / r8 / r9。 */
    w64((void *)d1, base + WX_OFF_STK_HC1);
    w64((void *)(d1 + 56), (int64_t)d1);
    w64((void *)d2, base + WX_OFF_STK_HC2);
    w64((void *)(d2 + 56), (int64_t)d2);
    w64((void *)d3, base + WX_OFF_STK_HC3);
    w64((void *)(d3 + 56), (int64_t)d3);
    (void)d4;

    /* 恢复 d2/d3 的捕获成员。原生形态为 [A, B, A]：
     *   A = vtable 0x8365848 的共享对象（跨消息类型、跨发送不变）→ 运行时扫描定位
     *   B = 0x2d1fa8d8ea0，首 qword 不是合法 vtable，字段类型与持有关系均未定，
     *       且无法从 A 反查（A 内不含该指针），故 +0x10 显式留空。
     * 早期实现把三个槽都写成 A，得到 [A, A, A]，属于错误回填 —— 已修正。 */
    {
        int64_t dcA = 0, dcB = 0;
        wxb_load_delegate_caps(&dcA, &dcB);      /* frida 抓取的真实捕获优先 */
        if (!dcA) dcA = wxb_find_delegate_ctx(base);
        if (dcA) {
            w64((void *)(d2 + 0x08), dcA);
            w64((void *)(d2 + 0x10), dcB);
            w64((void *)(d2 + 0x18), dcA);
            w64((void *)(d3 + 0x08), dcA);
            w64((void *)(d3 + 0x10), dcB);
            w64((void *)(d3 + 0x18), dcA);
        }
        /* d1：必须用【外部存储】。0xDB40 对每个委托都先取 [d+0x38]：
         *   等于自身 → 调 move-ctor（实测 d1 这一类只拷 vtable，捕获会丢）
         *   不等于自身 → 直接把该指针写进 cfg（即外部数据对象）
         * 原生 d1 的 [d+0x38] 指向栈上的数据对象（故其 cfg+0x48 是栈地址），
         * 因此这里改为让 [d1+0x38] 指向我们自备的数据对象，捕获才能真正生效。 */
        if (g_cap_d1_08 || g_cap_d1_18_rva) {
            w64((void *)(d1_data + 0x00), base + WX_OFF_STK_HC1);
            w64((void *)(d1_data + 0x08), g_cap_d1_08);
            w64((void *)(d1_data + 0x10), 0);   /* 原生为栈地址，无法复用 */
            w64((void *)(d1_data + 0x18), base + g_cap_d1_18_rva);
            w64((void *)(d1 + 0x38), (int64_t)d1_data);
        }
    }

    /* ---- 5b) 注入捕获到的真实任务上下文（免点击的关键，TASK_LOG §27） ----
     * 0xDB40 会把 [d4] / [d4+8] 原样搬进 cfg[0] / cfg[8]。d4 本身是 arena 里的
     * 全零块（假上下文），这一步把它替换成 frida 在 pack 入口捕获到的真实
     * shared_ptr<TaskContext>。校验失败则退回空块（只会「发送失败」，不会崩）。 */
    {
        int64_t ctxBody = 0, ctxCtrl = 0;
        if (wxb_load_ctx_override(base, &ctxBody, &ctxCtrl)) {
            w64((void *)d4, ctxBody);
            w64((void *)(d4 + 8), ctxCtrl);
            {
                char msg[192];
                wsprintfA(msg, "ctx override: body=%p ctrl=%p\r\n",
                          (void *)ctxBody, (void *)ctxCtrl);
                tpl_dbg(msg);
            }
        } else {
            tpl_dbg("ctx override: 不可用（缺失/校验失败），退回空上下文\r\n");
        }
    }

    result = ((WxbFn6)(base + WX_OFF_SEND_CALL2))(
        (int64_t)cfg, (int64_t)d1, (int64_t)d2, (int64_t)d3, (int64_t)d4,
        (int64_t)(GetTickCount() & 0xFFFF));
    if (!result) return -5;

    /* ---- 6) pack 投递 ---- */
    /* 在两侧打点：frida 在 pack 内部多点 hook 会互相干扰，DLL 侧的探针更可靠，
     * 可确认 pack 是否真的正常返回（此前"发送失败"但 ok=1 无法区分这一点）。 */
    tpl_dbg("pack: before call\n");
    ((FnCall3)(base + WX_OFF_SEND_CALL3))((int64_t)container, result);
    tpl_dbg("pack: after call (returned)\n");

    /* 微信异步消费这些对象，arena 必须常驻 */
    wxb_retain_send_arena(arena);
    return 1;
}

int wxb_send_sticker_tpl(int tpl_index, const char *to_wxid) {    int64_t base;
    WxbOpNew op_new;
    int64_t content_block = 0;
    int64_t env_block = 0;
    int64_t env_body = 0;
    BYTE *env_sp = NULL;      /* 信封 shared_ptr（16 字节够用） */
    BYTE *out_sp = NULL;      /* 发送输出缓冲 */
    BYTE *arena = NULL;
    /* arena 布局与尺寸：out_sp 必须留足空间。
     * 依据（TASK_LOG 第十五节材料三）：0xDB40 的输出对象会写到 +0xD8，
     * 即至少 0xE8 字节；它并非 16 字节的 shared_ptr 包装。
     * 早先只给 16 字节，若 0x16A60D0 与之同构就会越界写穿 arena，
     * 破坏其后数据 —— 崩在栈上地址处的「坏虚调用目标」很可能由此而来。
     * 现按 0x400 字节预留并整体清零。 */
    const SIZE_T ARENA_SIZE = 0x2000;
    const SIZE_T OUT_SP_SIZE = 0x400;
    int stage = 0;

    if (tpl_index < 0 || tpl_index >= WXB_STK_TPL_COUNT) return -1;
    if (!to_wxid || !wxb_weixin_module()) return -1;

    base = (int64_t)wxb_weixin_module();
    op_new = wxb_op_new(base);

    arena = (BYTE *)VirtualAlloc(NULL, ARENA_SIZE, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!arena) return -1;
    ZeroMemory(arena, ARENA_SIZE);
    env_sp = arena + 0x0000;
    out_sp = arena + 0x0800;

    /* ---- 1) 内容对象 ---- */
    stage = 1;
    wxb_write_status("tpl stage1: build content\n");
    content_block = wxb_build_content(&g_wxb_stk_tpls[tpl_index], base, op_new);
    if (!content_block) { wxb_write_status("tpl stage1 FAILED\n"); return -(stage); }
    wxb_write_status("tpl stage1 ok\n");

    /* ---- 2) 信封：0x1AFE710(&env_sp) ---- */
    stage = 2;
    wxb_write_status("tpl stage2: envelope factory\n");
    ((FnCall1)(base + WX_OFF_STK_ENV_FACTORY2))((int64_t)env_sp);
    env_block = (int64_t)r64(env_sp + 8);      /* _Rep = 控制块 */
    if (!env_block) { wxb_write_status("tpl stage2 FAILED: env_block=0\n"); return -(stage); }
    env_body = (int64_t)r64(env_sp);           /* _Ptr = body = block + 0x10 */
    if (env_body != env_block + 0x10) { wxb_write_status("tpl stage2 FAILED: body!=block+0x10\n"); return -(stage); }
    wxb_write_status("tpl stage2 ok\n");

    /* ---- 3) 填信封字段 ---- */
    stage = 3;
    wxb_write_status("tpl stage3: fill envelope\n");
    w32((void *)(env_body + 0xD8), 0x2F);      /* 收藏表情类型码 */
    if (!wxb_heap_string(env_body + 0xB0, to_wxid, lstrlenA(to_wxid), op_new)) {
        wxb_write_status("tpl stage3 FAILED: wxid string\n"); return -(stage);
    }
    {
        /* UUID：用一个基于时间与地址的确定性 8-4-4-4-12 串，格式合法即可 */
        char uuid[37];
        static const char *hx = "0123456789abcdef";
        unsigned long long t = (unsigned long long)GetTickCount64();
        unsigned long long p = (unsigned long long)(uintptr_t)&uuid;
        unsigned long long mix = t * 0x9E3779B97F4A7C15ULL ^ p;
        int i;
        for (i = 0; i < 36; i++) {
            if (i == 8 || i == 13 || i == 18 || i == 23) { uuid[i] = '-'; continue; }
            mix = mix * 6364136223846793005ULL + 1442695040888963407ULL;
            uuid[i] = hx[(mix >> 33) & 0xF];
        }
        uuid[36] = 0;
        if (!wxb_heap_string(env_body + 0x600, uuid, 36, op_new)) {
            wxb_write_status("tpl stage3 FAILED: uuid string\n"); return -(stage);
        }
    }
    /* 内容对象 shared_ptr：_Ptr = body(block+0x10)，_Rep = block */
    w64((void *)(env_body + 0x660), content_block + 0x10);
    w64((void *)(env_body + 0x668), content_block);
    /* 内容对象引用 +1（信封持有一份） */
    w32((void *)(content_block + 0x08), (int32_t)(r32((void *)(content_block + 0x08)) + 1));
    wxb_write_status("tpl stage3 ok\n");

    /* ---- 4) 发送 ---- */
    stage = 4;
    wxb_write_status("tpl stage4: locating send context\n");
    ZeroMemory(out_sp, OUT_SP_SIZE);
    {
        int64_t ctx = wxb_find_send_ctx(base);
        char msg[160];
        if (!ctx) {
            tpl_dbg("stage4: send context NOT FOUND (scan failed)\r\n");
            wxb_write_status("tpl stage4 FAILED: ctx not found\n");
            return -5;
        }
        wsprintfA(msg, "stage4: ctx=%p  calling 0x16A60D0\r\n", (void *)ctx);
        tpl_dbg(msg);
        /* 0x16A60D0(rcx = ctx, rdx = &out, r8 = &env_sp) */
        ((void (*)(int64_t, int64_t, int64_t))(base + WX_OFF_STK_SEND_ENTRY))(
            ctx, (int64_t)out_sp, (int64_t)env_sp);
    }
    {
        int64_t out_ptr = (int64_t)r64(out_sp);
        int64_t out_rep = (int64_t)r64(out_sp + 8);
        char msg[256];
        wsprintfA(msg, "tpl=%d out.ptr=%p out.rep=%p out.vt=%p env=%p block=%p\r\n",
                  tpl_index, (void *)out_ptr, (void *)out_rep,
                  out_ptr ? (void *)r64((void *)out_ptr) : (void *)0,
                  (void *)env_body, (void *)content_block);
        tpl_dbg(msg);
        if (out_ptr == 0) {
            tpl_dbg("  -> out_ptr NULL: 发送未产出结果对象\r\n");
            wxb_write_status("tpl stage4: out_ptr=NULL\n");
            return -4;
        }
        {
            char hex[200];
            int i;
            for (i = 0; i < 0x30; i++) {
                BYTE b = ((const BYTE *)out_ptr)[i];
                hex[i * 3] = "0123456789abcdef"[b >> 4];
                hex[i * 3 + 1] = "0123456789abcdef"[b & 0xF];
                hex[i * 3 + 2] = (i == 0x2F) ? 0 : ' ';
            }
            hex[0x2F * 3 + 2] = 0;
            tpl_dbg("  out[0..0x30]: ");
            tpl_dbg(hex);
            tpl_dbg("\r\n");
        }
    }
    wxb_write_status("tpl stage4 ok (submitted)\n");

    /* 微信异步消费，arena 必须保活 */
    wxb_retain_send_arena(arena);
    return stage;
}

/* ---- 对外两个入口 ---------------------------------------------------- */

/* 收藏表情（type=8） */
int wxb_send_sticker_pack(int tpl_index, const char *to_wxid) {
    return wxb_send_sticker_pack_ex(tpl_index, to_wxid, 0);
}

/* 表情包（表情商店添加）表情（type=12）。
 * 内容对象按 §29 实测的表情包型布局构造（+0x08=5、slot0=md5、slot1=专辑 ID、
 * slot10=名字），发送链路与收藏表情完全共用。 */
int wxb_send_pack_sticker(int tpl_index, const char *to_wxid) {
    return wxb_send_sticker_pack_ex(tpl_index, to_wxid, 1);
}

int wxb_pack_tpl_count(void) {
    return WXB_PACK_TPL_COUNT;
}

/* ================= pack 入口常驻 hook：自动捕获任务上下文 =================
 *
 * 目的（TASK_LOG §31）：把「上下文需要人工触发一次」降级为「平时任何表情往来都自动捕获」。
 * 用户正常使用微信时本就会有表情的收发，届时上下文自动落盘，无需任何人特意操作。
 *
 * 为什么必须 hook：任务上下文是「每次发送新建、用后即释放」的对象，而它的控制块
 * vtable 0x7F5F398 在一个进程里有 14+ 个同类实例（§29 实测），无法靠扫描区分出来。
 *
 * 为什么只切 6 字节：hook 点 0x160EBE0 的开头是
 *     55 / 41 56 / 56 / 57 / 53 / 48 81 EC ...
 * 前 6 字节恰好是 6 条完整指令，第 7 个字节 48 是 `sub rsp,0x1e0` 的前缀——
 * 按 7 字节切会造出半条指令，跳回去必崩。
 *
 * 为什么回调安全：hook 点在函数最开头，此时除入参寄存器外还没有任何有效状态；
 * 回调只做「读内存 + 写文件」，不构造、不分配、不释放任何微信对象，
 * 且整体被 __try 包住，读异常绝不冒泡到 pack 的调用方。
 */
#define WXB_PACK_HOOK_LEN    6
#define WXB_PACK_TRAMP_SIZE  256

typedef void (*WxbPackProbeFn)(int64_t container, int64_t cfg, int64_t a3, int64_t a4);

static struct {
    volatile LONG installed;
    BYTE *target;
    BYTE *trampoline;
    BYTE original[WXB_PACK_HOOK_LEN];
} g_pack_hook = { 0, NULL, NULL, { 0 } };

/* 无前导零的 64 位十六进制（DLL 侧 strtoull_hex 两种都吃，但省掉前导零更接近
 * frida 侧写出的格式，便于两处产物直接比对）。 */
static void wxb_u64_hex(char *dst, unsigned long long v) {
    static const char *hx = "0123456789abcdef";
    char tmp[17];
    int i, j = 0, start = 0;
    for (i = 0; i < 16; i++) tmp[i] = hx[(v >> ((15 - i) * 4)) & 0xF];
    tmp[16] = 0;
    while (start < 15 && tmp[start] == '0') start++;
    for (i = start; i < 16; i++) dst[j++] = tmp[i];
    dst[j] = 0;
}

/* 把捕获到的上下文落盘成 ctx_override.txt（与 frida 侧同一格式、同一路径） */
static void wxb_save_ctx_override(int64_t body, int64_t ctrl) {
    WCHAR path[MAX_PATH];
    char buf[128];
    char hb[24], hc[24];
    char *p = buf;
    const char *lit;

    if (!wxb_paths_ready()) return;
    wxb_u64_hex(hb, (unsigned long long)body);
    wxb_u64_hex(hc, (unsigned long long)ctrl);

    lit = "BODY="; while (*lit) *p++ = *lit++;
    { const char *q = hb; while (*q) *p++ = *q++; }
    *p++ = '\n';
    lit = "CTRL="; while (*lit) *p++ = *lit++;
    { const char *q = hc; while (*q) *p++ = *q++; }
    *p++ = '\n';
    *p = 0;

    wsprintfW(path, L"%s\\ctx_override.txt", CONTROL_DIR);
    write_file_bytes(path, buf, (DWORD)(p - buf));
}

/* pack 入口回调。签名与 pack 的 x64 调用约定一致：(rcx, rdx, r8, r9)。 */
static void wxb_pack_probe(int64_t container, int64_t cfg, int64_t a3, int64_t a4) {
    int64_t base, model, content, body, ctrl;
    int plus08;
    (void)a3; (void)a4;

    __try {
        base = (int64_t)wxb_weixin_module();
        if (!base || !container || !cfg) return;

        /* container+0x08 = vector begin；元素 16 字节；取第 0 个元素 */
        model = (int64_t)r64((void *)(container + 0x08));
        if (!model) return;
        model = (int64_t)r64((void *)model);
        if (!model) return;
        if (r64((void *)model) != base + WX_STK_ENVELOPE_VTBL) return;   /* 只认表情信封 */

        content = (int64_t)r64((void *)(model + 0x660));
        if (!content) return;
        if (r64((void *)content) != base + WX_OFF_STK_CONTENT_BODY_VT) return;

        plus08 = (int)r32((void *)(content + 0x08));
        if (plus08 != 3 && plus08 != 5) return;   /* 3=收藏表情，5=表情包表情 */

        body = (int64_t)r64((void *)cfg);
        ctrl = (int64_t)r64((void *)(cfg + 8));
        if (!body || !ctrl || body != ctrl + 0x10) return;
        if (r64((void *)ctrl) != base + WX_OFF_STK_TASKCTX_CTRL_VT) return;

        wxb_save_ctx_override(body, ctrl);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        /* 读内存异常一律吞掉：绝不影响 pack 的正常执行 */
    }
}

static int wxb_build_pack_trampoline(BYTE *p, BYTE *target, WxbPackProbeFn handler) {
    BYTE *start = p;
    int i;

    *p++ = 0x9C;                              /* pushfq */
    *p++ = 0x50;                              /* push rax */
    *p++ = 0x51;                              /* push rcx */
    *p++ = 0x52;                              /* push rdx */
    *p++ = 0x41; *p++ = 0x50;                 /* push r8  */
    *p++ = 0x41; *p++ = 0x51;                 /* push r9  */
    *p++ = 0x41; *p++ = 0x52;                 /* push r10 */
    *p++ = 0x41; *p++ = 0x53;                 /* push r11 */
    *p++ = 0x48; *p++ = 0x83; *p++ = 0xEC; *p++ = 0x28;   /* sub rsp,0x28 */
    *p++ = 0x48; *p++ = 0xB8;                 /* mov rax, imm64 */
    *(int64_t *)p = (int64_t)handler; p += 8;
    *p++ = 0xFF; *p++ = 0xD0;                 /* call rax */
    *p++ = 0x48; *p++ = 0x83; *p++ = 0xC4; *p++ = 0x28;   /* add rsp,0x28 */
    *p++ = 0x41; *p++ = 0x5B;                 /* pop r11 */
    *p++ = 0x41; *p++ = 0x5A;                 /* pop r10 */
    *p++ = 0x41; *p++ = 0x59;                 /* pop r9  */
    *p++ = 0x41; *p++ = 0x58;                 /* pop r8  */
    *p++ = 0x5A;                              /* pop rdx */
    *p++ = 0x59;                              /* pop rcx */
    *p++ = 0x58;                              /* pop rax */
    *p++ = 0x9D;                              /* popfq   */

    for (i = 0; i < WXB_PACK_HOOK_LEN; i++) *p++ = g_pack_hook.original[i];

    *p++ = 0x48; *p++ = 0xB8;                 /* mov rax, imm64 */
    *(int64_t *)p = (int64_t)(target + WXB_PACK_HOOK_LEN); p += 8;
    *p++ = 0xFF; *p++ = 0xE0;                 /* jmp rax */

    return (int)(p - start);
}

int wxb_install_pack_hook(void) {
    static const BYTE expected[WXB_PACK_HOOK_LEN] =
        { 0x55, 0x41, 0x56, 0x56, 0x57, 0x53 };
    BYTE patch[WXB_PACK_HOOK_LEN];
    int64_t rel;
    DWORD old = 0;
    int i;

    if (InterlockedCompareExchange(&g_pack_hook.installed, 0, 0)) return 1;
    if (!wxb_weixin_module() || !wxb_paths_ready()) return 0;

    g_pack_hook.target = (BYTE *)((int64_t)wxb_weixin_module() + WX_OFF_SEND_CALL3);
    for (i = 0; i < WXB_PACK_HOOK_LEN; i++) {
        if (g_pack_hook.target[i] != expected[i]) {
            tpl_dbg("pack hook: 站点字节不匹配，放弃安装\n");
            return 0;
        }
    }
    copy_bytes(g_pack_hook.original, g_pack_hook.target, WXB_PACK_HOOK_LEN);

    g_pack_hook.trampoline = (BYTE *)wxb_alloc_near(g_pack_hook.target,
                                                    WXB_PACK_TRAMP_SIZE);
    if (!g_pack_hook.trampoline) return 0;
    {
        int len = wxb_build_pack_trampoline(g_pack_hook.trampoline,
                                            g_pack_hook.target, wxb_pack_probe);
        FlushInstructionCache(GetCurrentProcess(), g_pack_hook.trampoline, (SIZE_T)len);
    }

    rel = (int64_t)g_pack_hook.trampoline - ((int64_t)g_pack_hook.target + 5);
    if (rel < INT32_MIN || rel > INT32_MAX) {
        VirtualFree(g_pack_hook.trampoline, 0, MEM_RELEASE);
        g_pack_hook.trampoline = NULL;
        return 0;
    }
    patch[0] = 0xE9;
    *(int32_t *)(patch + 1) = (int32_t)rel;
    patch[5] = 0x90;
    VirtualProtect(g_pack_hook.target, WXB_PACK_HOOK_LEN, PAGE_EXECUTE_READWRITE, &old);
    copy_bytes(g_pack_hook.target, patch, WXB_PACK_HOOK_LEN);
    VirtualProtect(g_pack_hook.target, WXB_PACK_HOOK_LEN, old, &old);
    FlushInstructionCache(GetCurrentProcess(), g_pack_hook.target, WXB_PACK_HOOK_LEN);
    InterlockedExchange(&g_pack_hook.installed, 1);
    tpl_dbg("pack hook installed: 自动捕获任务上下文已启用\n");
    return 1;
}

void wxb_uninstall_pack_hook(void) {
    DWORD old = 0;
    if (!InterlockedCompareExchange(&g_pack_hook.installed, 0, 0)) return;
    if (!g_pack_hook.target) return;
    VirtualProtect(g_pack_hook.target, WXB_PACK_HOOK_LEN, PAGE_EXECUTE_READWRITE, &old);
    copy_bytes(g_pack_hook.target, g_pack_hook.original, WXB_PACK_HOOK_LEN);
    VirtualProtect(g_pack_hook.target, WXB_PACK_HOOK_LEN, old, &old);
    FlushInstructionCache(GetCurrentProcess(), g_pack_hook.target, WXB_PACK_HOOK_LEN);
    InterlockedExchange(&g_pack_hook.installed, 0);
    if (g_pack_hook.trampoline) VirtualFree(g_pack_hook.trampoline, 0, MEM_RELEASE);
    g_pack_hook.trampoline = NULL;
}

int wxb_pack_hook_installed(void) {
    return InterlockedCompareExchange(&g_pack_hook.installed, 0, 0) != 0;
}
