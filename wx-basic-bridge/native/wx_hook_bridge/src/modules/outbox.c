#include "../include/wx_bridge_outbox.h"
#include "../include/wx_bridge_file_io.h"
#include "../include/wx_bridge_paths.h"
#include "../include/wx_bridge_protocol.h"
#include "../include/wx_bridge_send_image.h"
#include "../include/wx_bridge_send_sticker.h"
#include "../include/wx_bridge_send_sticker_tpl.h"
#include "../include/wx_bridge_send_text.h"
#include "../include/wx_bridge_runtime.h"
#include "../include/wx_bridge_text.h"

static volatile LONG g_processing = 0;

static char *next_field(char **cursor) {
    char *field;
    if (!cursor || !*cursor) return NULL;
    field = *cursor;
    while (**cursor && **cursor != '\t' && **cursor != '\r' && **cursor != '\n') (*cursor)++;
    if (**cursor == '\t') {
        **cursor = 0;
        (*cursor)++;
    } else if (**cursor) {
        **cursor = 0;
        (*cursor)++;
    }
    return field;
}

void wxb_poll_outbox(void) {
    char data[65536];
    char *cursor;
    char *seq;
    char *type;
    char *to;
    char *content;
    int n;
    int ok;

    if (InterlockedCompareExchange(&g_processing, 1, 0) != 0) return;
    n = read_file_bytes(OUTBOX_FILE, data, sizeof(data));
    if (n <= 0) {
        InterlockedExchange(&g_processing, 0);
        return;
    }
    /* 容忍 UTF-8 BOM：PowerShell 的 `Set-Content -Encoding UTF8`（PS 5.1）会写入
     * EF BB BF 三个字节。若不过滤，BOM 会粘进第一个字段 seq，于是
     * write_result 用 "result_<BOM>1791….json" 去落盘 —— 命令照常执行、
     * status.txt 也正常，但 result_*.json 静默不出现（2026-10-14 实测踩到）。
     * Python 的 open(..., encoding="utf-8") / Path.write_text 默认不带 BOM，
     * 所以既有调用方（frida 脚本、feizhi_pc/bridge.py）不受影响。 */
    cursor = data;
    if (n >= 3 && (unsigned char)cursor[0] == 0xEF &&
        (unsigned char)cursor[1] == 0xBB && (unsigned char)cursor[2] == 0xBF) {
        cursor += 3;
    }
    seq = next_field(&cursor);
    type = next_field(&cursor);
    to = next_field(&cursor);
    content = cursor;
    trim_trailing_crlf(content);

    /* 诊断：记录执行前后 worker 线程的 TLS 服务状态。
     * 目的：验证 [tls+0x1F0] 是否由发送路径懒加载 —— 若 post 变成非 0，
     * 说明服务是被我们调用的构造/提交链初始化出来的，TaskContext 路线仍然可行。 */
    wxb_write_tls_report("pre_exec", GetCurrentThreadId());

    if (!seq || !type || !to || !content || !seq[0]) {
        write_status("malformed outbox command\n");
        if (seq) write_result(seq, 0, "unknown", "malformed outbox command");
    } else if (str_eq(type, "1")) {
        ok = send_text(to, content);
        write_status(ok ? "send_text ok\n" : "send_text failed\n");
        write_result(seq, ok, "send_text", ok ? "send_text ok" : "send_text failed");
    } else if (str_eq(type, "2")) {
        /* type=2 图片：实验性，暂不启用。
         * 微信 4.1.9.23 的图片消息体构造入口未定位（aixed 的 0x1677A30/
         * create_param2 等属于 4.1.10.27，本机全都不是函数入口，实测会崩进程），
         * 为避免误触发导致微信退出，这里直接拒绝。 */
        write_status("send_image disabled (offset not validated for 4.1.9.23)\n");
        write_result(seq, 0, "send_image", "disabled: offset not validated on this version");
    } else if (str_eq(type, "3")) {
        /* type=3 收藏表情。content 为预设编号（十进制）。
         * 返回值是阶段号：7=全部完成；1..5=卡在该阶段；负数=该阶段抛异常。 */
        int preset_id = 0;
        const char *p = content;
        const WxbStickerSpec *spec;
        char msg[96];
        int rc;
        while (*p >= '0' && *p <= '9') {
            preset_id = preset_id * 10 + (*p - '0');
            p++;
        }
        spec = wxb_sticker_preset(preset_id);
        if (!spec) {
            write_status("sticker preset not found\n");
            write_result(seq, 0, "send_sticker", "preset not found");
        } else {
            rc = wxb_send_sticker(to, spec);
            wsprintfA(msg, rc == 7 ? "send_sticker ok (stage=%d)" : "stage=%d", rc);
            write_status(rc == 7 ? "send_sticker ok\n" : msg);
            write_result(seq, rc == 7, "send_sticker", msg);
        }
    } else if (str_eq(type, "4")) {
        /* type=4 收藏表情（模板路径）。content 为模板序号（十进制，0 起）。
         * 返回：4=已提交发送；1..3=卡在该阶段；负数=该阶段失败。
         * 与 type=3 的区别：type=3 走旧的 0x15F35C0/0x17040A0 链（已知失效），
         * type=4 走实测有效的 0x1AFE710 信封 + 0x16D4450 发送。 */
        int idx = 0;
        const char *p = content;
        char msg[128];
        int rc;
        while (*p >= '0' && *p <= '9') {
            idx = idx * 10 + (*p - '0');
            p++;
        }
        rc = wxb_send_sticker_tpl(idx, to);
        if (rc == 4) {
            wsprintfA(msg, "send_sticker_tpl ok (tpl=%d)", idx);
            write_status("send_sticker_tpl ok\n");
            write_result(seq, 1, "send_sticker_tpl", msg);
        } else {
            wsprintfA(msg, "send_sticker_tpl stage=%d (tpl=%d)", rc, idx);
            write_status("send_sticker_tpl failed\n");
            write_result(seq, 0, "send_sticker_tpl", msg);
        }
    } else if (str_eq(type, "5")) {
        /* type=5 只构造内容对象并 dump，不发送（零风险，供离线核验构造结果）。
         * content 为模板序号。 */
        int idx = 0;
        const char *p = content;
        char msg[128];
        int rc;
        while (*p >= '0' && *p <= '9') {
            idx = idx * 10 + (*p - '0');
            p++;
        }
        rc = wxb_dump_content_tpl(idx);
        if (rc == 1) {
            wsprintfA(msg, "content dumped (tpl=%d)", idx);
            write_status("dump_content ok\n");
            write_result(seq, 1, "dump_content", msg);
        } else {
            wsprintfA(msg, "dump failed rc=%d (tpl=%d)", rc, idx);
            write_status("dump_content failed\n");
            write_result(seq, 0, "dump_content", msg);
        }
    } else if (str_eq(type, "6")) {
        /* type=6 构造「内容对象 → 信封 → TaskContext」全链并 dump，不发送（零风险）。 */
        int idx = 0;
        const char *p = content;
        char msg[128];
        int rc;
        while (*p >= '0' && *p <= '9') {
            idx = idx * 10 + (*p - '0');
            p++;
        }
        rc = wxb_dump_task_tpl(idx);
        if (rc == 1) {
            wsprintfA(msg, "task dumped (tpl=%d)", idx);
            write_status("dump_task ok\n");
            write_result(seq, 1, "dump_task", msg);
        } else {
            wsprintfA(msg, "dump_task failed rc=%d (tpl=%d)", rc, idx);
            write_status("dump_task failed\n");
            write_result(seq, 0, "dump_task", msg);
        }
    } else if (str_eq(type, "8")) {
        /* type=8 收藏表情（pack 路线，frida 实证的主流路径）。
         * content = 模板序号（十进制）；to = 接收方 wxid。 */
        int idx = 0;
        const char *p = content;
        char msg[128];
        int rc;
        while (*p >= '0' && *p <= '9') {
            idx = idx * 10 + (*p - '0');
            p++;
        }
        rc = wxb_send_sticker_pack(idx, to);
        if (rc == 1) {
            wsprintfA(msg, "sticker_pack submitted (tpl=%d)", idx);
            write_status("sticker_pack submitted\n");
            write_result(seq, 1, "sticker_pack", msg);
        } else {
            wsprintfA(msg, "sticker_pack failed rc=%d (tpl=%d)", rc, idx);
            write_status("sticker_pack failed\n");
            write_result(seq, 0, "sticker_pack", msg);
        }
    } else if (str_eq(type, "12")) {
        /* type=12 表情包（表情商店添加）表情。
         * 与 type=8 的唯一区别是内容对象布局（TASK_LOG §29）：
         *   body+0x08 = 5、slot0 = 该表情 md5、slot1 = 专辑 ID、slot10 = 名字；
         * 发送链路（信封 → pack → 真实任务上下文）完全共用。 */
        int idx = 0;
        const char *p = content;
        char msg[128];
        int rc;
        while (*p >= '0' && *p <= '9') {
            idx = idx * 10 + (*p - '0');
            p++;
        }
        rc = wxb_send_pack_sticker(idx, to);
        if (rc == 1) {
            wsprintfA(msg, "pack_sticker submitted (tpl=%d)", idx);
            write_status("pack_sticker submitted\n");
            write_result(seq, 1, "pack_sticker", msg);
        } else {
            wsprintfA(msg, "pack_sticker failed rc=%d (tpl=%d)", rc, idx);
            write_status("pack_sticker failed\n");
            write_result(seq, 0, "pack_sticker", msg);
        }
    } else if (str_eq(type, "9")) {
        /* type=9 以「自定义类型码的消息模型」发送 content。
         * content 格式：<type_code>\t<payload>；缺省 type_code = 47（收藏表情）。
         * 走的是已验证可用的文本同构通道，用于试探 XML 投递是否可行。 */
        int tc = 0;
        const char *p = content;
        char msg[160];
        const char *tab;
        while (*p >= '0' && *p <= '9') { tc = tc * 10 + (*p - '0'); p++; }
        if (*p == '\t') {
            p++;
        } else {
            tc = 47;
            p = content;
        }
        tab = p;
        ok = wxb_send_model(to, tab, tc);
        wsprintfA(msg, "send_model type=%d ok=%d", tc, ok);
        write_status(ok ? "send_model ok\n" : "send_model failed\n");
        write_result(seq, ok, "send_model", msg);
    } else if (str_eq(type, "11")) {
        /* type=11 图片模型（类型码可配）：content = "<type_code>\t<path>"，
         * 缺省 type_code = 3。用于试探 type=47 是否走"动画表情"处理。 */
        int tc = 0;
        const char *p = content;
        while (*p >= '0' && *p <= '9') { tc = tc * 10 + (*p - '0'); p++; }
        if (*p == '\t') p++; else { tc = 3; p = content; }
        ok = wxb_send_image_model_ex(to, p, tc, 1);
        write_status(ok ? "send_image_model_ex ok\n" : "send_image_model_ex failed\n");
        write_result(seq, ok, "send_image_model_ex",
                     ok ? "submitted" : "failed");
    } else if (str_eq(type, "10")) {
        /* type=10 图片消息：content = 本地图片路径（UTF-8）。
         * 使用 frida 实测的图片模型布局，走 pack 通道。 */
        ok = wxb_send_image_model(to, content);
        write_status(ok ? "send_image_model ok\n" : "send_image_model failed\n");
        write_result(seq, ok, "send_image_model",
                     ok ? "image model submitted" : "image model failed");
    } else if (str_eq(type, "7")) {
        /* type=7 重新枚举进程内所有线程的 TLS 服务状态（诊断用，零风险）。 */
        wxb_scan_threads_tls();
        write_status("tls scan done\n");
        write_result(seq, 1, "scan_tls", "tls_threads.txt rewritten");
    } else {
        write_status("unsupported msg type\n");
        write_result(seq, 0, "unknown",
                     "supported types: 1=text 3=sticker(legacy) 4=sticker_template 5=dump_content 6=dump_task");
    }
    wxb_write_tls_report("post_exec", GetCurrentThreadId());
    write_file_bytes_atomic(OUTBOX_FILE, "", 0);
    InterlockedExchange(&g_processing, 0);
}
