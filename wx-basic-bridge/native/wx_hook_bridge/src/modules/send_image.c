/* 发送本地图片文件（第二版）。
 *
 * 第一版直接照搬 aixed 的整组 offset，结果崩在 Weixin.dll+0xdf79 —— 因为
 * 那组 offset 属于 4.1.10.27，在本机 4.1.9.23 上 create_param2/txt_message_ctr/
 * dec_pic_call/send_message 全都不是函数入口（只落在函数中间）。
 *
 * 本版策略：只保留「与版本无关的数据布局」，函数地址一律改用我们自己已验证的：
 *   构造器  0xDB40      (= WX_OFF_SEND_CALL2，send_text.c 正在用，文本收发长期稳定)
 *   提交    0x160EBE0   (= WX_OFF_SEND_CALL3，且实测它也会被图片/表情消息触发)
 *   委托vtable 0x83661E8 / 0x8366068 / 0x8366128 (WX_OFF_SEND_CALL2_HC1/2/3)
 *
 * 消息体的字段布局沿用 aixed 那份（vtable/img_msg_vtb2 两个地址在两版通用，
 * 已在本机核对为有效 vtable）：
 *   msg[0]=img_msg_vtbl  msg[1]=0x200000006  msg[2]=img_msg_vtb2
 *   wxid@0xC0(ASCII串)  filetype@0xE8  path@0xF0(宽串)  size@0x198  guid@0x6B8
 *
 * 内存策略：全部走进程堆且不释放（异步发送需要对象存活）。
 */
#include "../include/wx_bridge_send_image.h"
#include "../include/wx_bridge_memory.h"
#include "../include/wx_bridge_native_call.h"
#include "../include/wx_bridge_offsets.h"
#include "../include/wx_bridge_runtime.h"

#define IMG_ARENA_SIZE  0x30000
#define IMG_MSG_OFF     0x0000
#define IMG_RCXS_OFF    0x1000
#define IMG_BUF1_OFF    0x1100
#define IMG_BUF2_OFF    0x1200
#define IMG_BUF3_OFF    0x1300
#define IMG_BUF4_OFF    0x1400
#define IMG_BUF5_OFF    0x1500
#define IMG_BUF6_OFF    0x1600
#define IMG_MSG_SIZE    0x7C0

/* 微信的 32 字节字符串 */
typedef struct {
    union { char inline_buf[16]; char *heap_buf; } u;
    uint64_t length;
    uint64_t cap;
} wxb_wx_str;

typedef struct {
    union { wchar_t inline_buf[8]; wchar_t *heap_buf; } u;
    uint64_t length;
    uint64_t cap;
} wxb_wx_str_u;

void wxb_retain_send_arena(void *arena);

static uint64_t wxb_calc_cap(uint64_t len) {
    uint64_t need = len + 1;
    uint64_t cap = (need + 0xF) & ~(uint64_t)0xF;
    return cap - 1;
}

static void *wxb_heap_alloc(SIZE_T size) {
    return HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, size);
}

/* ASCII 字符串写入微信字符串结构（池分配，池耗尽则回退到堆） */
static void wxb_set_wx_str_pool(void *raw, const char *src,
                                BYTE **pool, BYTE *pool_end) {
    wxb_wx_str *dst = (wxb_wx_str *)raw;
    size_t n;
    ZeroMemory(dst, sizeof(wxb_wx_str));
    if (!src) return;
    n = (size_t)lstrlenA(src);
    dst->length = (uint64_t)n;
    if (n < 16) {
        CopyMemory(dst->u.inline_buf, src, n);
        dst->cap = 0xF;
        return;
    }
    {
        char *buf;
        if (*pool && (*pool + n + 1) < pool_end) {
            buf = (char *)(*pool);
            *pool += n + 16;
        } else {
            buf = (char *)wxb_heap_alloc(n + 1);
            if (!buf) return;
        }
        CopyMemory(buf, src, n);
        buf[n] = 0;
        dst->u.heap_buf = buf;
        dst->cap = wxb_calc_cap((uint64_t)n);
    }
}

/* UTF-8 → 宽字符串，写入微信宽字符串结构 */
static void wxb_set_wx_str_u_pool(void *raw, const char *utf8,
                                  BYTE **pool, BYTE *pool_end) {
    wxb_wx_str_u *dst = (wxb_wx_str_u *)raw;
    int need;
    size_t wlen;
    wchar_t *wbuf;
    ZeroMemory(dst, sizeof(wxb_wx_str_u));
    if (!utf8) return;
    need = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, NULL, 0);
    if (need <= 0) return;
    wlen = (size_t)(need - 1);
    dst->length = (uint64_t)wlen;
    if (wlen < 8) {
        wchar_t tmp[8];
        MultiByteToWideChar(CP_UTF8, 0, utf8, -1, tmp, 8);
        CopyMemory(dst->u.inline_buf, tmp, wlen * sizeof(wchar_t));
        dst->u.inline_buf[wlen] = 0;
        dst->cap = 0xF;
        return;
    }
    if (*pool && (*pool + wlen * sizeof(wchar_t) + 2) < pool_end) {
        wbuf = (wchar_t *)(*pool);
        *pool += wlen * sizeof(wchar_t) + 16;
    } else {
        wbuf = (wchar_t *)wxb_heap_alloc((SIZE_T)need * sizeof(wchar_t));
        if (!wbuf) return;
    }
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, wbuf, need);
    dst->u.heap_buf = wbuf;
    dst->cap = wxb_calc_cap((uint64_t)wlen);
}

static void wxb_gen_guid(char *out) {
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

static uint64_t wxb_file_size(const char *utf8_path) {
    wchar_t wpath[1024];
    WIN32_FILE_ATTRIBUTE_DATA fad;
    if (MultiByteToWideChar(CP_UTF8, 0, utf8_path, -1, wpath, 1024) <= 0) return 0;
    if (!GetFileAttributesExW(wpath, GetFileExInfoStandard, &fad)) return 0;
    if (fad.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) return 0;
    return ((uint64_t)fad.nFileSizeHigh << 32) | (uint64_t)fad.nFileSizeLow;
}

int wxb_send_image_ex(const char *wxid, const char *img_path, int file_type) {
    const SIZE_T arena_size = IMG_ARENA_SIZE;
    BYTE *arena;
    BYTE *pool;
    BYTE *pool_end;
    int64_t base;
    BYTE *msg;
    BYTE *rcxs;
    BYTE *buf1;
    BYTE *buf2;
    BYTE *buf3;
    BYTE *buf4;
    BYTE *buf5;
    BYTE *buf6;
    char guid[40];
    uint64_t file_size;
    int wxid_len;
    int ok = 0;

    if (!wxid || !img_path || !img_path[0]) return 0;
    base = (int64_t)wxb_weixin_module();
    if (!base) return 0;

    file_size = wxb_file_size(img_path);
    if (!file_size) return 0;
    wxid_len = lstrlenA(wxid);

    arena = (BYTE *)VirtualAlloc(NULL, arena_size, MEM_COMMIT | MEM_RESERVE,
                                 PAGE_READWRITE);
    if (!arena) return 0;
    ZeroMemory(arena, arena_size);

    msg = arena + IMG_MSG_OFF;
    rcxs = arena + IMG_RCXS_OFF;
    buf1 = arena + IMG_BUF1_OFF;
    buf2 = arena + IMG_BUF2_OFF;
    buf3 = arena + IMG_BUF3_OFF;
    buf4 = arena + IMG_BUF4_OFF;
    buf5 = arena + IMG_BUF5_OFF;
    buf6 = arena + IMG_BUF6_OFF;
    pool = arena + 0x2000;
    pool_end = arena + arena_size;

    __try {
        wxb_gen_guid(guid);

        /* ---------- 1) 图片消息结构（字段布局来自 aixed，纯数据偏移） ---------- */
        w64(msg + 0x000, base + WX_OFF_IMG_MSG_VTBL);
        w64(msg + 0x008, 0x200000006LL);
        w64(msg + 0x010, base + WX_OFF_IMG_MSG_VTB2);

        w64(msg + 0x040, 0xF);
        w64(msg + 0x060, 0xF);
        w64(msg + 0x080, 0xF);
        w64(msg + 0x0A0, 0xF);
        w64(msg + 0x0A8, 0x0000000100000000LL);
        w64(msg + 0x0B0, 0x0000000700000000LL);

        /* 接收方 */
        wxb_set_wx_str_pool(msg + WX_IMG_OFF_RECEIVER, wxid, &pool, pool_end);
        w64(msg + 0x0D0, (int64_t)wxid_len);
        w64(msg + 0x0D8, (int64_t)wxb_calc_cap((uint64_t)wxid_len));

        /* 文件类型 */
        w64(msg + WX_IMG_OFF_FILETYPE, (int64_t)file_type);

        /* 本地路径（宽字符） */
        wxb_set_wx_str_u_pool(msg + WX_IMG_OFF_PATH, img_path, &pool, pool_end);
        w64(msg + 0x100, (int64_t)lstrlenA(img_path));
        w64(msg + 0x108, (int64_t)wxb_calc_cap((uint64_t)lstrlenA(img_path)));

        w64(msg + 0x130, 0xF);
        w64(msg + 0x150, 7);
        w64(msg + 0x170, 0xF);
        w64(msg + WX_IMG_OFF_FILESIZE, (int64_t)file_size);
        w64(msg + 0x1B8, 0xF);

        w64(msg + 0x668, 0xF);
        w64(msg + 0x688, 0xF);
        w64(msg + 0x6B0, 0xF);

        wxb_set_wx_str_pool(msg + WX_IMG_OFF_GUID, guid, &pool, pool_end);
        w64(msg + 0x6C8, (int64_t)lstrlenA(guid));
        w64(msg + 0x6D0, (int64_t)wxb_calc_cap((uint64_t)lstrlenA(guid)));

        w64(msg + 0x6F0, 0xF);
        w64(msg + 0x710, 0xF);
        w64(msg + 0x738, 0xF);
        w64(msg + 0x760, 0xF);
        w64(msg + 0x780, 0xF);
        w64(msg + 0x7A0, 0xF);

        /* ---------- 2) 容器 rcxs（照 send_text.c 的结构） ----------
         * buf1 是"伪 shared_ptr<消息>": {子对象, 控制块}。
         * 文本路径里控制块之所以有效，是因为它先做过 msg+0x18 = msg+0x10；
         * 而图片布局没有那个字段，必须直接写 msg+0x10，
         * 否则 buf1[1] 为 NULL，提交时消息会被忽略（表现为 ok 但发不出去）。 */
        w64((void *)rcxs, base + WX_OFF_SEND_CALL2);
        w64((void *)buf1, (int64_t)(msg + 0x10));
        w64((void *)(buf1 + 8), (int64_t)(msg + 0x10));
        w64((void *)(rcxs + 8), (int64_t)buf1);
        w64((void *)(rcxs + 16), (int64_t)buf1 + 16);
        w64((void *)(rcxs + 24), (int64_t)buf1 + 16);

        /* 三个委托对象 */
        w64((void *)buf3, base + WX_OFF_SEND_CALL2_HC1);
        w64((void *)(buf3 + 56), (int64_t)buf3);
        w64((void *)buf4, base + WX_OFF_SEND_CALL2_HC3);
        w64((void *)(buf4 + 56), (int64_t)buf4);
        w64((void *)buf5, base + WX_OFF_SEND_CALL2_HC2);
        w64((void *)(buf5 + 56), (int64_t)buf5);
        (void)buf6;

        /* ---------- 3) 构造 + 提交（全部使用本机已验证地址） ---------- */
        {
            int64_t result = ((FnCall2)(base + WX_OFF_SEND_CALL2))(
                (int64_t)buf2, (int64_t)buf3, (int64_t)buf4,
                (int64_t)buf5, (int64_t)buf6);
            if (result) {
                ((FnCall3)(base + WX_OFF_SEND_CALL3))((int64_t)rcxs, result);
                ok = 1;
            }
        }
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        ok = 0;
    }

    /* 异步发送，保留 arena */
    wxb_retain_send_arena(arena);
    return ok;
}

int wxb_send_image(const char *wxid, const char *img_path) {
    return wxb_send_image_ex(wxid, img_path, 3);
}
