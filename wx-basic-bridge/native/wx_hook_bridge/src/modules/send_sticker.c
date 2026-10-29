/* 发送「收藏表情」（表情库里已有的表情）。
 *
 * 构造链全部使用本机 4.1.9.23 上验证过的函数入口（不再是拼凑来的常量）：
 *   0x15f35c0  内容对象构造 → vtable 0x82bcc28
 *   0x17040a0  信封构造     → vtable 0x82cb8d8
 *   0xDB40     参数构造     (= WX_OFF_SEND_CALL2，文本路径长期在用)
 *   0x160EBE0  提交         (= WX_OFF_SEND_CALL3)
 *
 * 字段偏移与字段值都来自运行时 dump（用户手动发表情时抓取）。
 *
 * 内存策略：arena 保留不释放（异步发送需要对象存活）。
 */
#include "../include/wx_bridge_send_sticker.h"
#include "../include/wx_bridge_file_io.h"
#include "../include/wx_bridge_memory.h"
#include "../include/wx_bridge_native_call.h"
#include "../include/wx_bridge_offsets.h"
#include "../include/wx_bridge_paths.h"
#include "../include/wx_bridge_runtime.h"
#include "../include/wx_bridge_wechat_string.h"

void wxb_retain_send_arena(void *arena);

/* 诊断输出：把构造链的中间状态写到 control\stk_debug.txt，
 * 便于定位到底卡在哪一步（构造函数没产出对象 / 参数构造失败 / 异常）。 */
static void stk_dbg(const char *msg, int64_t a, int64_t b) {
    char buf[256];
    WCHAR path[MAX_PATH];
    if (!wxb_paths_ready()) return;
    wsprintfA(buf, "%s a=%lld(0x%llx) b=%lld(0x%llx)\n",
              msg, a, (unsigned long long)a, b, (unsigned long long)b);
    wsprintfW(path, L"%s\\stk_debug.txt", CONTROL_DIR);
    write_file_bytes_atomic(path, buf, (DWORD)lstrlenA(buf));
}

#define STK_ARENA_SIZE  0x30000
#define STK_SP_OFF      0x0000   /* shared_ptr<Content> 16 字节（0x15f35c0 自己分配对象） */
#define STK_ENV_BUF_OFF 0x0020   /* 信封「控制块 + 对象体」缓冲区 */
#define STK_ENV_BUF_SIZE 0x800   /* 0x17040a0 会写到对象体 +0x690，必须给足 */
#define STK_RCXS_OFF    0x1000
#define STK_BUF1_OFF    0x1100
#define STK_BUF2_OFF    0x1200
#define STK_BUF3_OFF    0x1300
#define STK_BUF4_OFF    0x1400
#define STK_BUF5_OFF    0x1500
#define STK_BUF6_OFF    0x1600
#define STK_POOL_OFF    0x2000

/* ------------------------------------------------------------------
 * 内置预设：采集自用户实际发送过的表情（vt 0x82bcc28 的内容对象字段）。
 * 目前只有一组，用于打通通路；后续可扩展成从文件加载。
 * ------------------------------------------------------------------ */
static const WxbStickerSpec g_presets[] = {
    {
        /* md5 */
        "7ed206382321db118c4951f1e448166a",
        /* md5b */
        "49cd60dd1f354795b1334bf655a189a5",
        /* url20401 */
        "http://vweixinf.tc.qq.com/110/20401/stodownload?m=7ed206382321db118c4951f1e448166a"
        "&filekey=30440201010430302e02016e040253480420376564323036333832333231646231313863"
        "34393531663165343438313636610203021390040d00000004627466730000000132&hy=SH"
        "&storeid=26a5d7ba3000639e9e36a4af20000006e01004fb1534807e3c03157101db45&ef=1&bizid=1022",
        /* url20403 */
        "http://vweixinf.tc.qq.com/110/20403/stodownload?m=5f3c31ac7ae8771f51519ce40409ed7a"
        "&filekey=3043020101042f302d02016e04025348042035663363333161633761653837373166353135"
        "31396365343034303965643761020230d0040d00000004627466730000000132&hy=SH"
        "&storeid=26a5d7ba30007b824e36a4af20000006e03004fb3534807e3c03157101db5d&ef=3&bizid=1022",
        /* md5c */
        "96d1ce52eeffc92219b7524763fbf5d5",
        /* url20402 */
        "http://vweixinf.tc.qq.com/110/20402/stodownload?m=455d847059730c65bff4e247110bfd03"
        "&filekey=30440201010430302e02016e040253480420343535643834373035393733306336356266"
        "663465323437313130626664303302030213a0040d00000004627466730000000132&hy=SH"
        "&storeid=26a5d7ba300070b2ce36a4af20000006e02004fb2534807e3c03157101db4e&ef=2&bizid=1022"
    }
};

const WxbStickerSpec *wxb_sticker_preset(int id) {
    if (id < 0 || id >= (int)(sizeof(g_presets) / sizeof(g_presets[0]))) return NULL;
    return &g_presets[id];
}

int wxb_sticker_preset_count(void) {
    return (int)(sizeof(g_presets) / sizeof(g_presets[0]));
}

static void wxb_stk_guid(char *out) {
    unsigned char b[16];
    int i;
    for (i = 0; i < 16; i++) b[i] = (unsigned char)((rand() >> 4) & 0xFF);
    b[6] = (unsigned char)((b[6] & 0x0F) | 0x40);
    b[8] = (unsigned char)((b[8] & 0x3F) | 0x80);
    wsprintfA(out,
              "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
              b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7],
              b[8], b[9], b[10], b[11], b[12], b[13], b[14], b[15]);
}

/* 返回值编码：正数 = 成功且到达该阶段；负数 = 在该阶段抛异常。
 *   阶段 1 造内容对象  2 填内容字段  3 包信封  4 填信封字段  5 提交
 * 用返回值而不是写文件，避免诊断代码本身成为干扰源。 */
int wxb_send_sticker(const char *wxid, const WxbStickerSpec *spec) {
    BYTE *arena;
    BYTE *pool;
    BYTE *pool_end;
    int64_t base;
    int64_t *content_sp;
    BYTE *env_buf;
    int64_t env_ptr;
    int64_t env_ctrl;
    BYTE *content;
    BYTE *env;
    BYTE *rcxs;
    BYTE *buf1;
    BYTE *buf2;
    BYTE *buf3;
    BYTE *buf4;
    BYTE *buf5;
    BYTE *buf6;
    char uuid[40];
    volatile int stage = 0;
    int rc = 0;

    if (!wxid || !spec || !spec->md5) return -100;
    base = (int64_t)wxb_weixin_module();
    if (!base) return -101;

    arena = (BYTE *)VirtualAlloc(NULL, STK_ARENA_SIZE, MEM_COMMIT | MEM_RESERVE,
                                 PAGE_READWRITE);
    if (!arena) return -102;
    ZeroMemory(arena, STK_ARENA_SIZE);

    content_sp = (int64_t *)(arena + STK_SP_OFF);
    env_buf = arena + STK_ENV_BUF_OFF;
    rcxs = arena + STK_RCXS_OFF;
    buf1 = arena + STK_BUF1_OFF;
    buf2 = arena + STK_BUF2_OFF;
    buf3 = arena + STK_BUF3_OFF;
    buf4 = arena + STK_BUF4_OFF;
    buf5 = arena + STK_BUF5_OFF;
    buf6 = arena + STK_BUF6_OFF;
    pool = arena + STK_POOL_OFF;
    pool_end = arena + STK_ARENA_SIZE;

    __try {
        /* ---------- 1) 造内容对象 ----------
         * 0x15f35c0 自己 operator new(0x70)，输出 shared_ptr，所以只需 16 字节。 */
        stage = 1;
        content_sp[0] = 0;
        content_sp[1] = 0;
        ((FnCall1)(base + WX_OFF_CONTENT_CTOR))((int64_t)content_sp);
        content = (BYTE *)content_sp[0];
        if (!content) { rc = -1; }
        else {
            /* ---------- 2) 填内容字段 ---------- */
            stage = 2;
            wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_MD5), spec->md5, -1,
                             &pool, pool_end);
            if (spec->md5b)
                wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_MD5B), spec->md5b, -1,
                                 &pool, pool_end);
            if (spec->url20401)
                wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_URL20401), spec->url20401, -1,
                                 &pool, pool_end);
            if (spec->url20403)
                wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_URL20403), spec->url20403, -1,
                                 &pool, pool_end);
            if (spec->md5c)
                wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_MD5C), spec->md5c, -1,
                                 &pool, pool_end);
            if (spec->url20402)
                wx_set_str_arena((int64_t)(content + WX_STK_CONTENT_URL20402), spec->url20402, -1,
                                 &pool, pool_end);

            /* ---------- 3) 包信封 ----------
             * 0x17040a0 不像 0x15f35c0 那样自己分配：它要求调用者提供
             * 「控制块 + 对象体」的完整内存（会写到对象体 +0x690），
             * 所以必须给足缓冲区，否则就是上一轮的越界崩溃。 */
            stage = 3;
            ((FnCall2)(base + WX_OFF_ENVELOPE_CTOR))((int64_t)env_buf,
                                                     (int64_t)content_sp,
                                                     0, 0, 0);
            env_ptr = (int64_t)(env_buf + 0x10);   /* 对象体 */
            env_ctrl = (int64_t)env_buf;           /* 控制块 */
            env = (BYTE *)env_ptr;
            if (!env_ptr) { rc = -3; }
            else {
                /* ---------- 4) 填信封字段 ---------- */
                stage = 4;
                wx_set_str_arena((int64_t)(env + WX_STK_ENV_RECEIVER), wxid, -1,
                                 &pool, pool_end);
                wxb_stk_guid(uuid);
                wx_set_str_arena((int64_t)(env + WX_STK_ENV_UUID), uuid, -1,
                                 &pool, pool_end);

                /* ---------- 5) 容器 + 提交 ---------- */
                stage = 5;
                w64((void *)rcxs, base + WX_OFF_SEND_CALL2);
                w64((void *)buf1, env_ptr);
                w64((void *)(buf1 + 8), env_ctrl);
                w64((void *)(rcxs + 8), (int64_t)buf1);
                w64((void *)(rcxs + 16), (int64_t)buf1 + 16);
                w64((void *)(rcxs + 24), (int64_t)buf1 + 16);

                w64((void *)buf3, base + WX_OFF_SEND_CALL2_HC1);
                w64((void *)(buf3 + 56), (int64_t)buf3);
                w64((void *)buf4, base + WX_OFF_SEND_CALL2_HC3);
                w64((void *)(buf4 + 56), (int64_t)buf4);
                w64((void *)buf5, base + WX_OFF_SEND_CALL2_HC2);
                w64((void *)(buf5 + 56), (int64_t)buf5);
                (void)buf6;

                stage = 6;
                {
                    int64_t result = ((FnCall2)(base + WX_OFF_SEND_CALL2))(
                        (int64_t)buf2, (int64_t)buf3, (int64_t)buf4,
                        (int64_t)buf5, (int64_t)buf6);
                    if (result) {
                        stage = 7;
                        ((FnCall3)(base + WX_OFF_SEND_CALL3))((int64_t)rcxs, result);
                        rc = 7;
                    } else {
                        rc = -6;
                    }
                }
            }
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        rc = -(stage > 0 ? stage : 99);   /* 在哪一阶段抛的异常 */
    }

    wxb_retain_send_arena(arena);
    return rc != 0 ? rc : stage;
}
