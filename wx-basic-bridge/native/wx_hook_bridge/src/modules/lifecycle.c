#include "../include/wx_bridge_file_io.h"
#include "../include/wx_bridge_outbox.h"
#include "../include/wx_bridge_owner.h"
#include "../include/wx_bridge_paths.h"
#include "../include/wx_bridge_protocol.h"
#include "../include/wx_bridge_receive.h"
#include "../include/wx_bridge_runtime.h"
#include "../include/wx_bridge_send_sticker_tpl.h"
#include "../include/wx_bridge_text.h"
#include <tlhelp32.h>

static volatile LONG g_worker_active = 0;

/* ------------------------------------------------------------------
 * 消息通道（线程调度架构改造 · 第 1 阶段：只验证通道，不迁业务）
 *
 * 背景（外部评审）：
 *   wechat_inject.py 的 SetWindowsHookExW 只在「远程 LoadLibrary 失败」时才执行，
 *   且是在【注入器进程内】调用 —— 所以默认注入路径下 bridge 根本没有消息 hook，
 *   唯一的命令消费者是自建的 worker 线程，而这个线程缺少微信的 TLS 服务对象
 *   （0x39B8F0 依赖 gs:[0x58] -> TLS -> [+0x1f0]），导致依赖微信线程服务的
 *   原生构造/调用一律崩溃。
 *
 * 本阶段目标：让 DLL 自己建立并持有 WH_GETMESSAGE hook，并记录
 *   1) 目标窗口 HWND / 其创建线程 TID
 *   2) 每次回调的真实 TID 与累计次数
 * 以便确认「命令消费线程已就绪」——按评审要求，ready 必须由实际回调确认，
 * 不能只看 worker started。
 *
 * 注意：WH_GETMESSAGE 不受 LowLevelHooksTimeout 约束（那是低级键鼠 hook 的规则），
 *       但仍应保持回调轻量，以免阻塞微信消息泵。
 * ------------------------------------------------------------------ */
static HHOOK g_msg_hook = NULL;
static HWND g_weixin_hwnd = NULL;
static DWORD g_weixin_tid = 0;
static volatile LONG g_hook_callback_count = 0;
static volatile LONG g_hook_last_tid = 0;
static volatile LONG g_wake_count = 0;

typedef struct {
    DWORD pid;
    HWND best;
    DWORD best_area;
} FindWinCtx;

/* 定义在本文件后部（导出函数），此处前向声明供 install_msg_hook 使用 */
__declspec(dllexport) LRESULT CALLBACK WxGetMsgHook(int code, WPARAM wparam, LPARAM lparam);

static BOOL CALLBACK find_weixin_window_proc(HWND hwnd, LPARAM lparam) {
    FindWinCtx *ctx = (FindWinCtx *)lparam;
    DWORD pid = 0;
    RECT rc;
    DWORD area;

    GetWindowThreadProcessId(hwnd, &pid);
    if (pid != ctx->pid) return TRUE;
    if (!IsWindowVisible(hwnd)) return TRUE;
    if (GetWindow(hwnd, GW_OWNER) != NULL) return TRUE;   /* 跳过子/弹出窗口 */
    if (!GetWindowRect(hwnd, &rc)) return TRUE;
    area = (DWORD)((rc.right - rc.left) * (rc.bottom - rc.top));
    if (area > ctx->best_area) {
        ctx->best_area = area;
        ctx->best = hwnd;
    }
    return TRUE;
}

/* 找到本进程内「面积最大的可见顶层窗口」作为微信主窗口，
 * 并返回其创建线程 TID（注意：PostMessage 投递到窗口创建线程的消息队列）。 */
static int locate_weixin_window(void) {
    FindWinCtx ctx;
    ctx.pid = GetCurrentProcessId();
    ctx.best = NULL;
    ctx.best_area = 0;
    EnumWindows(find_weixin_window_proc, (LPARAM)&ctx);
    if (!ctx.best) return 0;
    g_weixin_hwnd = ctx.best;
    g_weixin_tid = GetWindowThreadProcessId(g_weixin_hwnd, NULL);
    return g_weixin_tid != 0;
}

static void write_channel_status(const char *phase) {
    WCHAR path[MAX_PATH];
    char info[512];
    if (!wxb_paths_ready()) return;
    wsprintfW(path, L"%s\\channel.txt", CONTROL_DIR);
    wsprintfA(info,
              "phase=%s\r\n"
              "hooked=%d\r\n"
              "hwnd=%p\r\n"
              "window_tid=%lu\r\n"
              "self_tid=%lu\r\n"
              "callbacks=%ld\r\n"
              "last_callback_tid=%ld\r\n"
              "wakes=%ld\r\n",
              phase,
              g_msg_hook ? 1 : 0,
              (void *)g_weixin_hwnd,
              (unsigned long)g_weixin_tid,
              (unsigned long)GetCurrentThreadId(),
              (long)g_hook_callback_count,
              (long)g_hook_last_tid,
              (long)g_wake_count);
    write_file_bytes(path, info, (DWORD)lstrlenA(info));
}

/* 由 DLL 自己安装消息 hook（宿主为本模块，与 bridge 同寿命） */
static int install_msg_hook(void) {
    HINSTANCE inst;
    if (g_msg_hook) return 1;
    if (!locate_weixin_window()) {
        write_channel_status("window_not_found");
        return 0;
    }
    inst = wxb_bridge_instance();
    if (!inst) {
        write_channel_status("no_module_instance");
        return 0;
    }
    g_msg_hook = SetWindowsHookExW(WH_GETMESSAGE, WxGetMsgHook, inst, g_weixin_tid);
    if (!g_msg_hook) {
        write_channel_status("hook_failed");
        return 0;
    }
    write_channel_status("hook_installed");
    return 1;
}

/* 唤醒目标消息线程：向其窗口投一条 WM_NULL 作为探针/唤醒。
 * 注意 PostMessage 成功只代表入队，不代表 hook 已回调。 */
static int wake_msg_thread(void) {
    if (!g_weixin_hwnd) return 0;
    if (!PostMessageW(g_weixin_hwnd, WM_NULL, 0, 0)) {
        return 0;
    }
    InterlockedIncrement(&g_wake_count);
    return 1;
}

/* ------------------------------------------------------------------
 * TLS 服务探测（架构改造第 2 阶段：验证哪个线程具备微信业务服务）
 *
 * 依据 0x39B8F0 的实现：
 *     mov eax, [rip+0xa1952a4]        ; TLS 索引（槽位在 base+0xA530BA0）
 *     mov rdx, gs:[0x58]              ; TEB -> ThreadLocalStoragePointer
 *     mov rax, [rdx + rax*8]
 *     mov rdx, [rax + 0x1f0]          ; ★ 业务服务对象
 * 该函数被 143 处调用，且在没有服务时会走清理分支并读 [0+0x388] 崩溃。
 *
 * 本函数只【读】不做任何调用，因此可用于安全地对比各线程：
 *   - 自然发送线程（未捕获）
 *   - 自建 worker 线程
 *   - WxGetMsgHook 回调线程
 * 若回调线程的 +0x1F0 非空，则该线程可用于执行依赖 TLS 的原生构造与提交。
 *
 * 注意：绝不能把另一线程的 TLS 服务指针搬给 worker 使用 ——
 *       指针非空不代表服务归属、队列与寿命可转移。
 * ------------------------------------------------------------------ */
#define WX_TLS_INDEX_RVA   0xA530BA0
#define WX_TLS_SERVICE_OFF 0x1F0

typedef struct {
    DWORD  tls_index;
    void  *tls_block;      /* tls[idx] */
    void  *service;        /* [tls_block + 0x1F0] */
    int    service_vt_rva; /* 服务的 vtable RVA（若可读） */
} WxbTlsProbe;

/* MinGW 的 winnt.h 不暴露完整 _TEB 结构，直接从 gs:0x58 读
 * TEB->ThreadLocalStoragePointer（x64 ABI 固定偏移）。 */
static void **teb_tls_array(void) {
    void **p;
    __asm__ volatile("movq %%gs:0x58, %0" : "=r"(p));
    return p;
}

static void probe_tls(WxbTlsProbe *out) {
    int64_t base;
    DWORD idx;
    void **tls_array;
    void *blk;

    if (!out) return;
    out->tls_index = 0;
    out->tls_block = NULL;
    out->service = NULL;
    out->service_vt_rva = -1;

    base = (int64_t)wxb_weixin_module();
    if (!base) return;
    idx = *(DWORD *)(base + WX_TLS_INDEX_RVA);
    out->tls_index = idx;
    if (idx == 0 || idx > 0x10000) return;

    /* x64 下用 gs:0x58 取 TEB，再读 ThreadLocalStoragePointer */
    tls_array = teb_tls_array();
    if (!tls_array) return;
    blk = tls_array[idx];
    out->tls_block = blk;
    if (!blk) return;

    /* 只读服务指针；不做任何调用，避免触发空服务分支 */
    out->service = *(void **)((char *)blk + WX_TLS_SERVICE_OFF);

    /* 若服务非空，尝试读其 vtable 的 RVA（同样只读） */
    if (out->service) {
        __try {
            void *vt = *(void **)out->service;
            if (vt) out->service_vt_rva = (int)(((int64_t)vt - base) & 0x7FFFFFFF);
        }
        __except (EXCEPTION_EXECUTE_HANDLER) {
            out->service_vt_rva = -1;
        }
    }
}

void wxb_write_tls_report(const char *who, DWORD tid) {    WCHAR path[MAX_PATH];
    char info[512];
    WxbTlsProbe p;
    if (!wxb_paths_ready()) return;
    probe_tls(&p);
    wsprintfW(path, L"%s\\tls_report.txt", CONTROL_DIR);
    wsprintfA(info,
              "who=%s\r\n"
              "tid=%lu\r\n"
              "tls_index=%lu\r\n"
              "tls_block=%p\r\n"
              "service_0x1f0=%p\r\n"
              "service_vt_rva=0x%x\r\n"
              "verdict=%s\r\n",
              who,
              (unsigned long)tid,
              (unsigned long)p.tls_index,
              p.tls_block,
              p.service,
              (unsigned)p.service_vt_rva,
              p.service ? "HAS_SERVICE" : "NO_SERVICE");
    /* 追加模式：让 worker 线程与回调线程的报告并存，便于对比 */
    append_file_bytes(path, "\r\n----------------------------------------\r\n",
                      (DWORD)lstrlenA("\r\n----------------------------------------\r\n"));
    append_file_bytes(path, info, (DWORD)lstrlenA(info));
}

/* ------------------------------------------------------------------
 * 线程级 TLS 扫描（第 2 阶段 B：定位「究竟哪个线程持有服务」）
 *
 * 实测事实：worker 线程与微信窗口/消息线程的 [tls_block+0x1F0] 都是 0。
 * 说明该服务既不是「自建线程没有」那么简单，也**不是微信线程就一定有**，
 * 而是懒加载或只绑定在特定线程上。
 *
 * TEB 属于普通进程内存，可以安全读取其它线程的 TEB（线程存活期间），
 * 因此这里枚举本进程全部线程，逐个读取
 *     TEB + 0x58 -> ThreadLocalStoragePointer -> [idx] -> +0x1F0
 * 一次看清谁有服务。找到后即可用 QueueUserAPC 把构造/发送投递到那个线程。
 * ------------------------------------------------------------------ */
typedef LONG (NTAPI *WxbNtQit)(HANDLE, ULONG, PVOID, ULONG, PULONG);

typedef struct {
    LONG       ExitStatus;
    LONG       _pad0;
    void      *TebBaseAddress;   /* 官方文档名为 PebBaseAddress，实际返回 TEB 基址 */
    ULONG_PTR  AffinityMask;
    LONG       BasePriority;
    LONG       _pad1;
    ULONG_PTR  UniqueProcessId;
    ULONG_PTR  InheritedFromUniqueProcessId;
} WxbThreadBasicInfo;

#define WXB_TBIC_BASIC               0
#define WXB_TBIC_SET_WIN32_START     9

void wxb_scan_threads_tls(void) {
    WCHAR path[MAX_PATH];
    char line[400];
    int64_t base;
    DWORD idx;
    HANDLE snap;
    THREADENTRY32 te;
    DWORD self_pid = GetCurrentProcessId();
    DWORD self_tid = GetCurrentThreadId();
    int total = 0;
    int with_service = 0;
    WxbNtQit qit;
    HMODULE ntdll;

    if (!wxb_paths_ready()) return;
    base = (int64_t)wxb_weixin_module();
    if (!base) return;
    idx = *(DWORD *)(base + WX_TLS_INDEX_RVA);

    ntdll = GetModuleHandleW(L"ntdll.dll");
    qit = ntdll ? (WxbNtQit)GetProcAddress(ntdll, "NtQueryInformationThread") : NULL;
    if (!qit) return;

    wsprintfW(path, L"%s\\tls_threads.txt", CONTROL_DIR);
    wsprintfA(line,
              "self_tid=%lu tls_index=%lu pid=%lu\r\n"
              "--- threads ---\r\n",
              (unsigned long)self_tid, (unsigned long)idx, (unsigned long)self_pid);
    write_file_bytes(path, line, (DWORD)lstrlenA(line));

    snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    te.dwSize = sizeof(te);
    if (Thread32First(snap, &te)) {
        do {
            HANDLE th;
            WxbThreadBasicInfo tbi;
            ULONG ret = 0;
            void *tlsp = NULL;
            void *blk = NULL;
            void *svc = NULL;
            void *entry = NULL;
            int ok = 0;

            if (te.th32OwnerProcessID != self_pid) continue;
            total++;
            th = OpenThread(THREAD_QUERY_INFORMATION, FALSE, te.th32ThreadID);
            if (!th) continue;
            ZeroMemory(&tbi, sizeof(tbi));
            if (qit(th, WXB_TBIC_BASIC, &tbi, sizeof(tbi), &ret) == 0 &&
                tbi.TebBaseAddress != NULL) {
                __try {
                    tlsp = *(void **)((char *)tbi.TebBaseAddress + 0x58);
                    if (tlsp && idx > 0 && idx < 0x10000) {
                        blk = *(void **)((char *)tlsp + (SIZE_T)idx * 8);
                        if (blk) svc = *(void **)((char *)blk + WX_TLS_SERVICE_OFF);
                    }
                    ok = 1;
                }
                __except (EXCEPTION_EXECUTE_HANDLER) {
                    ok = 0;
                }
            }
            if (qit(th, WXB_TBIC_SET_WIN32_START, &entry, sizeof(entry), &ret) != 0) {
                entry = NULL;
            }
            CloseHandle(th);
            if (svc) with_service++;
            wsprintfA(line,
                      "tid=%lu%s teb=%p tlsblk=%p svc=%p entry=%p %s\r\n",
                      (unsigned long)te.th32ThreadID,
                      te.th32ThreadID == self_tid ? "(self)" : "",
                      tbi.TebBaseAddress, blk, svc, entry,
                      !ok ? "READ_FAIL" : (svc ? "HAS_SERVICE" : "no_service"));
            append_file_bytes(path, line, (DWORD)lstrlenA(line));
        } while (Thread32Next(snap, &te));
    }
    CloseHandle(snap);

    wsprintfA(line, "--- total=%d with_service=%d ---\r\n", total, with_service);
    append_file_bytes(path, line, (DWORD)lstrlenA(line));
}

static int nonce_valid(const WCHAR *nonce) {
    if (!nonce || lstrlenW(nonce) != WXB_STARTUP_NONCE_CHARS) return 0;
    for (DWORD i = 0; i < WXB_STARTUP_NONCE_CHARS; i++) {
        WCHAR c = nonce[i];
        if (!((c >= L'0' && c <= L'9') || (c >= L'a' && c <= L'f') ||
              (c >= L'A' && c <= L'F'))) return 0;
    }
    return 1;
}

static int copy_nonce(WCHAR *out, LPVOID param) {
    const WxbStartupConfig *config = (const WxbStartupConfig *)param;
    if (!out) return 0;
    out[0] = 0;
    if (!config || config->magic != WXB_STARTUP_CONFIG_MAGIC ||
        config->size != sizeof(WxbStartupConfig)) return 0;
    if (!nonce_valid(config->startup_nonce)) return 0;
    CopyMemory(out, config->startup_nonce,
               (WXB_STARTUP_NONCE_CHARS + 1) * sizeof(WCHAR));
    return 1;
}

static void startup_path(WCHAR *out, const WCHAR *nonce, const WCHAR *suffix) {
    if (!out || !nonce || !suffix) return;
    wsprintfW(out, L"%s\\worker_start_%s.%s", CONTROL_DIR, nonce, suffix);
}

static void startup_write(const WCHAR *nonce, const WCHAR *suffix, const char *text) {
    WCHAR path[MAX_PATH];
    startup_path(path, nonce, suffix);
    write_file_bytes_atomic(path, text, (DWORD)lstrlenA(text));
}

static int startup_exists(const WCHAR *nonce, const WCHAR *suffix) {
    WCHAR path[MAX_PATH];
    startup_path(path, nonce, suffix);
    return file_exists(path);
}

static int wait_for_ack(const WCHAR *nonce) {
    DWORD started = GetTickCount();
    if (!nonce || !nonce[0]) return 1;
    startup_write(nonce, L"ready", "worker ready\n");
    while (GetTickCount() - started < 30000) {
        if (startup_exists(nonce, L"cancel")) return 0;
        if (startup_exists(nonce, L"ack")) return 1;
        Sleep(50);
    }
    return 0;
}

static void cleanup_startup_files(const WCHAR *nonce) {
    WCHAR path[MAX_PATH];
    if (!nonce || !nonce[0]) return;
    startup_path(path, nonce, L"ready"); DeleteFileW(path);
    startup_path(path, nonce, L"ack"); DeleteFileW(path);
    startup_path(path, nonce, L"active"); DeleteFileW(path);
    startup_path(path, nonce, L"cancel"); DeleteFileW(path);
}

static int wait_for_hook_site(void) {
    DWORD started = GetTickCount();
    while (GetTickCount() - started < 10000) {
        if (recv_hook_site_ready()) return 1;
        Sleep(50);
    }
    return 0;
}

static int bridge_init(void) {
    ensure_dirs();
    wxb_ensure_weixin_module();
    if (wxb_weixin_module() && !recv_hook_installed()) {
        if (!install_recv_hook()) {
            write_status("receive hook install failed\n");
            return 0;
        }
    }
    /* pack 入口常驻 hook（TASK_LOG §31）：平时任何表情往来都自动把任务上下文落盘，
     * 使「免点击发送」不再需要人工特意触发一次。安装失败不阻塞启动——
     * 只是退化为需要人工触发，其它功能不受影响。 */
    if (wxb_weixin_module() && !wxb_pack_hook_installed()) {
        if (!wxb_install_pack_hook()) {
            write_status("pack hook install failed (auto ctx capture off)\n");
        }
    }
    return wxb_weixin_module() && recv_hook_installed();
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        wxb_set_bridge_instance(instance);
        DisableThreadLibraryCalls(instance);
    }
    return TRUE;
}

__declspec(dllexport) DWORD WINAPI WxBridgeWorker(LPVOID param) {
    WCHAR nonce[WXB_STARTUP_NONCE_CHARS + 1] = {0};
    char owner_token[128] = {0};
    int has_nonce = copy_nonce(nonce, param);
    if (!wxb_paths_init(wxb_bridge_instance(), param)) return 1;
    if (!wait_for_ack(has_nonce ? nonce : NULL)) {
        cleanup_startup_files(nonce);
        return 2;
    }
    if (InterlockedCompareExchange(&g_worker_active, 1, 0) != 0) {
        cleanup_startup_files(nonce);
        return 3;
    }
    ensure_dirs();
    wxb_ensure_weixin_module();
    if (!claim_worker_owner(owner_token, sizeof(owner_token))) {
        InterlockedExchange(&g_worker_active, 0);
        cleanup_startup_files(nonce);
        return 4;
    }
    /* A previous cache-busted basic DLL sees the owner token change, removes
     * its hook, and exits. Never overwrite a foreign/full bridge hook. */
    if (!wait_for_hook_site()) {
        write_status("receive hook site busy; restart Weixin before injecting basic bridge\n");
        release_worker_owner(owner_token);
        InterlockedExchange(&g_worker_active, 0);
        cleanup_startup_files(nonce);
        return 5;
    }
    if (!bridge_init()) {
        release_worker_owner(owner_token);
        InterlockedExchange(&g_worker_active, 0);
        cleanup_startup_files(nonce);
        return 6;
    }
    write_status("worker started\n");
    if (has_nonce) startup_write(nonce, L"active", "worker active\n");

    /* 第 1 阶段：建立自有消息 hook 并写出通道状态（不改动 poll 位置，
     * 以免影响现有文本发送功能；业务迁移在下一阶段进行）。 */
    install_msg_hook();
    wake_msg_thread();
    write_channel_status(g_msg_hook ? "phase1_waiting_callback" : "phase1_hook_missing");
    /* 第 2 阶段：记录 worker 线程的 TLS 服务状态（与回调线程对比） */
    wxb_write_tls_report("worker", GetCurrentThreadId());
    /* 第 2 阶段 B：枚举进程内所有线程，找出真正持有服务的那个线程 */
    wxb_scan_threads_tls();

    for (;;) {
        if (file_exists(STOP_FILE)) break;
        if (!worker_owner_current(owner_token)) break;
        if (!wxb_weixin_module()) wxb_ensure_weixin_module();
        if (wxb_weixin_module() && !recv_hook_installed()) install_recv_hook();
        if (wxb_weixin_module()) poll_outbox();
        /* 定期唤醒消息线程，并刷新通道状态（观察回调是否真的发生） */
        {
            static DWORD last_wake = 0;
            DWORD now = GetTickCount();
            if (now - last_wake > 2000) {
                last_wake = now;
                if (!g_msg_hook) install_msg_hook();
                wake_msg_thread();
                write_channel_status("running");
            }
        }
        Sleep(100);
    }

    if (g_msg_hook) {
        UnhookWindowsHookEx(g_msg_hook);
        g_msg_hook = NULL;
    }
    write_channel_status("worker_exiting");

    uninstall_recv_hook();
    release_worker_owner(owner_token);
    InterlockedExchange(&g_worker_active, 0);
    write_status("worker stopped\n");
    cleanup_startup_files(nonce);
    return 0;
}

__declspec(dllexport) LRESULT CALLBACK WxGetMsgHook(int code, WPARAM wparam, LPARAM lparam) {
    /* 只处理 HC_ACTION（评审指出：其他 code 应及时转交 CallNextHookEx） */
    if (code == HC_ACTION) {
        DWORD tid = GetCurrentThreadId();
        LONG n = InterlockedIncrement(&g_hook_callback_count);
        InterlockedExchange(&g_hook_last_tid, (LONG)tid);

        /* 首次回调即写出 ACK —— ready 必须由实际回调确认，
         * 不能只看 worker started。此后每 50 次刷新一次，保持回调轻量。 */
        if (n == 1 || (n % 50) == 0) {
            WCHAR path[MAX_PATH];
            char info[256];
            if (wxb_paths_ready()) {
                wsprintfW(path, L"%s\\hook_ack.txt", CONTROL_DIR);
                wsprintfA(info,
                          "callbacks=%ld\r\ncallback_tid=%lu\r\nwindow_tid=%lu\r\n",
                          (long)n, (unsigned long)tid, (unsigned long)g_weixin_tid);
                write_file_bytes(path, info, (DWORD)lstrlenA(info));
            }
            /* 第 2 阶段：记录回调线程的 TLS 服务状态（与 worker 对比）。
             * 回调里必须保持轻量，probe_tls 只做几次读取，不调用任何微信函数。 */
            wxb_write_tls_report("hook_callback", tid);
        }

        /* 第 1 阶段保持原有行为，业务迁移在下一阶段进行 */
        if (wxb_paths_ready() && InterlockedCompareExchange(&g_worker_active, 0, 0)) {
            if (!file_exists(STOP_FILE)) {
                if (wxb_weixin_module() && !recv_hook_installed()) install_recv_hook();
            }
        }
    }
    return CallNextHookEx(g_msg_hook, code, wparam, lparam);
}

__declspec(dllexport) DWORD WINAPI WxBridgeVersion(void) {
    return 0x04192301;
}
