#include "../include/wx_bridge_platform.h"

/* 发送落地的 arena 必须常驻：微信会异步消费其中构造的消息模型、信封与字符串。
 *
 * 演进过程（每一步都是被实测逼出来的）：
 *   1) 原实现：16 槽环形，覆盖时直接 VirtualFree 最旧块 —— 高频发送会在微信
 *      读完之前把内存还掉（评审指出的所有权缺口，成立）。
 *   2) 一度改为"年龄 > 30s 才释放" —— 这仍是权宜：块年龄并不能证明异步任务
 *      已经完成（评审再次指正，成立）。
 *   3) 现版本：256 槽；只有当槽内旧块年龄超过 RETIRE_MS 才释放；否则放弃追踪
 *      而不释放。阈值放大到 5 分钟，使"仍在异步使用"的窗口几乎不可能被命中。
 *
 * 仍未闭合：这依然是"用时间近似完成信号"，而不是真正的引用计数/完成回调。
 * 要彻底闭合，应改为让微信自己的堆持有这些对象（构造时即用其 operator new
 * 分配对象体），或挂到发送结果回调上，二者都需要先恢复发送链的完整契约。 */
#define RETAINED_ARENAS 256
#define RETIRE_MS       300000

static void *g_arenas[RETAINED_ARENAS] = {0};
static DWORD g_ticks[RETAINED_ARENAS] = {0};
static int g_arena_index = 0;

void wxb_retain_send_arena(void *arena) {
    DWORD now;
    if (!arena) return;
    now = GetTickCount();
    if (g_arenas[g_arena_index] && (DWORD)(now - g_ticks[g_arena_index]) > RETIRE_MS) {
        VirtualFree(g_arenas[g_arena_index], 0, MEM_RELEASE);
        g_arenas[g_arena_index] = NULL;
    }
    /* 若旧块仍年轻：直接覆盖槽位记录（旧块不再被追踪，但绝不释放）。 */
    g_arenas[g_arena_index] = arena;
    g_ticks[g_arena_index] = now;
    g_arena_index = (g_arena_index + 1) % RETAINED_ARENAS;
}
