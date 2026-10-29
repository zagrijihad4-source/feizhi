# 微信 PC 4.1.9.23 「发送收藏表情」技术档案

> 用途：把本次任务的全部进展、已验证坐标、失败尝试与待解决问题记录下来，便于其他人/其他 AI 接手。
> 结论先行：**文本收发已完全打通并可稳定生产运行；「发送收藏表情（自定义表情包）」未打通，
> 卡在 `0x17040A0`（信封构造）—— 参数经运行时核对正常，但调用后内容立即崩溃。**
>
> ⚠️ **阅读前必看**：本文件写完后经外部复核，发现两处关键错误已在
> [第八节「修订记录」](#八修订记录2026-10-13-下午) 中更正：
> **内容对象的 vtable 是 `0x83DCC28`（不是 `0x82BCC28`）**，
> **`+0x668` 存的是裸指针（不是 shared_ptr）**。
> 第三、四节的对应描述按第八节为准。

---

## 一、环境与工具链

| 项 | 值 |
|---|---|
| 微信版本 | `4.1.9.23`（目录 `C:\Program Files\Tencent\Weixin\4.1.9.23\`） |
| 目标模块 | `Weixin.dll`，179,819,056 字节，SHA256 未记录 |
| 运行时基址 | 每次启动变化，本例多次观测到 `0x7FFCBB540000`（不可写死） |
| 注入方式 | `SetWindowsHookExW(WH_GETMESSAGE)` + 远程 `LoadLibraryW`（比 `CreateRemoteThread` 隐蔽） |
| 编译 | LLVM-MinGW clang（`--target=x86_64-w64-windows-gnu`，需 `-fms-extensions` 以支持 `__try/__except`） |
| 动态分析 | frida 17.18.0 |
| 静态分析 | 自建 `pefile`(精确 RVA→文件偏移) + `capstone`(精确解码) 反汇编器 |

**重要**：`radare2` / `rizin` 在这份 179MB 的 PE 上**寻址不可靠**（`s <小地址>` 会落到 paddr 语义，
`s <imagebase+rva>` 又读到空洞），两次结果都与文件字节矛盾，已弃用。必须用 pefile + capstone。

---

## 二、已打通（生产可用）

### 2.1 文本收发

| 用途 | RVA |
|---|---|
| 收消息 hook 点 | `0x166A6BF`（`DoAddMsg`，运行时被替换为 `E9 3C 59 98 FE 90 90`——这正好是"hook 是否存活"的判据） |
| 轻量消息模型 vtable | `0x805E4E8`（msg+0） |
| 子对象 vtable | `0x805e708`（msg+0x10，由 CALL1 设置） |
| CALL1 文本消息构造 | `0x6A35B0` |
| CALL2 参数构造 | `0xDB40` |
| CALL2 三个委托 vtable | `0x83661E8` / `0x8366068` / `0x8366128` |
| CALL3 提交 | `0x160EBE0` |

**发送骨架（实测稳定）**：
```c
msg[0]      = base + 0x805E4E8;
msg[8]      = 0x100000001;
CALL1(msg + 0x10);          /* 构造子对象，其 vtable 变为 0x805e708 */
msg[0xE8]   = 1;            /* 消息类型 */
msg[0x18]   = msg + 0x10;   /* 关键：buf1 的"控制块"要取这个位置 */
msg[0x20]   = msg;
set_str(msg + 0xC0, wxid);
set_str(msg + 0x670, content);

rcxs[0]     = base + 0xDB40;
buf1[0]     = msg + 0x10;
buf1[8]     = msg + 0x10;   /* 伪 shared_ptr{ptr, ctrl}，两者同址 */
rcxs[8]=buf1; rcxs[0x10]=buf1+16; rcxs[0x18]=buf1+16;

buf3/4/5 各自 = { base+委托vtable, ..., [+0x38]=自身 };
result = CALL2(buf2, buf3, buf4, buf5, buf6);
CALL3(rcxs, result);
```
文本消息的 std::string 布局是 **32 字节**：`buf@+0`(16字节 SSO) / `len@+0x10` / `cap@+0x18`，`cap<=0xF` 表示 SSO。

### 2.2 内置表情（图片表情）

`[微笑]` `[偷笑]` 等 108 个代码**写在文本里，微信客户端会渲染成真正的表情图**（已人工确认）。
因此**不需要扩展 hook** 即可让机器人"发表情"。已在 prompt 中：
- 注入全部 108 个可用代码，并禁止自创（自创的微信不认，会显示成方括号文字）
- 硬约束禁止 Unicode emoji（🥲🥺 这类只是系统字体图标，看起来像机器人群发）

---

## 三、未打通：发送收藏表情（核心问题）

### 3.1 目标行为

让程序发送**用户表情库里已有的自定义表情**（`xwechat_files\<wxid>\business\emoticon\Persist\<hash2>\<md5>`，文件为加密存储，统一 magic `D0 B1 68 C5 3A C9 50 57`）。

### 3.2 已验证的运行时事实（frida 抓取，可信）

**提交侧对象（`0x160EBE0` 的 rcxs vector 元素）**：
```
信封 ptr=…  vtable = 0x82CB8D8
    +0x0b0  std::string  接收方 wxid（如 <WXID_FRIEND_A>）
    +0x600  std::string  消息 UUID（每次新生成，如 3e6ace01-03be-4ac6-a970-dafb38496db0）
    +0x668  shared_ptr   内容子对象
```
图片消息走同一条提交路径，只是信封 vtable 不同（观测到 `0x82CB658`），字段为
`+0xb0` 接收方、`+0x168` 文件名、`+0x600` UUID。

**内容子对象（vtable `0x83DCC28`）字段**（两次发送同一表情，逐字节相同）：
```
+0x020  md5             7ed206382321db118c4951f1e448166a
+0x060  md5b            49cd60dd1f354795b1334bf655a189a5
+0x0e0  CDN 20401       http://vweixinf.tc.qq.com/110/20401/stodownload?m=7ed20638…&filekey=3044…&storeid=26a5d7ba…&ef=1&bizid=1022
+0x100  CDN 20403       …/20403/…m=5f3c31ac…
+0x120  md5c            96d1ce52eeffc92219b7524763fbf5d5
+0x140  CDN 20402       …/20402/…m=455d8470…
```
`filekey` 是 ASN.1 DER，**md5 明文嵌在里面**：
```
30 44 02 01 01 04 30 [ 30 2e 02 01 6e("110") 04 02 "SH" 04 20 "<md5原文>"
                       02 03 020db6 04 0d 00000004 "btfs" 00000001 32 ]
```
**结论：表情不需要上传**（附件已在微信服务器），且 `md5`/`filekey`/`storeid` **本地可复用**
（同一表情连发两次完全相同）。这正是这条路比"发图片"更值得走的原因。

### 3.3 构造链三个关键函数（均经 capstone + `.pdata` 验证为**函数入口**）

| RVA | 作用 | 状态 |
|---|---|---|
| `0x15F35C0` | 内容对象构造 | ⚠️ 可裸调，但它造的是**链表容器**（vtable `0x82BCC28`，对象体 0x60 字节），**不是表情内容对象** —— 详见第八节更正 |
| `0x17040A0` | 信封构造（`(out, shared_ptr<Content>)`） | ❌ **调用后崩溃** |
| `0x1702FC0` | 包信封核心（被 `0x17040A0` 调用） | 未验证（未被走到）。它把对象 vtable 设为 `0x805e708` |

### 3.4 失败尝试全记录

**尝试 A：直接照搬开源项目 `aixed/WeChat-Hook` 的常量** → 崩进程（3 次）
该项目标称支持 `3.9.10.16 / 4.1.10.27`，其 `global.h` 里注释写着 `//ok 41930 ? 41923`，
且 `IMAGE_FIELD_VTABLE2 = 0x80D1128` 与本机逆向结果一致，让人误以为整组可用。
**但实测在本机 4.1.9.23 上：**
```
send_message     0x1677A30 → 落在函数内，反汇编是 lea rbp,[rdx+0x80]（MSVC 异常处理帧），不是发送函数
create_param2    0xDF40    → fn [0xded0,…)  不是入口；调用后崩在 Weixin.dll+0xdf79（解引用空指针）
txt_message_ctr  0x6B2C30  → fn [0x6b2c20,…) 不是入口
dec_pic_call     0x493E70  → fn [0x493cc0,…) 不是入口
param1_vtable    0x84EC9C8 → 内容是一串 ASCII 文本 "228F4DE4…"，根本不是 vtable
param2_1/2/3     0x8595F58/0x8595E98/0x8595DD8 → 全是垃圾数据
img_msg_vtbl     0x84F96B8 → 是有效的 4 槽 vtable，但它不是消息信封
```
**教训：跨版本能借的只有「数据布局」，绝不能借「函数地址和虚表地址」。**

**尝试 B：复用捕获对象做延迟重放** → 崩（5 次迭代）
思路是 hook `0x160EBE0` 保存 `(rcxs, result)` 并 retain，之后重新提交。逐次修掉的问题：
1. `own_rcxs` 清零时误清 `[0]`（`send_text.c` 里它是必需的）→ 崩 `0x50`
2. 错误地把 `result`（同进程内恒定地址的静态对象）替换成自有副本 → 崩在 `own_result` 附近
3. `own_rcxs` 缓冲区只给 0x40，而 CALL3 会访问 `rcxs+0x4C0`（`send_text.c` 的 rcxs 位于 0x30000 的 arena 内，
   那些偏移落在已分配内存里所以一直没暴露）→ 越界崩
4. 修完以上三点后重测 → 崩在 `access violation accessing 0x200000003c`
   —— `0x20000000xx` 是消息对象**标志值**的形态，它被当指针解引用了。
   **说明 `result` 这类对象即使内存还在，内部状态也已被微信改写。**
**结论：整条发送链是绑定了时间上下文的临时态，任何一环跨时间复用都会崩。**

**尝试 C：自己构造对象（本档案的核心未解问题）** → 崩在阶段 3
用 `0x15F35C0` 造内容对象 → 成功；填 6 个字段 → 成功；调 `0x17040A0` 包信封 → **崩**。
诊断数据（frida 在 `0x17040A0` 入口抓取）：
```json
{"a1": "0x12abb1f0020",      // env_buf（调用者提供的缓冲区）
 "a2": "0x12abb1f0000",      // shared_ptr<Content>
 "a1_0_ptr": "0x0",          // 目标缓冲已清零
 "a2_0_ptr": "0x12aba6d7350", // 内容对象指针（有效）
 "a2_8": "0x12aba6d7340",     // 控制块（有效）
 "a2_8_refcnt": 1,            // 引用计数正常
 "a1_head": "readable"}
```
**参数全部正常，但函数在序言之后、第一条逻辑之前就崩溃**（在 `0x17040A0`、`0x17040c1`、
`0x17040cc`、`0x17040da`、`0x17040e3`、`0x170411e`、`0x170412a` 设置的 7 个插桩点中，
除入口外**一个都没被触发**），`0x1702FC0` 也从未被调用。

### 3.5 `0x17040A0` 的反汇编（节选）

```asm
0x17040a0  push rbp
0x17040a1  push rsi
0x17040a2  push rdi
0x17040a3  sub rsp, 0x50
0x17040a7  lea rbp, [rsp + 0x50]
0x17040ac  mov qword ptr [rbp - 8], 0xfffffffffffffffe     ; SEH 帧标记
0x17040b4  mov rsi, rcx                                    ; rsi = arg1
0x17040b7  movabs rax, 0x100000001
0x17040c1  mov qword ptr [rcx + 8], rax                    ; arg1[8] = 引用计数 {1,1}
0x17040c5  lea rax, [rip + 0x6bc777c]                      ; → 控制块 vtable
0x17040cc  mov qword ptr [rcx], rax                        ; arg1[0] = vtable
0x17040cf  add rcx, 0x10                                   ; 对象体从 arg1+0x10 开始
0x17040da  mov rax, qword ptr [rdx + 8]                    ; arg2[8] = Content 控制块
0x17040e3  lock inc dword ptr [rax + 8]                    ; retain
0x1704126  lea rdx, [rbp - 0x30]
0x170412a  call 0x1702fc0                                  ; ★ 从未执行到
0x1704130  lea rax, [rip + 0x6bc77a1]                      ; → 0x82cb8d8
0x1704137  mov qword ptr [rsi + 0x10], rax                 ; 对象体 vtable = 信封 vtable
0x170413e  movups xmmword ptr [rsi + 0x670], xmm0
0x1704145  movups xmmword ptr [rsi + 0x680], xmm0
0x170414c  mov qword ptr [rsi + 0x690], 0
```
**注意**：它**不用 `operator new`**，而是要求调用者提供「控制块 + 对象体」的完整内存
（会写到对象体 `+0x690`）。这是与 `0x15F35C0` 的关键差别。

同样的模式（无 `operator new`、要求调用者给足缓冲区）也出现在
析构函数 `0x1704220`、以及 `0x9de2b0`（图片消息体）等函数上。

---

## 四、需要请教的具体问题

1. **`0x17040A0` 的正确调用约定到底是什么？**
   - 它是否要求 `arg1` 指向一个**已经构造好的对象**（即是"拷贝构造"而非"就地构造"）？
   - 是否还有第 3 个参数（如某个上下文/分配器）被我省略了（我一直只传 2 个）？
   - 为什么参数核对无误却崩在第一条逻辑之前？

2. **有没有 4.1.9.23 上正确的「图片/表情消息构造入口」坐标？**
   - 已知提交点是 `0x160EBE0`、信封 vtable 是 `0x82CB8D8`。
   - 只要能找到"构造出带该 vtable 对象的那个函数"，问题即解。

3. **是否存在「不构造对象」的发送路径？**
   - 例如某个高层 API 直接接收 `(wxid, emoticon_md5)`。

4. **`0x805e708` 这个 vtable 的语义**（`0x1702FC0` 会用它）——它与
   `send_text.c` 里 `msg+0x10` 子对象是同一族，是否意味着信封与文本消息模型可互换构造？

---

## 五、工程侧已就绪的基础设施（可复用）

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\build_clang.ps1` | clang 零 MSVC 构建 bridge DLL |
| `<PROJECT_ROOT>\wxdis.py` | pefile+capstone 反汇编器，支持 `.pdata` 函数边界查询（`fn`/`entry`/`str` 子命令） |
| `<PROJECT_ROOT>\wxref.py` | 字节级 xref：找 call/jmp/lea 引用（比 r2 的 `axt` 可靠） |
| `<PROJECT_ROOT>\find_ptr.py` | 在文件里搜"函数指针值"以定位 vtable 槽位 |
| `<PROJECT_ROOT>\dump_vtable.py` | dump vtable 并把槽位解析成函数 RVA + 大小 |
| `<PROJECT_ROOT>\str_xref.py` | 字符串 → 引用者 → 所属函数 |
| `<PROJECT_ROOT>\reinject.py` | 一次性注入（**注意：注入完成后会写 `stop.txt` 让 worker 退出**） |
| `<PROJECT_ROOT>\force_inject.py` | 强制热更新：先停旧 worker 再加载新 DLL（绕过 `hook_loaded` 检测） |
| `<PROJECT_ROOT>\restart_worker.py` | 不重启微信，远程调用已加载 DLL 的 `WxBridgeWorker` 导出把 worker 拉起来 |
| `<PROJECT_ROOT>\frida_sticker_capture.py` | 抓表情构造链（内容/信封/提交三点） |
| `<PROJECT_ROOT>\frida_sticker_diag.py` | 抓 `0x17040a0` 异常现场 + 内部轨迹 |

### 踩过的坑（务必记录）

1. **`reinject.py` 会调 `build.ps1`（MSVC）**：若 DLL 时间戳旧于源码就触发重建，而本机无 VS C++ 工具链
   → 注入失败。解法：改完源码后用 clang 构建，并把 `dist\wx_hook_bridge.dll` 的 mtime 设为**未来**。
2. **`restart_worker.py` 必须用「进程实际加载的那份 DLL 副本」算导出 RVA**
   （`bridge\control\inject_dlls\<模块名>`），用 `dist` 里的文件会算错 → 调到错误地址 → **微信崩溃**。
3. **frida 17 移除了 `Module.findBaseAddress`、`Memory.readByteArray`**，
   必须用 `Process.findModuleByName().base` 和 `NativePointer.readByteArray()`。
4. **frida 的 `rpc.exports` 方法名会把下划线转驼峰**（`send_later` → `sendLater`），调用侧要对应。
5. **`Memory.alloc` 默认不可执行**，写汇编 stub 前必须 `Memory.protect(.., 'rwx')`。
6. **`lock inc` stub**（frida 拿不到 `InterlockedIncrement`）：`F0 FF 01 C3` = `lock inc dword [rcx]; ret`，
   分配页 + `Memory.protect` 后即可当函数用。
7. **微信的发送链接跑在 fiber/协程里**（`0x64b5d7f` 是 fiber 上下文恢复：`mov rsp,[rcx+0x20]`、`ldmxcsr`、`jmp rdx`），
   **所以 frida 的 backtrace 会断在调度器 `0x587ca0`**，不要依赖它定位上游。
8. **微信崩溃后**：守护进程会自动重新注入 hook；但若进程是**提权**启动的，普通权限无法注入，
   表现为 `OpenProcess` 成功却读不到模块、`taskkill` 报 Access denied —— 需重启（或提权清理）。

---

## 六、给接手者的最短复现路径

1. 确认微信为 **4.1.9.23** 且为**普通权限**启动（否则注入不了）。
2. `powershell -File <PROJECT_ROOT>\build_clang.ps1` 构建，产物 `<PROJECT_ROOT>\dist\wx_hook_bridge.dll`。
3. 复制到 `<PROJECT_ROOT>\wx-basic-bridge\dist\`，并把 mtime 设为未来（避免触发 MSVC 重建）。
4. `python <PROJECT_ROOT>\force_inject.py` 注入并拉起 worker。
5. 验证文本：向 `bridge\outbox\next.txt` 写 `<seq>\t1\t<wxid>\t<文本>`，看 `bridge\control\result_<seq>.json`。
6. 复现崩溃：写 `<seq>\t3\t<wxid>\t0`（type=3 走 `wxb_send_sticker`），
   读回 `result` 会得到 `{"message":"stage=-3"}` —— 即"阶段 3 包信封时异常"。

**关键判据**：`stage` 返回值编码了到达的阶段（1 造内容 / 2 填字段 / 3 包信封 / 4 填信封 / 5 提交 / 7 完成），
负值表示在该阶段抛异常。这是目前最有效的定位手段（比写日志文件可靠，避免诊断代码本身成为干扰源）。

---

## 七、当前交付状态

- ✅ 文本收发：稳定生产运行（自动回复 + 主动消息）
- ✅ 内置表情：108 个代码已接入 prompt，渲染为真实表情图，硬约束禁止 Unicode emoji
- ❌ 收藏表情包：未打通，卡在 `0x17040A0`
- 🔒 生产安全性：`type=2`（图片）/`type=3`（表情）在 outbox 层受控，不会误触发导致微信退出

---

## 八、修订记录（2026-10-13 下午）

本节由一轮外部复核 + 一次精确采集驱动，**更正了上文两处关键错误**，并补上了新的构造证据。

### 8.1 更正一：内容对象的 vtable 是 `0x83DCC28`，不是 `0x82BCC28`

**错因**：我做 RVA 换算时是手工算的，算错了 **`0x120000`**（≈1.125 MB）。
采集到的绝对地址是 `0x7fff07e8cc28`，基址 `0x7ffeffab0000`：

```
正确：0x7fff07e8cc28 - 0x7ffeffab0000 = 0x83DCC28
我写的：0x82BCC28                              ← 少了 0x120000
```

**这两个是完全不同的类**：

| vtable | 引用数 | 性质 |
|---|---|---|
| `0x82BCC28` | 1（仅在 `0x15F35C0` 内） | 一个 **0x60 字节的对象体**，字段是 `+0x18`/`+0x28`/`+0x38` 几个**链表头**（`operator new(0x38)` 造空循环链表）。它是**多链表容器**。 |
| `0x83DCC28` | 24 | **真正的表情内容对象**，对象体 **0x158 字节**，字段是约 10 个 32 字节的 `std::string`。 |

**尺寸自洽性**：采集到的字段最远到 `+0x140`，落在 `0x158` 之内 ✅；而 `0x82BCC28` 只有 `0x60`，
根本装不下 —— 硬填就是越界写坏堆内存。**这正是"阶段 3 崩溃"的直接原因**：
我把一个"链表容器"当成"表情内容对象"喂给了信封构造。

### 8.2 更正二：`+0x668` 存的是裸指针，不是 shared_ptr

信封 `+0x668` 处解析出的 `ctrl` 恒为 **0**（`[env+0x670] == 0`），
说明那里是**裸对象指针**，不是 `{ptr, ctrl}` 的 16 字节智能指针包装。
此前采集脚本按 shared_ptr 解析该位置，据此得到的"控制块/引用计数"结论无效。

**统一术语**（后续采集必须区分）：

| 名称 | 含义 |
|---|---|
| raw / block | 整块原始存储起点（`operator new` 的返回值） |
| ctrl | 引用计数控制块（候选布局下可能等于 raw） |
| obj | 对象体（候选布局为 raw+0x10） |
| sp | 另外存放 `{obj, ctrl}` 的 16 字节包装 |

### 8.3 新增：`0x83DCC28` 的真实构造序列

在 24 处「设置该 vtable」的代码点中，完整序列如下（以 `0x03d67e50` 附近为例）：

```asm
mov  ecx, 0x1b0              ; operator new(0x1B0) = 432 字节
call 0x64a7d1c               ; operator new
mov  [r12+8], 0x100000001    ; 控制块引用计数 {1,1}
lea  rax, [rip+0x4674d93]    ; → 0x83DCC28
mov  [r12], rax              ; 控制块 vtable
lea  rdi, [r12+0x10]         ; 对象体 = 块 + 0x10
lea  rcx, [r12+0x18]
mov  r8d, 0x158              ; 对象体尺寸 0x158 = 344 字节
xor  edx, edx
call 0x669e3c0               ; 清零 0x158
mov  [r12+0x38], 0xF         ; 随后逐个初始化 std::string（cap=0xF 标记）
mov  [r12+0x58], 0xF         ;   ［间隔 0x20，共约 10 个］
mov  [r12+0x78], 0xF
...
```

`0x158` 的尺寸与 8.1 的结论互相印证。

### 8.4 新增：一次精确采集的实测数据（可信）

改用 **hook `operator new` 并按 `0x1B0` 过滤** 的方式重新采集（不再依赖猜测偏移，
且所有地址换算都在 Python 端用 base 统一完成）：

```
[COMMIT] 信封 vt_rva=0x82cb8d8   +0x0b0 '<WXID_FRIEND_A>'   +0x600 <UUID>
         内容 vt_rva=0x83dcc28            ← 确认
             +0x020 len=32  cap=47   <md5>            如 cbab1418a65ab56a82b228ea2a27c621
             +0x060 len=32  cap=47   <规格 md5>
             +0x0e0 len=324 cap=335  .../20401/stodownload?m=<md5>&filekey=…&storeid=…&ef=1
             +0x100 len=322 cap=335  .../20403/…
             +0x120 len=32  cap=47   <规格 md5>
             +0x140 len=324 cap=335  .../20402/…
             +0x1e0 len=32  cap=47   <规格 md5>
```

采集到的 md5（`cbab1418a65ab56a82b228ea2a27c621`）**正是用户表情库里那 7 个文件之一**，
证明采集链路真实可信。

**结论**：**字段偏移与旧记录一致**（`+0x020`/`+0x060`/`+0x0e0`/`+0x100`/`+0x120`/`+0x140`/`+0x1e0`），
所以那份偏移表是可用的；错的只是 vtable 的 RVA。

### 8.5 新增的未解问题：内容对象不走 `0x1B0` 那条分配

脚本判定 **「内容对象是否来自 `0x1B0` 分配」= False**。
而我 hook 到的 40+ 次 `0x1B0` 分配里，**只有一部分块头确实写着 `0x83dcc28`**，
其余块头是 ASCII 文本碎片 —— 说明**微信存在多个 `operator new` 重载或分配路径**，
我只 hook 到了其中一个（`0x64a7d1c`）。

**这决定了我能否自己分配一个布局正确的对象**，因此是下一步的首要目标。

### 8.6 方法学教训（写给后续接手者）

1. **绝不手工做 RVA 换算。** 本次两处错误（vtable 认错、字段归属误判）都源于此。
   必须程序化换算，并用**已知正确值反推基址自检**（本次反推结果与 frida 报告的 base 完全一致，才确认方法可靠）。
2. **hook 分配点比 hook 使用点更可靠。** 对象刚 `operator new` 出来时，地址与大小都是确定的，
   不依赖任何偏移假设。
3. **"阶段 N 通过"不等于"该阶段成功"。** `memory.c` 里的 `w64`/`w32`/`copy_bytes`
   都用 `__try/__except` **吞掉异常**，因此写入失败也会静默通过。
   后续诊断必须让底层写入返回失败状态，失败即中止，不得进入下一阶段。
4. **多点 inline hook 可能互相干扰。** 本次曾在相距 9/11/14 字节处设多个插桩点，
   因此"trace 未触发"不能作为"没走到"的证据；需要单点或低干扰观测复核。

### 8.7 新增工具

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\find_ctor.py` | 从「引用某 vtable 的 lea」中筛出「设置 vtable」的代码（构造函数候选） |
| `<PROJECT_ROOT>\frida_sticker_precise.py` | hook `operator new` 按大小过滤 + 提交点抓取，全程不做手工换算 |

### 8.8 更新后的待请教问题

1. **`0x83DCC28` 这个类走哪条分配路径？** 已知它不走 `0x64a7d1c`（`0x1B0` 过滤命中但不匹配）。
   微信还有哪些 `operator new` 重载 / 分配器入口？（这是当前首要目标）
2. **`0x17040A0`（信封构造 `(out, 裸指针)`）的正确契约** —— 注意 `arg2` 应为**裸对象指针**，
   不是 shared_ptr 包装（第 3.5 节的旧描述需按此修正）。
3. **是否有「不构造对象」的业务入口** —— 接收 `(会话 + 表情模型/md5)` 直接产生新发送任务。
4. **`0x8421B68` 是什么？** 部分 `0x1B0` 分配块的「对象体 +0x10」处指针指向它，疑为子对象 vtable。

---

## 九、分配路径完全解（2026-10-13 15:10，静态证据闭合）

本节回答外部评审提出的四个专项问题。**全部结论来自 `Weixin.dll` 文件字节的反汇编**，
未经手工 RVA 换算，可用 `wxdis.py` 复现。

### 9.1 先纠正一个前置错误：`0x64A7D1C` 不是构造函数

`0x64A7D1C` 的宿主函数是 `[0x064a7d1c, 0x064a7d58)`，**仅 60 字节**，是标准 MSVC
`operator new(size_t)` 的失败重试包装：

```
0x064a7d22  mov  rbx, rcx            ; 保存 size
0x064a7d36  call 0x66783f4           ; 真正分配器
0x064a7d3b  test rax, rax
0x064a7d3e  je   0x064a7d27          ; 失败 → new_handler
0x064a7d27  mov  rcx, rbx
0x064a7d2a  call 0x6661ce0           ; new_handler 返回 false 则抛 bad_alloc
0x064a7d46  cmp  rbx, -1
0x064a7d4c  call 0x64a8ac8           ; 抛 std::bad_alloc
```

所以「`0x64A7D1C` → `0x1B0` 的完整工厂」这个提法本身需要修正：
**`0x64A7D1C` 只是分配器，真正的工厂在调用它的地方。**

### 9.2 完整工厂 = `0x03D67DA0`（函数区间 `[0x3d67da0, 0x3d6860e)`，2158 字节）

**唯一调用者**：`0x05FAB6A1`（全 DLL 一处引用，`wxref.py` 可复现）。
调用链已追通三层：

```
0x05FA380C  → 0x05FAB590  → { 0x3D671A0, 0x3D67DA0 }
  入参来自         入参 rcx         两个工厂
  [rsi+0x258]
```

`0x3D671A0` 与 `0x3D67DA0` 是**同构兄弟函数**（只差字段偏移和 T 的大小）：

| | `0x3D671A0` | `0x3D67DA0` |
|---|---|---|
| 遍历字段 | `[obj+0x90]` / `[obj+0x98]` | `[obj+0x70]` / `[obj+0x78]` |
| 计数字段 | `[obj+0xa8]` | `[obj+0x6c]` |
| `operator new` 大小 | `0x308` | `0x1B0` |
| 控制块 vtable | `0x85265E8` | `0x83DCC28` |
| memset 大小 | `0x2f8` | `0x158` |

**两者结构完全一致，证明这是一套统一的对象工厂模板。**

### 9.3 `0x83DCC28` 在控制块，不在对象体

这是本次最关键的更正。

**证据一：写入位置与引用计数写在同一个 16 字节头里**

```
0x03d67e6e  mov  ecx, 0x1b0
0x03d67e73  call 0x64a7d1c           ; rax = 新块
0x03d67e79  mov  r12, rax
0x03d67e7c  mov  r13, rax
0x03d67e7f  movabs rax, 0x100000001
0x03d67e89  mov  [r12 + 8], rax      ; ← 引用计数（_Uses=1, _Weaks=1）
0x03d67e8e  lea  rax, [rip + 0x4674d93]   ; → RVA 0x83dcc28
0x03d67e95  mov  [r12], rax          ; ← +0 处写 0x83DCC28
```

**证据二：对象体另有真 vtable**

```
0x03d67fdc  lea  rax, [rip + 0x49ed545]   ; → RVA 0x8755528
0x03d67fe3  mov  [r12 + 0x10], rax        ; ← 对象体 +0 处写 0x8755528
```

`dump_vtable.py` 对比：

- `0x83DCC28` 槽位：`+0 = 0x170240`、`+1 = 0xa400`、`+2 = 0xa3d0`（30 字节）、`+3 = 0xa420`
  —— 都是极小的 `std::_Ref_count_base` 家族函数，**典型引用计数块 vtable**。
- `0x8755528` 槽位：`+0 = 0x3d69670`（68B）、`+1 = 0x3d69a50`（196B）、`+2..+11` 共 12+ 个槽
  —— 指向 `0x3d69xxx`，**与工厂 `0x3d67da0` 同代码区**，是业务类真 vtable。

**证据三：释放协议是双计数**

工厂尾部（`0x03d685b6`–`0x03d685e0`）与提交函数内（`0x0160ee79`–`0x0160ee93`）都出现同一段：

```
mov  rsi, [refctrl + 8]          ; rcx/rdi/rsi 均为引用计数块指针
lock dec dword [rsi + 8]         ; _Uses--
jne  done
call qword [rsi]                 ; 虚函数0 = _Destroy（析构 T）
lock dec dword [rsi + 0xc]       ; _Weaks--
jne  done
call qword [rsi + 8]             ; 虚函数1 = _Delete_this（归还内存）
```

**结论**：`0x83DCC28` = `std::_Ref_count_obj2<T>` 的 vtable，位于**控制块 +0**。
8.1 节「内容对象的 vtable 是 `0x83DCC28`」应修正为：
**内容对象的引用计数块 vtable 是 `0x83DCC28`，业务对象真 vtable 是 `0x8755528`。**

### 9.4 分配返回 RAX 如何映射到信封内容地址

```
RAX (operator new 返回值)
 ├─ [RAX + 0x00] = 0x83DCC28          control block vtable
 ├─ [RAX + 0x08] = 0x1_0000_0001      _Uses | _Weaks<<32
 ├─ [RAX + 0x0c] = (高32位)            _Weaks
 └─ [RAX + 0x10] = 0x8755528          对象体起点（body），业务 vtable
```

工厂把对象放进输出 vector 的**确切指令**（`0x03d68261`–`0x03d6828d`）：

```
0x03d68261  mov  rax, [rbp + 0x108]   ; = 控制块 = RAX
0x03d6826d  lock inc dword [rax + 8]  ; _Uses++
0x03d68271  mov  rax, [rbp + 0x100]   ; = 对象体 = RAX + 0x10
0x03d68278  mov  [rdx], rax           ; shared_ptr._Ptr = body
0x03d68282  mov  [rdx + 8], r13       ; shared_ptr._Rep = control block
0x03d6828d  add  qword [rax + 8], 0x10   ; vector.end += 16（push_back 完成）
```

配合工厂开头的 `0x03d6801b  mov [rbp+0x100], rdi`（`rdi = r12 + 0x10`，见 `0x03d67e99 lea rdi,[r12+0x10]`）
与 `0x03d68022  mov [rbp+0x108], r12`：

**信封 `+0x668` 存的是 `RAX + 0x10`，即对象体指针，不是控制块、不是 shared_ptr 包装。**
这印证并强化了 8.2 节的结论。

### 9.5 总大小 / 对象体偏移 / 完整初始化 / 释放规则

**总大小 `0x1B0`；对象体偏移 `+0x10`；对象体大小 `0x1A0`。**

完整初始化序列（按执行顺序）：

```
1. block = operator new(0x1B0)                    ; 0x03d67e6e–73
2. [block+0x00] = 0x83DCC28                       ; 控制块 vtable
3. [block+0x08] = 0x100000001                     ; _Uses=1, _Weaks=1
4. memset(block+0x18, 0, 0x158)                   ; 0x03d67ea3–ab，覆盖 [0x18,0x170)
5. [block+0x10] = 0x8755528                       ; 对象体 vtable
6. 10 个 std::string 初始化（stride 0x20）
     buf @ block+0x20,0x40,0x60,0x80,0xa0,0xc0,0xe0,0x100,0x120,0x140
     len @ +0x10（memset 已清零）、cap @ buf+0x18 全写 0xF（SSO）
7. [block+0x168] = 0xFFFFFFFF                     ; int32 = -1   0x03d67fd0
8. string @ block+0x170（buf/len/cap = 0/0/0xF）  ; 0x03d67fe8–ffd
9. string @ block+0x190（buf/len/cap 三字段被
     movups 一次性清 0，cap=0 而非 0xF）           ; 0x03d68009–12
     （cap=0 且 len=0 → 析构走 SSO 分支，不触发 free，安全）
```

**字段语义**（合并 8.4 的运行实测偏移，两套证据完全吻合）：

| 偏移 | 内容 | 实测长度 |
|---|---|---|
| `block+0x20` | md5 | 32 |
| `block+0x60` | spec md5 | 32 |
| `block+0xe0` | CDN 20401 | 324 |
| `block+0x100` | CDN 20403 | 322 |
| `block+0x120` | spec md5 | 32 |
| `block+0x140` | CDN 20402 | 324 |

**8.4 节记录的 `+0x1e0` 字段越界（块只有 `0x1B0`），应删除；其余六个偏移全部正确。**

**释放规则**：见 9.3 证据三的双计数协议。要点：
- `_Uses`（`+8`）归零 → `vtable[0]` 析构业务对象（10+2 个 string 逐一释放）
- `_Weaks`（`+0xc`）归零 → `vtable[8]` 归还内存
- 弱计数不归零则内存不归还；构造出的初始值 `_Weaks=1` 意味着**引用释放后内存一定被归还**

### 9.6 撤回 8.5 的结论

8.5 判断「内容对象不走 `0x1B0` 那条分配」是**错的**。静态代码 `0x03d67e6e mov ecx,0x1b0`
是铁证：内容对象**正是** `0x1B0` 块。

当时判定失败的真正原因：8.1 的 vtable RVA 错误（`0x82BCC28` vs 真实 `0x83DCC28`）导致
脚本用错的标记值去匹配块头。而「部分 `0x1B0` 块头是 ASCII 碎片」是因为
**微信其他代码也用同一个 `operator new` 分配 0x1B0**（例如 8.8 第 4 问那个 `0x8421B68` 的类），
过滤条件应改为「块头 == `0x83DCC28` **且** 块体 +0 == `0x8755528`」这一对。

### 9.7 新增工具

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\find_disp668.py` | 扫描指定 RVA 区间内所有 `[reg+disp]` 内存操作数指令，用于定位字段写入点 |
| `<PROJECT_ROOT>\frida_sticker_full.py` | 一次性采样：Record 对象原始字节 + 内容对象完整 0x1B0 字节 + 提交点 vector |
| `<PROJECT_ROOT>\reports\ctor_3d67da0.asm` | 工厂函数 700 条指令完整反汇编（2158 字节） |
| `<PROJECT_ROOT>\reports\commit_160ebe0.asm` | 提交函数完整反汇编 |

### 9.8 信封 `+0x668` 的写入点

`find_disp668.py` 扫描结果中，`0x01703xxx` 区段（信封构造区）命中最多：

```
0x017036bb  movups xmmword [r15 + 0x668], xmm0     ; 清零 16 字节
0x0170376b  mov    qword [r15 + 0x668], rax        ; ← 写入
```

这两条属于函数 `[0x01703670, 0x01703a68)`（1016 字节），该函数有 **23 处调用者**，
是通用的信封填充函数（`0x1703670`）。而 `0x17040A0` 是信封的构造/初始化函数。

### 9.9 仍然未解

1. **Record 对象（工厂入参那个 shared_ptr 指向的对象）的完整结构** ——
   已知 `+0x6c`(int)、`+0x70`(vector begin)、`+0x78`(vector size)、`+0x90`(另一 vector)、
   `+0xa8`(int)。vector 元素是什么尚未确认。
   **这决定能否枚举整个收藏库、从而支持任意表情而不只是重放。**
2. **信封构造的完整契约** —— `0x17040A0` + `0x1703670` 的字段填充顺序。
3. **业务层入口 `0x05FAB590` 的入参 `rcx` 是什么** —— 它的上位是 `0x05FA380C`，
   取 `[rsi+0x258]`。再往上尚未追。
4. `0x8421B68` 是哪个类的对象体 vtable（与 0x1B0 块共用分配器）。

---

## 十、完整发送链路（2026-10-13 15:20，已贯通到发送入口）

第九节解决了「对象怎么造」，本节解决「造完往哪送」。链路已用 `wxref.py` 单链追通，
每一层都是**唯一调用者**，可直接复现。

### 10.1 四层链路总图

```
0x03D67DA0   内容对象工厂      new(0x1B0)    → vector<shared_ptr<Content>>
     ↓
0x160EBE0    打包              new(0x108)    → shared_ptr<Pack>（内含 0xE8 字节子对象）
     ↓
0x16D5B80    信封工厂          new(0x698)    → shared_ptr<Envelope>
     ↓
0x16D4450    发送入口          dynamic_cast + 类型码分支 → 真正落网
```

### 10.2 信封工厂 `0x16D5B80`（函数区间 `[0x16d5b80, 0x16d5c3e)`，190 字节）

**唯一调用者 `0x16D4CA4`**。签名 `(rcx = &out_shared_ptr<Envelope>, rdx = &in_shared_ptr<X>)`：

```
0x016d5b9b  mov  ecx, 0x698              ; ← 信封总大小 0x698（2024 字节）
0x016d5ba0  call 0x64a7d1c               ; operator new
0x016d5bb0  call 0x17040A0               ; 信封初始化
0x016d5bba  lea  rax, [rdx + 0x10]       ; body = block + 0x10
0x016d5bbe  mov  [rsi], rax              ; out._Ptr  = body
0x016d5bc1  mov  [rsi + 8], rdx          ; out._Rep  = block（控制块）
```

**`0x698` 这个数字直接印证了实测字段 `+0x668` 落在信封内**，也印证 8.2 节「`+0x668` 存裸指针」。
信封对象体 = `block + 0x10`，与内容对象同一套 `_Ref_count_obj2<T>` 布局。

**信封初始化 `0x17040A0`（`[0x17040a0, 0x1704188)`，232 字节）**：

```
0x017040c1  mov  [rcx + 8], 0x100000001        ; _Uses=1, _Weaks=1
0x017040c5  lea  rax, [rip + 0x6bc777c]        ; → RVA 0x82CB848
0x017040cc  mov  [rcx], rax                    ; 控制块 vtable = 0x82CB848
0x017040cf  add  rcx, 0x10                     ; rcx → 对象体
0x0170412a  call 0x1702FC0                     ; 子对象构造（rcx = body, rdx = &in）
0x01704130  lea  rax, [rip + 0x6bc77a1]        ; → RVA 0x82CB8D8
0x01704137  mov  [rsi + 0x10], rax             ; 对象体 vtable = 0x82CB8D8
0x0170413e  movups [rsi + 0x670], xmm0         ; 清 0x670..0x690
0x0170414c  mov  qword [rsi + 0x690], 0
```

**注意两个 vtable 值不同**：控制块 `0x82CB848`、对象体 `0x82CB8D8`（相差 0x90）。
`wxdis.py` 会把这两个 `lea` 目标显示成乱码字符，不要被误导——按 RIP 相对值手算：
`0x17040cc + 0x6bc777c = 0x82CB848`，`0x1704137 + 0x6bc77a1 = 0x82CB8D8`。

子对象构造函数 `0x1702FC0`（`[0x1702fc0, 0x17031d6)`，534 字节）设 vtable `0x805E708` ——
**与文本发送路径 CALL1 用的是同一个子对象 vtable**，说明文本与表情共用同一套信封骨架。

### 10.3 发送入口 `0x16D4450`（函数区间 `[0x16d4450, 0x16d54f5)`，4261 字节）

签名 `(rdx = &out_shared_ptr, r8 = &in_shared_ptr<Base>, r9 = ?)`：

```
0x016d447a  mov  rdi, r8
0x016d448e  mov  rcx, [r8]                    ; rcx = in._Ptr（基类指针）
0x016d44a9  call 0x664d9fc                    ; dynamic_cast
0x016d44b2  test rax, rax
0x016d44b5  je   0x16d44d1                    ; 转换失败 → 输出空 shared_ptr 返回
0x016d44f1  mov  edx, [rax + 0xd8]            ; ← 读消息类型码
0x016d44f7  cmp  edx, 0x2e                    ; 阈值 0x2e = 46
0x016d4501  jg   0x16d4569                    ; 按类型分派
```

**`0x664D9FC` 是 `dynamic_cast` 的实现**（`[0x664d9fc, 0x664db62)`）：
读 `vtable[-1]` 作为 8 字节绝对地址取 RTTI COL，再按 `COL->offset` / `COL->cdOffset` 调整指针。

调用 `0x16D5B80` 之后，函数立刻写类型码：

```
0x016d4caa  mov  rax, [rbp - 0x40]            ; rax = env._Ptr（= body）
0x016d4cb3  mov  dword [rax + 0xd8], 0x2f     ; 分支一：body+0xd8 = 0x2F
0x016d4cc9  mov  [rax + 0xd8], 0x800000031    ; 分支二：0x800000031
```

即**信封 `body + 0xd8` 是消息类型/标志字段**（注意「相对对象体」，不是相对控制块）。

### 10.4 RTTI 现状（避免后续重走弯路）

本 PE **保留了 RTTI 框架但裁剪了业务类名字**：

- `dynamic_cast` 可用，`vtable[-1]` 确实是 8 字节绝对地址指向 `_RTTICompleteObjectLocator`
- 但业务类的 `COL->pTypeDescriptor` 指向的位置**不是合法 TypeDescriptor**
  （例如内容对象 vtable `0x8755528` 的 COL 在 `0x8755520`，其 pTypeDescriptor 指向的数据非 ASCII）
- 全 PE 能搜到 **1301 个** `.?AV...@@` 类名，**全部属于第三方库**（Skia：`SkSurface`/`SkFontMgr`/`SkCanvas`…），
  微信自身业务类一个都没有

**结论：不要指望用类名识别业务对象**，只能靠行为 + 字段偏移推断。
工具 `<PROJECT_ROOT>\find_classnames.py`（搜索/统计 RTTI 名字）与
`<PROJECT_ROOT>\read_rtti.py`（vtable → 类名）留档备查。

### 10.5 新增工具

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\dump_rva.py` | 按 RVA dump 原始字节 + qword 解读，核对结构体布局用 |
| `<PROJECT_ROOT>\find_classnames.py` | 搜索统计 PE 内 RTTI 类名（判定是否保留名字） |
| `<PROJECT_ROOT>\read_rtti.py` | vtable → RTTI 类名（已修正为 8 字节绝对地址读法） |
| `<PROJECT_ROOT>\reports\envelope_build.asm` | 信封工厂 `0x16D5B80` 反汇编 |
| `<PROJECT_ROOT>\reports\envelope_send.asm` | 信封消费点 `0x16D4CA4` 周边反汇编 |

### 10.6 剩余缺口（决定了走哪条路线）

1. **`0x16D4450` 的 `r9` 参数含义** —— 这是唯一还没定性的入参。
2. **`0x160EBE0` 的 `rdx`（0xE8 字节子对象）从哪来** —— 它是 `Pack` 的组成部分，
   由 `0x160EBE0` 的调用方传入，而该函数零处直接引用（经 vtable 槽 `0x82C02C8` 分发）。
3. **内容对象的 `body + 0xd8` 类型码在内容对象上读什么** —— `0x16D4450` 是在
   **dynamic_cast 之后的对象**上读 `+0xd8`，需要采样确认那个对象的实际布局。

**若缺口 1/2 能补上**，就能走「自己构造对象 → 直接调 `0x16D4450` 发送」的纯程序化路线；
**若补不上**，退路是「录制一次真实发送得到的对象字节 → 深拷贝后重放」，
该退路所需的全部布局信息第九节已经给全。

---

## 十一、内容对象字段实测（2026-10-13 15:43，字符串内容已读出）

本节是**决定性的运行时验证**：在发送入口 `0x16D4450` 处，按「信封 `+0x660`/`+0x668` 的
shared_ptr → 内容对象」的路径，把内容对象里 12 个 `std::string` 的**实际文本**全部读出。

### 11.1 抓到的那一条

发送的表情 md5 = `53dcede756bc62e5e7cfb3eca4c3b5c5`（**正是用户表情库 7 个文件之一**）。

```
内容对象 block = 0x1714c5cba80
  控制块 vtable  = 0x83dcc28      （RVA）
  对象体 vtable  = 0x8755528      （RVA）
  引用计数       = 4294967301 = 0x1_0000_0005   （_Uses=5, _Weaks=1）
  ptr - rep      = 0x10           （标准 _Ref_count_obj2 间距）

  block+0x20  len=32  '53dcede756bc62e5e7cfb3eca4c3b5c5'   ← 表情库文件名 md5
  block+0x40  len=0   ''
  block+0x60  len=32  '47a7ee64be7f48bea221fff11c1afcef'   ← spec md5（不在表情库）
  block+0x80  len=0   ''
  block+0xa0  len=0   ''
  block+0xc0  len=0   ''
  block+0xe0  len=324 CDN 20401  见 11.2
  block+0x100 len=322 CDN 20403  见 11.2
  block+0x120 len=32  'd85a76430c0abecd1715fc0b723b0e20'
  block+0x140 len=324 CDN 20402  见 11.2
  block+0x160 len=0   cap=0
  block+0x180 len=0   cap=0
```

**`block+0x20` 与表情库文件名逐字节相同** —— 这条链路（收藏表情 → 内容对象）确认无疑。

### 11.2 三个 CDN URL 的原文与关键结论

```
20401: http://vweixinf.tc.qq.com/110/20401/stodownload?m=53dcede756bc62e5e7cfb3eca4c3b5c5&filekey=30440201010430302e02016e0402534804203533646365646537353662633632653565376366623365636134633362356335020302209
20403: http://vweixinf.tc.qq.com/110/20403/stodownload?m=f0b6c132c1bf914a6b3988e987f975b2&filekey=3043020101042f302d02016e0402534804206630623663313332633162663931346136623339383865393837663937356232020232500
20402: http://vweixinf.tc.qq.com/110/20402/stodownload?m=7430d39e838150c21e91969c2b1e0cc7&filekey=30440201010430302e02016e040253480420373433306433396538333831353063323165393139363963326231653063633702030220a
```

**关键事实**：

1. **`20401` 的 `m=` 参数 = `53dcede756bc62e5e7cfb3eca4c3b5c5`** = `block+0x20` 的 md5，**完全一致**。
2. **`20403` 的 `m=` = `f0b6c132c1bf914a6b3988e987f975b2`、`20402` 的 `m=` = `7430d39e838150c21e91969c2b1e0cc7`**
   —— 这两个 md5 **既不等于 `block+0x20`，也不等于 `block+0x60`，也不等于 `block+0x120`**。
3. `filekey` 是一段 ASN.1 DER，**内部以 ASCII 十六进制形式嵌着对应 URL 那个 `m=` 的 md5**：
   `30 44 02 01 01 04 30 30 2e 02 01 6e 04 02 "SH" 04 20 <md5-ascii-hex> 02 03 02 20 9`

**结论（对方案路线具有决定意义）**：
这三个 URL 是**服务端为该表情下发的一组相关资源地址**（原图 + 两个衍生版本），
其 `m=` 参数包含**客户端无法从表情库文件名推导**的额外 md5。
**因此「一套模板只替换 `block+0x20` 的 md5」不足以覆盖任意表情**——
除非服务端仅按 `block+0x20` 索引（需实验验证），否则每个表情的三个 URL 都必须独立获得。

### 11.3 修正一处旧结论

8.2 节与 9.4 节关于 `+0x668` 的描述应统一为：

**信封 `body+0x660` 与 `body+0x668` 构成一对 `shared_ptr<Content>`**
（`_Ptr = body 指针`，`_Rep = 控制块指针`，两者相差 `0x10`）。
不是「裸指针」，也不是「只有 `+0x668` 有意义」。

### 11.4 两条可行路线（按成本排序）

**路线 A：逐表情录制（立即可行）**
收藏库只有 **7 个表情**。让用户逐个手动发送一次，每次用
`frida_string_dump.py` 抓下内容对象的 12 个字符串，
即得到 7 套完整模板。之后重放时深拷贝对象并直接调 `0x16D4450`。
**成本**：7 次手动发送。**覆盖范围**：现有 7 个收藏表情。

**路线 B：枚举收藏记录（一劳永逸）**
`0x3D67DA0` 遍历的 Record 对象里含每个表情的完整记录（应包含三个 URL）。
用 frida dump 该 Record 的元素，即可一次性拿到全部 7 个表情的三 URL，
无需逐个发送。
**成本**：1 次手动发送 + 一次 Record 结构 dump。**覆盖范围**：任意数量的收藏表情。

**建议先做路线 B**：它把「每次新增表情都要录一次」变成「一次拿到整库」，
只多花一次采样。其入口已知——在 `0x3D67DA0` 的 `onEnter` 里，
`rdx` 指向的 shared_ptr 即 Record，Record 的 `+0x70` 是所有待发项的 vector。

### 11.5 本轮新增工具

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\frida_send_trace.py` | 6 点全链路追踪（工厂/打包/信封工厂/信封初始化/子对象构造/发送入口） |
| `<PROJECT_ROOT>\frida_env_dump.py` | 信封全文 dump + 内容指针追踪 |
| `<PROJECT_ROOT>\frida_string_dump.py` | **读内容对象 12 个 string 的实际文本**（本轮决定性工具） |
| `<PROJECT_ROOT>\parse_env_dump.py` | 离线解析信封 dump，输出 qword 视图 + string 识别 |
| `<PROJECT_ROOT>\find_alloc_size.py` | 扫描全 DLL 的 `mov <reg>, size ; call operator_new` 模式 |

---

## 十二、打通：收藏表情模板发送（2026-10-13 16:03）

**7 个收藏表情全部发送成功，微信进程始终存活。**

```
tpl=0 (0fbdd73c) ok    tpl=1 (53dcede7) ok    tpl=2 (7ed20638) ok
tpl=3 (b90ff3bb) ok    tpl=4 (cbab1418) ok    tpl=5 (ccfabb49) ok
tpl=6 (d727ccdf) ok
```

### 12.1 成功的调用序列（四步）

```c
base = Weixin.dll 基址
op_new = (void*(*)(size_t))(base + 0x64A7D1C)

/* 1) 内容对象：0x1B0 字节，两个 vtable */
block = op_new(0x1B0);
*(u64*)(block + 0x00) = base + 0x83DCC28;   /* 控制块 vtable */
*(u64*)(block + 0x08) = 0x1_0000_0001;      /* _Uses=1, _Weaks=1 */
memset(block + 0x18, 0, 0x158);
*(u64*)(block + 0x10) = base + 0x8755528;   /* 对象体 vtable（对象体=block+0x10） */
for (i=0;i<12;i++) *(u64*)(block+0x20+i*0x20+0x18) = 0xF;  /* 12 个 string 置 SSO */
*(u32*)(block + 0x168) = -1;
/* 六个字段用 op_new 分配堆缓冲后填入（buf/len@+0x10/cap@+0x18）：
 *   0x20 lib_md5   0x60 spec_md5   0xe0 url20401
 *   0x100 url20403 0x120 aux_md5   0x140 url20402 */

/* 2) 信封：现成工厂，唯一参数是输出 shared_ptr 的地址 */
((void(*)(void*))(base + 0x1AFE710))(env_sp);   /* 内部 new(0x698) */
env_block = *(u64*)(env_sp + 8);   /* _Rep */
env_body  = *(u64*)(env_sp + 0);   /* _Ptr == env_block + 0x10 */

/* 3) 填信封（偏移相对 env_body） */
*(u32*)(env_body + 0xD8) = 0x2F;                    /* 收藏表情类型码 */
heap_string(env_body + 0xB0, to_wxid);              /* 接收者 */
heap_string(env_body + 0x600, uuid_36);             /* UUID */
*(u64*)(env_body + 0x660) = block + 0x10;           /* 内容对象 _Ptr */
*(u64*)(env_body + 0x668) = block;                  /* 内容对象 _Rep */
*(u32*)(block + 0x08) += 1;                         /* 引用 +1 */

/* 4) 发送 */
((void(*)(i64,i64,i64,i64))(base + 0x16D4450))(0, out_sp, env_sp, 0);
```

### 12.2 崩溃复盘：参数错位（含 minidump 定位法）

**首次实测微信直接崩溃。** 用自写脚本解析 minidump 得到决定性证据：

```
异常码   : 0xC0000005 EXCEPTION_ACCESS_VIOLATION
崩溃地址 : Weixin.dll + 0x16D448E
访问地址 : 0x0
```

`0x16D448E = 0x16D4450 + 0x3E`，对应指令 **`mov rcx, qword ptr [r8]`** ——
即 `r8` 为 NULL。原因是**参数整体错位**：

| | 我的错误调用 | 正确调用 |
|---|---|---|
| rcx | `out_sp` | 无关（函数内 0x16D448E 处即被覆盖） |
| rdx | `env_sp` | `&out_sp` |
| r8 | `0` ← **NULL，崩溃点** | `&env_sp` |
| r9 | 未传 | 上下文（先传 0） |

**正确约定由真实调用点 `0x16A7B57` 逆推**：
`0x16A7B46 lea rdx,[rbp+0x1e0]` → `0x16A7B4D lea r8,[rbp+0x1c0]` → `0x16A7B54 mov r9,r15`。

**教训：x64 下「第 N 个参数」落哪个寄存器必须从真实调用点逆推，
不能凭函数名或直觉假设；少传一个参数不会编译报错，但会把后面的参数全挤错位。**

**新增工具** `<PROJECT_ROOT>\parse_minidump.py`：零依赖解析 `%LOCALAPPDATA%\CrashDumps\*.dmp`，
直接输出异常码、崩溃地址、所属模块与 RVA、访问地址 —— 比装 WinDbg 快得多。

### 12.3 工程落地

| 文件 | 作用 |
|---|---|
| `src/include/wx_sticker_templates.h` | 由 `reports/sticker_templates.json` 自动生成（`gen_templates_h.py`），7 个表情的 6 字段 |
| `src/modules/send_sticker_tpl.c` | 发送器：四步构造 + 分阶段 status 日志（崩溃时能定位到 stage） |
| `src/modules/outbox.c` | 新增 `type=4` 分支：`<seq>\t4\t<wxid>\t<模板号>` |
| `src/include/wx_bridge_offsets.h` | 新增 `WX_OFF_STK_*` 系列，并更正旧注释里 `0x82BCC28` → `0x83DCC28` |

**协议用法**：
```bash
# 在 bridge/outbox/next.txt 写入（UTF-8 无 BOM）：
<seq>\t4\t<接收者wxid>\t<模板号 0..6>
# 结果见 bridge/control/result_<seq>.json
```

### 12.4 热注入的正确姿势（踩过的坑）

`force_inject.py` 依赖 `wechat_inject.inject_hook`，而该函数**无条件**调用 `build_dll()`；
`build_dll` 只在「DLL 比源码新」时才跳过 MSVC 构建。三个必须同时满足的条件：

1. **构建产物要落到注入器读的路径**：注入器读 `wx-basic-bridge\dist\wx_hook_bridge.dll`，
   而 `build_clang.ps1` 输出到 `<PROJECT_ROOT>\dist\` —— 必须显式复制过去。
2. **复制后把目标 DLL 的 mtime 设为未来**（源码最新是刚写的那个 .c，否则又触发 MSVC 构建）。
3. **注入前必须先真正停掉旧 worker 并等它释放 hook 站点**：
   写 `stop.txt` → 轮询 `status.txt` 直到出现 `worker stopped` → 删 `stop.txt` → 再注入。
   只 sleep 固定几秒就注入，会在 `lifecycle.c` 的 `wait_for_hook_site()` 处失败（返回 5）。

### 12.5 遗留与下一步

1. **`r9` 仍未定性** —— 传 0 已能成功发送，但语义未知。
2. **扩展表情需重新采样**：新收藏表情要走一遍
   `frida_string_dump.py` → `extract_templates.py` → `gen_templates_h.py` → 重建。
3. **接入 `feizhi_pc`**：模板发送已可用，可让自动回复在合适场景发收藏表情
   （此前 persona 里只有 108 个内置表情码）。
4. **崩溃转储遗留**：`%LOCALAPPDATA%\CrashDumps\` 下有多次 `Weixin.exe.*.dmp`
   （含 13:55/13:56 两次早于本次实验的崩溃），可留档分析。

---

## 十三、真正的发送入口与上下文对象（2026-10-13 16:20）

### 13.1 更正：`0x16D4450` 不是发送函数

第十二节曾据「调用未崩溃」判定发送成功 —— **这是错的，用户并未收到消息**。

用 `tpl_debug.txt` 输出实参后得到铁证：

```
out.ptr = 0x1F9A98D9940
env     = 0x1F9A98D9940      ← 与 out.ptr 完全相同
out.vt  = RVA 0x82CB8D8      ← 就是我传进去的那个信封
out[0x00] = 信封 vtable
out[0x08] = 自身   out[0x10] = 控制块
```

**`0x16D4450` 只是「校验并原样返回传入的信封」，不产生任何副作用。**

### 13.2 逐层排查后的真实调用链

```
0x16D4450  返回信封本身（无副作用）
   ↓ 0x16A7EB0
0x34F01F0  比较 [ctx+8] 与 env，相等则记日志；也不是发送
   ↓
0x16A60D0  f(rcx = ctx, rdx = &out, r8 = &env_sp)   ← 真正的发送入口
   ↓ 0x16A6251
0x16A77E0  f(rcx, rdx, r8 = &shared_ptr<ctx>)
   ↓ 0x165B2B0（通用消息发送，4 个调用者：文本/图片/表情共用）
0x165B2B0  f(rcx = ctx, rdx = &string结构)
```

**关键更正**：正确入口是 `0x16A60D0(ctx, &out, &env_sp)`，参数是
「第 1 = 上下文对象，第 2 = 输出缓冲，第 3 = 信封 shared_ptr」，
而不是我之前使用的 `0x16D4450(rcx无关, rdx=&out, r8=&env_sp, r9=0)`。

### 13.3 上下文对象 ctx 是持久的（已硬证）

运行时捕获（`frida_sendctx_capture.py`）显示：两次不同来源的发送
（caller RVA `0x16575b5` 与 `0x16f7ed7`）使用**同一个 ctx**：

```
ctx = 0x1F9AF4884B0
vt  = 0x00007FFCA73274F8  →  RVA 0x82C74F8
```

发送结束后用 `ReadProcessMemory` 复读同址，**vtable 逐位相同**：

```
ctx+0x00 = 0x00007ffca73274f8   （== 期望值）
ctx+0x08 = 0x1f9af4884b0        （指向自身）
ctx+0x10 = 0x1f9af4884a0        （自身 - 0x10）
ctx+0x18 = 1     ctx+0x20 = 1
```

⇒ **ctx 是持久对象**（`enable_shared_from_this` 风格：`+8`/`+0x10` 是自身的 shared_ptr）。

**但它不是全局单例**：`0x1704520` 那个 getter 返回的静态地址 `base+0x9F961E0`
指向的是另一个类的 vftable，与 ctx 无关。ctx 由 `0x1652530` 就地构造，
调用者是 `0x1704530`（ctor + 条件析构的包装），再往上追到 UI 层。

### 13.4 运行时定位 ctx 的可行方法（已验证可用）

由于 ctx 地址随进程重启变化，采用**特征扫描**：在 `MEM_COMMIT | MEM_PRIVATE |
可读且非 GUARD/NOACCESS` 的区域中，按 8 字节步长搜索满足三重条件的地址：

```
[p]     == base + 0x82C74F8     （vtable）
[p + 8] == p                    （self）
[p + 0x10] == p - 0x10          （控制块）
```

**实测一次命中**，返回值与 frida 捕获的 ctx 完全一致（`0x1F9AF4884B0`）。
实现见 `send_sticker_tpl.c` 的 `wxb_find_send_ctx()`，含溢出保护与区域过滤。

### 13.5 当前阻塞点

`0x16A60D0(ctx, &out, &env_sp)` 调用后**微信崩溃**：

```
异常码   : 0xC0000005 EXCEPTION_ACCESS_VIOLATION
崩溃地址 : 0x0000009994FEF946   （不在任何模块内 —— 非法跳转）
访问地址 : 0x8                  （对 NULL+8 解引用）
```

**ctx 定位本身是对的**（`tpl_debug.txt` 记录了 `ctx=000001F9AF4884B0`），
说明 `0x16A60D0` 内部还依赖额外的运行时状态 —— 最可能是
**「当前存在激活会话」一类的 UI 上下文**（信封虽已就绪，但缺少投递目标会话）。

**结论**：`0x16A60D0` 不是无副作用的纯函数入口，它假设调用者处于
正常的 UI 消息流程中（`0x16A60D0` 自身就是被 `0x165B2B0` 在会话上下文中调用的）。

### 13.6 两条可选路线

**路线 A（推荐，风险低）：hook 替换法**
在 `0x16A60D0` 入口挂 hook，当用户在微信里**手动发送任意表情**时，
把 `r8` 指向的信封里的内容对象替换为我们模板构造的对象。
优点：整条调用链的所有上下文都是真实且完整的，不会崩；
     内容完全由我们控制（可指定发哪个收藏表情）。
代价：仍需一次用户手势触发（可配合自动回复：回复时触发）。

**路线 B（成本高）：补全 `0x16A60D0` 的前置状态**
继续逆向它内部依赖的会话字段，在调用前手工准备好。
需要更多轮次的崩溃-分析循环，且每次失败都会让微信退出。

### 13.7 本轮新增工具与教训

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\frida_submit_capture.py` | 抓 `0x34F01F0` / `0x16A77E0` / `0x165B2B0` 的实参 |
| `<PROJECT_ROOT>\frida_sendctx_capture.py` | 抓通用发送的 ctx 并输出候选地址 |
| `<PROJECT_ROOT>\parse_minidump.py` | **零依赖解析崩溃转储**，直接给出异常码/崩溃地址/模块 RVA |

**教训（第三次同类错误）**：本档案第十二节已写明「stage N passed ≠ success」，
我仍然用「调用没崩」当成了「发送成功」，并在用户反馈后才发现。
**判定发送成功的唯一可信标准是「对端收到」**，其余一律只能称「调用返回」。
后续所有阶段码都应改名为 `submitted`/`returned` 这类中性词，避免再次误读。

**环境注意**：`C:\Program Files\Tencent\Weixin\WeixinUpdate.exe` 会在后台自动更新，
更新期间 `Weixin.exe` 启动后会立刻退出（表现为"启动失败"），
与本项目改动无关；排查启动问题时应先确认 `WeixinUpdate` 是否在运行。

---

## 十四、新路线：`0xDB40` 通用消息任务构造器（2026-10-13 16:23）

### 14.1 关键观察：文本与表情共用同一个构造器

文本发送模块 `wxb_send_text`（**长期稳定工作**）的核心是：

```c
result = ((FnCall2)(base + WX_OFF_SEND_CALL2))(buf2, buf3, buf4, buf5, buf6);
if (result) ((FnCall3)(base + WX_OFF_SEND_CALL3))(rcxs, result);   /* → 0x160EBE0 */
```

其中 `WX_OFF_SEND_CALL2 = 0xDB40`、`WX_OFF_SEND_CALL3 = 0x160EBE0`。

而**表情消息构造函数 `0x160DF80` 内部调用的是同一个 `0xDB40`**：

```
0x0160e2d2  mov  [rsp + 0x28], rdi      ; 第 6 参数（栈）
0x0160e2d7  mov  [rsp + 0x20], rbx      ; 第 5 参数（栈）
0x0160e2dc  lea  rcx, [rbp + 0x140]     ; 参数 1 = 输出 shared_ptr
0x0160e2e3  lea  rdx, [rbp + 0x30]      ; 参数 2
0x0160e2e7  lea  r8,  [rbp - 0x10]      ; 参数 3
0x0160e2eb  lea  r9,  [rbp - 0x50]      ; 参数 4
0x0160e2ef  call 0x18000db40
0x0160e2f5  mov  rcx, [rsi + 0x38]
0x0160e302  mov  rax, [rcx]
0x0160e305  lea  rdx, [rbp + 0x140]
0x0160e30c  call qword ptr [rax + 0x10] ; ★ → 0x160EBE0（pack），vtable 槽 +0x10
```

**两个关键点**：

1. **`0xDB40` 是文本与表情共用的「消息任务构造器」**
2. **`0x160EBE0`（pack）是通过 vtable 槽 `[rax+0x10]` 调用的**
   —— 这独立印证了第九节「`0x160EBE0` 落在 vtable `0x82C02C8`」的结论

### 14.2 `0xDB40` 自身的结构

```
0x0000db67  mov  rsi, rcx            ; 参数1 = 输出地址
0x0000db6a  mov  ecx, 0x18
0x0000db6f  call 0x64a7d1c           ; operator new(0x18)
0x0000db75  movabs rcx, 0x100000001
0x0000db7f  mov  [rax + 8], rcx      ; _Uses=1, _Weaks=1
0x0000db83  lea  rcx, [rip+0x7f5180e] ; → 0x7F5F398（控制块 vtable）
0x0000db8a  mov  [rax], rcx
0x0000db94  mov  byte [rax + 0x10], 0
0x0000db98  mov  [rsi], rcx_body      ; out._Ptr = block + 0x10
0x0000db9b  mov  [rsi + 8], rax       ; out._Rep = block
0x0000db9f  mov  [rsi + 0x48], 0
0x0000dbab  mov  rcx, [r12 + 0x38]    ; r12 = 参数2
```

⇒ `0xDB40(rcx = &out_shared_ptr, rdx = obj1, r8 = obj2, r9 = obj3, [rsp+0x20] = obj4)`
   内部 `new(0x18)` 并把结果写入 `out`。

### 14.3 两种调用风格的差异（关键）

| | 文本路径（已验证可用） | 表情路径（微信自身实现） |
|---|---|---|
| 参数 2/3/4 | **手工伪造的静态包装**：buf 内写静态 vtable（`0x83661E8`/`0x8366128`/`0x8366068`）+ 在 `+56` 处写自指针 | **栈上的真实对象**：`[rbp+0x30]`、`[rbp-0x10]`、`[rbp-0x50]` |
| 第 5/6 参数 | `buf6`（未使用） | `rbx` / `rdi`（栈上真实对象） |

**这说明**：文本发送之所以能程序化工作，是因为它「伪造了那三个包装对象」；
而表情路径的包装对象是真实构造的。

### 14.4 为什么这条路比 `0x16A60D0` 更值得试

- `wxb_send_text` 证明「手工伪造参数 + 调 `0xDB40` + 调 `0x160EBE0`」**程序化可行且稳定**
- 该路径**完全绕开** `0x16A60D0`，因而不需要「激活会话」这类 UI 上下文
- 内容对象（`0x1B0`）与模板库（7 个表情）**已完全就绪**

### 14.5 待解的具体问题（交给外部评审）

`0x160DF80` 中送给 `0xDB40` 的那几个参数对象，其**类型与内容**尚未逆向：

1. 参数 2（`[rbp+0x30]`）、参数 3（`[rbp-0x10]`）、参数 4（`[rbp-0x50]`）
   分别是什么类型？是否就是三个「发送目标/内容/选项」包装？
2. 第 5、6 个参数（`rbx`、`rdi`，经 `[rsp+0x20]`/`[rsp+0x28]` 传栈）是什么？
3. 文本路径用静态 vtable `0x83661E8`/`0x8366128`/`0x8366068` 充当包装；
   **表情是否只需把这几个 vtable 换成表情对应的**？若是，对应 RVA 是多少？
4. `0x160DF80` 的入参是什么？它是否可被直接调用（像 `wxb_send_text` 那样自造 arena）？

**建议的验证顺序**（每步失败只会让微信退出，不会损坏数据）：
先在文本路径上把某一包装 vtable 换成候选表情 vtable 做单点实验，
观察是否被服务端拒绝（而非崩溃）——这能快速判断 vtable 是否就是「类型标签」。

> **【作废】以上"换 vtable 试错"的建议已被第十五节推翻**，理由见 15.3：
> 那三个包装是 `std::function` 类型擦除委托（复制/移动/调用/销毁四类虚行为），
> 换 vtable 会同时改变捕获成员的布局与所有权解释。**不要执行这段。**

---

## 十五、外部评审后的三处纠正（2026-10-13 16:39）

外部评审（`D:\Hermes work\微信收藏表情_最新发送路线评审与解决思路_2026-10-13.md`）
指出三处问题，**经逐条核对源码与 dump，三条全部成立**。

### 15.1 纠正一：minidump 解析偏移错误，撤回「缺少激活会话」推论

`parse_minidump.py` 原先用 `struct.unpack_from("<IIQI", d, rec)` 取 `num_params`，
该字段落在 `+0x10` —— 那实际是 **ExceptionAddress 的低 32 位**；
参数数组起点也写成了 `rec+0x18+i*8`，**整体提前了 8 字节**。

**正确的 MINIDUMP_EXCEPTION 布局**：

| 相对异常记录起点 | 字段 |
|---|---|
| `+0x00` | ExceptionCode |
| `+0x04` | ExceptionFlags |
| `+0x08` | ExceptionRecord |
| `+0x10` | ExceptionAddress |
| `+0x18` | NumberParameters（32 位） |
| `+0x1C` | 对齐 |
| `+0x20` | ExceptionInformation[0] |
| `+0x28` | ExceptionInformation[1] |

**后果**：原先打印的「访问地址 = 0x8」实际是 **`Information[0]`（操作码）**。
`0`/`1`/`8` 分别表示读/写/**执行**违规。`0x8` 是**执行违规**，
不是「访问地址 0x8」——**据此推出的「NULL+8 → 缺少激活会话」没有依据，撤回。**

**修正后的真实结果**（同一份 `Weixin.exe.31840.dmp`）：

```
异常码   : 0xC0000005
参数个数 : 2
操作码   : 8  (执行违规)
访问地址 : 0x0000009994FEF946   ← Information[1]
崩溃地址 : 0x0000009994FEF946   ← 与访问地址相同 ⇒ 执行流本身跳到了该地址

Rip = 0x9994FEF946      Rsp = 0x9994FEF850      Rsi = 0x9994FEF920
Rdi = 0x9994FEF84C      Rbp = 0x7FFD9094C160   <= KERNELBASE.dll+0x4C160
Rax/Rcx/Rdx/R8/R9 = 0
```

**关键推论**：`Rip` 与 `Rsp` **同处 `0x9994F...` 区段**，且 `Rip - Rsp = 0xF6`
——这不是「垃圾地址」，而是**「代码正在某个栈区域里执行」**。
结合 `Rbp` 落在 `KERNELBASE.dll` 的 fiber 相关函数上，最自洽的解释是：

> **微信的发送链运行在 fiber/coroutine 栈上**（档案早先已记录
> `0x64b5D7F` 是 fiber 上下文恢复：`mov rsp,[rcx+0x20]; ldmxcsr; jmp rdx`），
> 而我从**普通 worker 线程**直接调用，等于在**没有 fiber 栈的上下文**里执行链上代码
> → 执行违规。

**这是「缺 fiber 栈」，不是「缺会话」。** 是否需要在 fiber 上调用，需进一步验证，
但至少「缺少激活会话」这个方向已被证伪。

另：评审指出「不在模块列表中」不能自动等同于垃圾代码，还需区分线程栈、
动态代码、hook 跳板、未列出的可执行区域 —— 上述 `Rsp` 同区段的证据正说明这一点。

### 15.2 纠正二：内容构造的两处错误（已修复）

**（a）尾部两个 string 的偏移错了**

原生布局（`ctor_3d67da0.asm`）：

| 区域 | 原生布局 |
|---|---|
| 前 10 个 string | `block+0x20` .. `block+0x140`，stride `0x20` |
| `block+0x160..0x16F` | **元数据区**（`+0x168` 为 int32） |
| 第 11 个 string | `block+0x170`（len@`+0x180`, cap@`+0x188`） |
| 第 12 个 string | `block+0x190`（len@`+0x1A0`, cap@`+0x1A8`） |

原实现按 `0x20 + i*0x20` 连续跑 12 次，i=10/11 落到 `0x160`/`0x180`
—— **把第 11 个 string 的 buf（`0x170`/`0x178`）写坏了**，
且真实尾部两项从未按原生布局初始化。

**已修复**：引入 `wxb_slot_offset(slot)`，前 10 个连续、第 11/12 个分别返回 `0x170`/`0x190`。
验证见 15.4 的差异表。

**（b）声明的容量大于实际分配**

原实现 `op_new(len + 1)` 却把 cap 写成 `len | 0xF`：

| 字符串长度 | 实际申请 | 原声明容量 | 容量对应最低存储 |
|---:|---:|---:|---:|
| 32 | 33 | 47 | 48 |
| 324 | 325 | 335 | 336 |

**已修复**：`cap = len | 0xF`，并实际 `op_new(cap + 1)` 且清零。
MSVC 的 capacity **不含** 结尾 NUL，故分配 `cap+1` 是正确的。

### 15.3 纠正三：`0xDB40` 的三个包装不是「类型标签」，换 vtable 方案作废

第十四节末尾曾建议「把包装 vtable 换成表情对应的」做单点实验 —— **该建议作废**。

`0xDB40` 的实际行为（`reports/db40.asm`）：

```
0x0000dbd2  mov  rcx, [r12 + 0x38]     ; r12 = 参数2
0x0000dbd7  test rcx, rcx
0x0000dbda  je   …                     ; 空则跳过
0x0000dbdc  cmp  rcx, r12              ; ← 是否指向自身（内联判定）
0x0000dbdf  setne dl
0x0000dbe2  mov  rax, [rcx]
0x0000dbe5  call qword ptr [rax + 0x20]  ; 虚调用 0x20
0x0000dbe8  mov  qword ptr [r12 + 0x38], 0
```

内联时走另一支：

```
0x0000dbc4  lea  rdx, [rsi + 0x10]     ; 目标 = 输出对象 +0x10
0x0000dbc8  mov  rax, [rcx]
0x0000dbcb  call qword ptr [rax + 8]   ; 虚调用 0x08（复制）
0x0000dbce  mov  [rsi + 0x48], rax
```

**这正是 MSVC `std::function` 的「内联存储 / 堆存储」双分支**
（虚槽 `+8` = 复制构造、`+0x20` = 析构，捕获成员随实现而定）。
因此它们**不是消息类型标签，而是类型擦除的可调用委托**，
换 vtable 会同时改变复制、调用、销毁与捕获成员的解释方式 —— 已验证作废。

### 15.4 三份材料

**材料一：修正后的崩溃解析**（见 15.1）—— 操作码 8 / 真实访问地址 / 完整寄存器。

**材料二：手工构造与原生构造的逐字段差异表**
（工具 `<PROJECT_ROOT>\diff_content_layout.py`，输出如下）：

```
原生内容对象样本：384 字节，控制块 vtable RVA = 0x83dcc28
+0x000 控制块 vtable = 0x7ffca743cc28
+0x008 引用计数 = 0x100000005   (_Uses=5, _Weaks=1)
+0x010 对象体 vtable = 0x7ffca77b5528
+0x018 (未命名) = 0x3

slot     off    len    cap  类型
   0 0x00020     32     47  heap      ← lib_md5
   1 0x00040      0     15  empty
   2 0x00060     32     47  heap      ← spec md5
   3 0x00080      0     15  empty
   4 0x000a0      0     15  empty
   5 0x000c0      0     15  empty
   6 0x000e0    324    335  heap      ← url 20401
   7 0x00100    322    335  heap      ← url 20403
   8 0x00120     32     47  heap      ← aux md5
   9 0x00140    324    335  heap      ← url 20402
  10 0x00170  （超出样本长度，样本仅 384 字节）
  11 0x00190  （超出样本长度）

元数据区：
  +0x160 = 0    +0x164 = 0x12    +0x168 = 0x1    +0x16C = 0
```

**结论**：
- 尾部偏移表 **一致**（slot 10 = `0x170`、slot 11 = `0x190`）
- 容量约定 **全部吻合** `cap == len | 0xF`（32→47、324→335、322→335）
- **`+0x164`/`+0x168` 是运行时状态字段**：静态工厂写的是 `+0x168 = -1`，
  而运行样本是 `+0x164 = 0x12`、`+0x168 = 1`
  ⇒ **不能把样本里的值当常量硬编码**，代码保持静态初始值 `-1` 即可
- **注意**：本样本只有 384 字节（采样时截断），尾部两项的布局依据是静态反汇编
  `ctor_3d67da0.asm`，尚无运行时字节级确认 —— 这是已知的验证缺口

**材料三：`0xDB40` 完整契约（部分恢复）**

签名：`0xDB40(rcx = 输出对象, rdx = 委托1, r8 = 委托2, r9 = 委托3, [rsp+0x20] = ?, [rsp+0x28+ …] = ?)`

输出对象**不是 16 字节的 shared_ptr 包装，而是一个 ≥ 0xE8 字节的大对象**：

| 偏移 | 内容 | 写入来源 |
|---|---|---|
| `+0x00` / `+0x08` | shared_ptr（内部 `new(0x18)`，控制块 vtable `base+0x7F5F398`） | 函数自身 |
| `+0x10` | 委托 1 的内联存储（0x40 字节） | `call [rcx_vtbl+8]` 复制 |
| `+0x48` | 委托 1 的堆指针（或内联判定） | `[rdx+0x38]` 或上述复制结果 |
| `+0x50` | 委托 2 的内联存储 | 同上 |
| `+0x88` | 委托 2 的堆指针 | 同上 |
| `+0x90` | 委托 3 的内联存储 | 同上 |
| `+0xc8` | 委托 3 的堆指针 | 同上 |
| `+0xd0` | 来自栈参数（`[rbp+0x68]`） | 调用者栈 |
| `+0xd8` | 16 字节清零 | 函数自身 |

**仍未确定**（需进一步分析）：
1. 第 6/第 7 个栈参数的具体类型与用途（`[rbp+0x60]` → `rdi`、`[rbp+0x68]` → `rbx`）
2. 输出对象的总尺寸与析构路径
3. `RAX` 返回值与原输出地址的关系（文本路径把 RAX 传给后续调用，
   原生路径直接用原输出地址，两者是否恒等尚未核对）
4. 三个委托各自捕获什么（会话 / 信封 / 控制块 / 选项）

**—— 上述第 2、3 项已补完（见下）——**

**2'. 输出对象尺寸：≥ 0xE8 字节（已确定）**

`reports/db40.asm` 中对该对象的写入分布：

```
[rsi + 0x00] / [+0x08]  shared_ptr（内部 new(0x18)）
[rsi + 0x10]            委托 1 内联存储（0x40 字节）
[rsi + 0x48]            委托 1 堆指针
[rsi + 0x50]            委托 2 内联存储（0x40 字节）
[rsi + 0x88]            委托 2 堆指针
[rsi + 0x90]            委托 3 内联存储（0x40 字节）
[rsi + 0xc8]            委托 3 堆指针
[rsi + 0xd0]            来自栈参数
[rsi + 0xd8]            16 字节清零（movups）
```

**最大写入偏移为 `+0xd8`，加上 16 字节的 `movups` 共触及 `0xE8`。**
另有 `lock dec dword [rsi + 0xc]`，印证 `+0x08` 是强引用计数、`+0x0c` 是弱引用计数
（与内容对象的引用计数布局同源）。
⇒ **输出对象不是 16 字节的 shared_ptr 包装，而是 ≥ 0xE8 字节的大对象。**

**3'. 返回值 RAX 恒等于第一参数（已确定）**

```
0x0000dd4f  mov  rax, rsi      ; rsi = 第一参数（输出对象地址）
0x0000dd52  add  rsp, 0x40
0x0000dd56  pop  rbx / rdi / rsi / r12 / r14 / r15 / rbp
0x0000dd60  ret
```

⇒ **`RAX` 就是原输出地址**。因此文本路径「把 RAX 传给 `0x160EBE0`」
与原生路径「直接传 `&out`」**完全等价**；「RAX 非零即拿到任务结果」的说法
也据此修正为「RAX 只是同一地址的回传」。

**对 send_sticker_tpl.c 的影响（已修正）**：
输出缓冲原先只有 16 字节，若 `0x16A60D0` 与 `0xDB40` 同构即会被越界写穿 arena，
破坏其后数据 —— 这与「崩在栈上地址处的坏虚调用目标」的现场一致。
现按 `0x400` 字节预留并整体清零（`OUT_SP_SIZE`）。

### 15.5 关于 `0x160DF80` 的保留意见

评审指出「带 `this` 不等于依赖可见聊天窗口」——**同意，撤回我原先的贬级判断**。
它的 `this` 可能是管理器、发送适配器或任务模型；程序化发送也可以使用后台会话模型。

**但**：其 `[rbp+0x2B0]`/`[rbp+0x2C8]` 是基于**帧指针**的访问位置，
需要结合完整序言与写入来源才能映射到入口参数；
仅凭这两个位置不足以写出可直接使用的 C 函数声明。**保留为候选，暂不放弃。**

### 15.6 修订后的推进主线

> 正确构造内容与信封 → 恢复 `0xDB40` 输出与委托契约 → 按原生契约进入 pack
> → 跟踪 `0x160EBE0` 在 `0x160EE67` 调用 `0x290390` 的实际任务交接 → 确认对端收到。

**注意**：`0x160EBE0` 不能只被命名为「纯打包构造」——它在 `0x160EE67`
还调用了 `0x290390`，所以它也不是已证明的网络终点（见 `commit_160ebe0.asm:161`）。

**暂停**：按当前签名继续尝试 `0x16A60D0`；先换未知 vtable；猜 `SetCurrentSession`。
**若同一假设两轮没有新增证据，就改追真实构造或消费代码。**

### 15.7 新增/修正的工具

| 文件 | 变更 |
|---|---|
| `parse_minidump.py` | **修正异常参数偏移**，新增崩溃线程寄存器输出（RIP/RSP/RBP/R8-R15） |
| `diff_content_layout.py` | **新增**：手工构造与原生构造的逐字段差异表 |
| `send_sticker_tpl.c` | 修正尾部 string 偏移（`wxb_slot_offset`）与容量分配（`cap+1`） |
| `reports/db40.asm` | **新增**：`0xDB40` 全文反汇编（140 条） |

---

## 十六、第二次外部复核后的修正（2026-10-13 16:53）

外部复核（`D:\Hermes work\微信收藏表情_修复后实测前契约复核_2026-10-13.md`）
指出五处问题，**经逐条核对源码与汇编，五条全部成立**。

### 16.1 纠正一：当前 `type=4` 走的仍是旧入口，不是 `0xDB40` 路线

`send_sticker_tpl.c` 的第 4 阶段仍在调用 `0x16A60D0(ctx, out_sp, env_sp)`，
**并未调用 `0xDB40`，也没有构造它的三份委托**。

⇒ 若现在实测，实验只能回答「**修正内容并移动输出位置后，旧入口调用有什么变化**」，
**不能称为「`0xDB40` 发送路线验证」**。第十五节末「材料三已完成」的表述造成了两条路线的混淆。

**结论**：`0xDB40` 与 `0x16A60D0` 是两条独立路线，必须分别标记，不可混用证据。
「给 `0xDB40` 分配足够输出空间」是正确的，但**不能由此推出 `0x16A60D0` 输出同构**。

### 16.2 纠正二：撤回「写穿 arena」的因果推论

原代码布局：`VirtualAlloc(NULL, 0x2000)`，`env_sp = arena+0x000`、
`content_sp = arena+0x100`、`out_sp = arena+0x200`。

**若向 `out_sp` 写 `0xE8` 字节，结束于 `arena+0x2E8`，远小于 `arena+0x2000`**
—— 物理上根本没有越界。

⇒ **「仅因写 0xE8 便写穿 arena」不成立，该推论撤回。**
「逻辑上把输出当 16 字节」确实是类型契约错误，但它与「坏虚调用」之间的因果链
**尚未建立**；需要先找到真实写入范围与被破坏字段。

（新代码把 `out_sp` 移到 `+0x800` 并清零 `0x400`，且此前已清零整个 arena，
所以它本身也不能证明「曾缺失可写空间」。）

### 16.3 纠正三：`0xDB40` 的参数编号是 5/6，不是 6/7

`0xDB40` 序言为 7 次 `push` + `sub rsp,0x40` + `lea rbp,[rsp+0x40]`。
设 **S = 被调函数刚进入时的 RSP**，则 **`RBP = S - 0x38`**。于是：

| 机器参数 | 位置（入口视角） | 等价（RBP 视角） | 已见行为 |
|---|---|---|---|
| 1 | RCX | — | 输出对象；正常返回时 `RAX = RCX` |
| 2 | RDX | — | 委托 1 |
| 3 | R8 | — | 委托 2 |
| 4 | R9 | — | 委托 3 |
| **5** | **S + 0x28** | **RBP + 0x60** | **按 `{ptr, ctrl}` 读取；非空时 retain 并替换输出首个 shared_ptr** |
| **6** | **S + 0x30** | **RBP + 0x68** | **其 64 位值写入输出 `+0xD0`** |

**第十五节把它写成「第 6/7 参数」是错的**，此处更正。
第五项的结构行为已明朗（智能指针语义），第六项的业务含义仍未知
（**不能默认它是可随意清零的选项**）。

### 16.4 纠正四：输出 `+0x08` 存的是控制块指针，不是引用计数

`lock dec dword [rsi + 0xc]` 出现在 **`0xdd70` 之后的另一段代码**中，
该处的 `rsi` **已被重新赋成控制块地址**。

⇒ **输出 `+0x08` 存的是控制块指针**，不应描述成「输出自身 `+8`/`+0xC` 直接存引用计数」。
第十五节材料三的措辞据此更正。

### 16.5 纠正五：尾部 string 的 16 字节 buf 未清零（已修复）

`memset(block+0x18, 0, 0x158)` 只覆盖 `[0x18, 0x170)`，
而尾部两项的 buf（`0x170..0x17F`、`0x190..0x19F`）**不在其中**；
`operator new` 返回的存储不保证清零，原生工厂对这 16 字节是**显式清零**的。

**已修复**：初始化循环现在同时写 `buf[0..15] = 0`、`len = 0`、`cap = 0xF`。

**同时更正对 `diff_content_layout.py` 的定位**：它主要打印旧原生样本、
并把自定义偏移表与常量比较，**并未读取新手工构造的对象，也未证明新旧对象逐字段相等**。
它能展示布局依据，**不能替代真正的对象差异核验** —— 这是当前材料链的缺口。

### 16.6 新增材料四：`0x16A60D0` 的输出写入范围（≈0x38，与 DB40 不同构）

按复核建议补测。`0x16A60D0` 入口处 `mov rsi, rdx`（`rsi` = 第 2 参数 = `&out`），
对 `rsi` 的全部写入（`reports/send_entry_16a60d0.asm`）：

```
0x016a66fd  mov    qword [rsi], rax
0x016a6707  movups xmm  [rsi + 0x18], xmm0
0x016a68f7  mov    qword [rsi + 0x18], rdi
0x016a68fb  mov    qword [rsi + 0x20], 0xf
0x016a6aa5  mov    qword [rsi + 0x18], rdi
0x016a6aa9  mov    qword [rsi + 0x20], r14
0x016a6ac1  movups xmm  [rsi + 0x28], xmm0
0x016a6ae7  mov    qword [rsi + 0x28], rax
0x016a6aeb  mov    qword [rsi + 0x30], rdi
```

**最大写入偏移为 `+0x30`；`+0x28` 处的 `movups` 触及 `+0x38`。**

| | `0xDB40` | `0x16A60D0` |
|---|---|---|
| 输出最小覆盖 | `0xE8` | **`0x38`** |
| 输出结构 | shared_ptr 头 + 三份委托 + `+0xd0` | 指针 + 一个 std::string（buf@`+0x08`, len@`+0x18`, cap@`+0x20`）+ `+0x28` |
| 返回值 | `RAX = 第一参数` | 尚未核对 |

⇒ **两者输出不同构，「同构即越界」的假设被证伪**；但 `0x38` 仍大于原先的 16 字节，
说明**输出缓冲确实应当放大**（现已 `0x400`），只是**这不能解释旧崩溃**。

### 16.7 三个委托是「被转移并消耗的输入」（补充第十五节）

`0xDB40` 对堆实现**直接转移指针**；对内联实现**调用虚槽 `+8` 在输出内联区建立目标**，
随后**销毁源实现并清零源 `+0x38`**（`mov qword [r12+0x38], 0` 等）。

⇒ **不是保留源对象不变的普通复制，而是移动语义**；
**每次任务都必须有合法的所有权来源**。
MSVC STL 对应槽位候选：`+8` = Move、`+0x20` = Delete_this
（仍应以本机虚函数实际行为确认）。

### 16.8 修订后的下一步

**优先补的唯一材料**（复核指定）：

> `0x16A60D0` 的完整输出写入范围（✅ 已完成，见 16.6），
> 以及**原生调用前 RCX/RDX/R8/栈参数的数据流**；
> 尤其 **R8 包装中的 `_Ptr` 实际类型及必要成员**；
> 说明**哪个间接调用最终产生了旧 dump 中的栈地址目标**。

**两条路线必须分开标记**：

- **路线 β（旧入口）**：继续走 `0x16A60D0`。需要先补上「`R8` 包装的 `_Ptr` 真实类型」。
- **路线 γ（`0xDB40`）**：按已确认的**六参形式**恢复三份完整委托与第五项包装，
  再沿 输出 → pack → `0x290390` 追实际任务消费。

**不得**把仍调用旧入口的 `type=4` 当作新路线验证；
**不得**在没有唯一假设与结果记录的情况下做诊断实验（成功仍以对端收到为准）。

---

## 十七、材料五：真实对象差异核验（2026-10-13 16:55，已实测）

外部复核指出「已有差异表只打印旧原生样本，从未读取新手工构造的对象」。
本节补上这一环：**在微信进程内真正构造出对象、落盘、再与原生样本逐字段比对**。

### 17.1 新增零风险取证通道 `type=5`

`send_sticker_tpl.c` 新增 `wxb_dump_content_tpl(tpl_index)`：
**只构造内容对象并 dump 成十六进制，不调用任何发送入口**，因此无副作用风险。
`outbox.c` 增加 `type=5` 分支：

```
<seq>\t5\t-\t<模板号>
```

产出两个文件（`bridge\control\`）：
- `content_built.hex` —— 对象的 `0x1B0` 字节十六进制
- `content_built.txt` —— 该模板的 6 个字段与长度，便于确认构造的是预期模板

核验工具：`<PROJECT_ROOT>\verify_built_content.py`（读取上述 hex 与 `sticker_precise.json`
的原生样本，逐字段比对）。

### 17.2 核验结果：逐字段一致

实测命令 `type=5` + `tpl=0`，**微信进程未崩溃**。

```
新构造对象: 432 字节 (= 0x1B0)
构造参数: tpl=0  lib_md5=0fbdd73cc59f210845f4d2457b0167b8
          spec_md5=9558c0a6b75d4821b7b68c2eecb19eac
          aux_md5=8cbd585dba8bb6cc4d5c0a7ccfead51d
          url 长度 = 324 / 322 / 324

控制块 vtable   新=0x7ffca743cc28  旧=0x7ffca743cc28  [一致]
对象体 vtable   新=0x7ffca77b5528  旧=0x7ffca77b5528  [一致]

slot     off   新 len  旧 len  新 cap  旧 cap  判定
   0 0x00020     32     32     47     47  一致  (heap/heap)
   1 0x00040      0      0     15     15  一致  (empty/empty)
   2 0x00060     32     32     47     47  一致  (heap/heap)
   3 0x00080      0      0     15     15  一致  (empty/empty)
   4 0x000a0      0      0     15     15  一致  (empty/empty)
   5 0x000c0      0      0     15     15  一致  (empty/empty)
   6 0x000e0    324    324    335    335  一致  (heap/heap)
   7 0x00100    322    322    335    335  一致  (heap/heap)
   8 0x00120     32     32     47     47  一致  (heap/heap)
   9 0x00140    324    324    335    335  一致  (heap/heap)
  10 0x00170  （旧样本未覆盖，布局依据为静态反汇编）
  11 0x00190  （旧样本未覆盖，布局依据为静态反汇编）

尾部两项 16 字节 buf（外部复核关注点）：
  slot 10 @ 0x170: buf = 00…00  [已清零]
  slot 11 @ 0x190: buf = 00…00  [已清零]

元数据区（运行时状态，不参与判定）：
  +0x160 新=0x0          旧=0x0
  +0x164 新=0x0          旧=0x12
  +0x168 新=0xffffffff   旧=0x1
  +0x16C 新=0x0          旧=0x0

总体结论：逐字段一致
```

**三点说明**：

1. `+0x008`：新对象 `0x100000001`（`_Uses=1`）、原生 `0x100000005`（`_Uses=5`）
   —— 这是引用计数，**运行时差异，非构造差异**。
2. `+0x164`/`+0x168`：新对象是静态初值（`0` / `-1`），原生是运行时值（`0x12` / `1`）
   —— 证实**这两个字段由运行时改写**，不能硬编码。
3. **`0x1B0` 内容对象的构造现已具备完整证据链**：
   静态工厂反汇编 + 运行时逐字段核验，且尾部 buf 已按原生方式清零。

### 17.3 当前证据状态总览

| 环节 | 状态 |
|---|---|
| 内容对象（`0x1B0`）构造 | ✅ **已完成核验**（静态 + 运行时逐字段一致） |
| 信封（`0x698`）构造 | ✅ 布局与工厂已验证（运行时命中） |
| 7 套表情模板 | ✅ 已采集固化为 C 头文件 |
| `0xDB40` 契约 | 🟡 六参数已定、输出 ≥`0xE8`、`RAX=参数1`、委托为**移动语义**；**委托捕获成员未解** |
| `0x16A60D0` 契约 | 🟡 输出 ≈`0x38`（与 DB40 **不同构**）；**`R8` 包装的 `_Ptr` 真实类型未解** |
| 实际发送 | ❌ **未打通**（成功仍以对端收到为准） |

### 17.4 下一步（复核指定的唯一材料）

> **原生调用前 RCX/RDX/R8/栈参数的数据流**；
> 尤其 **`R8` 包装中的 `_Ptr` 实际类型及必要成员**；
> 说明**哪个间接调用最终产生了旧 dump 中的栈地址目标**。

对应手段：在 `0x165B8C3`（`0x16A60D0` 的真实调用点）处 hook 并 dump
`rcx` / `rdx` / `r8` 及其指向对象，与 `0x16A77E0` 内部的 `r8` 交叉比对，
确定上层传入的 `R8` 究竟是「信封」还是「请求/任务上下文」。
（档案第十五节已记录：`0x16A60D0` 采集记录只保存了 R8 指向的包装内存，
未完整证明包装中的 `_Ptr` 是 Envelope；更下层采样出现的是 vtable `0x865DEC8` 的对象。）

---

## 十八、决定性发现：`0x16A60D0` 的 R8 应为「任务上下文」，不是信封（2026-10-13 17:04）

### 18.1 实测证据

用 `frida_dump_send_args.py` hook `0x16A60D0` 真入口，实测一次真实发送：

```
[send_entry] caller_rva = 0x165b8c8
  rcx = 0x1f58b157980        → 类型：发送上下文 ctx（vtable 0x82C74F8）✅ 扫描定位正确
  rdx = 0xa4041feff0         （栈地址，指向输出缓冲）
  r8  = 0xa4041fefa0         （栈地址，指向一个 shared_ptr）

── R8 作为 shared_ptr 解引用 ──
    _Ptr = 0x1f58d277110
    _Rep = 0x1f58d277100
    _Ptr.vtable RVA = 0x865dec8
    ★ 类型 = 【请求 / 任务上下文】，不是信封
```

**结论**：`0x16A60D0` 的第三个参数要的是
**`&shared_ptr<TaskContext>`（vtable `0x865DEC8`）**，
而我此前一直传 `&env_sp`（信封，vtable `0x82CB8D8`）。

**这就是调用即崩的直接原因** —— 传入对象的类型根本不对。

交叉印证：`TaskContext` 在 `+0x08`/`+0x10` 处**持有信封的 shared_ptr**
（与 `submit_capture.json` 里 `env = 0x1f9a9b6db60` 完全吻合），
说明它是**包裹信封的任务对象**，而非信封本身。

### 18.2 TaskContext 的构造已经定位

**基类构造函数 `0x34EC620`**，签名 `(rcx = this, rdx = &shared_ptr<Envelope>, r8d = flags)`：

```
0x034ec641  mov  ebx, r8d
0x034ec644  mov  r8, rcx                ; r8 = this
0x034ec647  lea  rax, [rip + 0x517187a] ; → vtable 0x865DEC8
0x034ec64e  mov  [rcx], rax
0x034ec654  movups [rcx + 8], xmm0      ; this+8..0x18 清零
0x034ec658  mov  rax, [rdx + 8]         ; 参数2._Rep
0x034ec661  lock inc dword [rax + 8]    ; 引用计数 ++
0x034ec670  mov  [r8 + 8], rax          ; this+0x08 = env._Ptr
0x034ec67c  mov  [r8 + 0x10], rax       ; this+0x10 = env._Rep
```

**它不自己分配内存**（`this` 由调用者提供），只写入 vtable 与信封 shared_ptr。
**调用者共 6 处**，其中 `0x34F0AC0` 在函数 `[0x34f0a70, 0x34f0d5b)`（747 字节）内。

**派生类构造 `0x34F0A70`**，签名 `(rcx = this, rdx = &shared_ptr<Envelope>)`：

```
0x034f0a92  mov  rax, [rdx + 8]
0x034f0a9b  lock inc dword [rax + 8]     ; 参数2 引用 ++
0x034f0aaa  mov  [rbp - 0x50], rcx       ; 栈上组出 shared_ptr 副本
0x034f0ab2  lea  rdx, [rbp - 0x50]
0x034f0ab9  xor  r8d, r8d
0x034f0ac0  call 0x34EC620               ; ← 基类构造
0x034f0ac6  lea  rax, [rip + 0x516d423]  ; → vtable 0x865DEF0（★ 派生类）
0x034f0ad1  mov  [rsi], rax              ; 覆盖 this[0] 为派生类 vtable
```

⇒ **两段式构造**：`0x865DEC8` = 基类 vtable、`0x865DEF0` = 派生类 vtable。
之后该函数继续做了多次分配（`new(0x2A0)` @ `0x34f0afe`、
`new(0x140)` @ `0x34f0b78` 等），构造链更深。

### 18.3 对两条路线的影响

**路线 β（`0x16A60D0`）的正确调用形态应是**：

```
task = 创建 TaskContext（包裹 env_sp）
0x16A60D0(ctx, &out, &shared_ptr<TaskContext>)
```

**而不是** `0x16A60D0(ctx, &out, &env_sp)`。
构造 TaskContext 需要走 `0x34F0A70`（或其等价路径），**且必须提供合法的 shared_ptr 所有权来源**。

**同时**：`0x165B2B0`（通用发送）的 `rcx` 类型在本轮也被实测确认为
**发送上下文 ctx（vtable `0x82C74F8`）**，与 `0x16A60D0` 的 rcx 是**同一个对象**
（两次 `generic` 采集都命中同一类型），这进一步支持「ctx 是持久服务对象」的判断。

### 18.4 当前状态与下一步

| 项目 | 状态 |
|---|---|
| 内容对象构造 | ✅ 已完成核验（静态 + 运行时逐字段一致，见第十七节） |
| 信封构造 | ✅ 布局与工厂已验证 |
| 发送上下文 ctx | ✅ 可运行时扫描定位（vtable `0x82C74F8`） |
| **真入口 R8 的真实类型** | ✅ **本轮确定：`TaskContext`（vtable `0x865DEC8`）** |
| TaskContext 完整构造 | 🟡 基类 `0x34EC620` 已解；**派生路径 `0x34F0A70` 的多次分配与入参来源未解** |
| 实际发送 | ❌ 未打通 |

**下一步（唯一目标）**：恢复 `0x34F0A70` 的**入参来源与完整分配序列**，
即「谁创建 TaskContext 的 `this`、谁提供 `&shared_ptr<Envelope>`」。
拿到它就能按原生形态组装 `(ctx, &out, &task_sp)` 并真正驱动发送。

**核对要点**：`0x34F0A70` 的 `this` 是 `0x34EC620` 的就地构造目标，
其大小应从派生类的析构路径（`0x34F1299` 读 `[rcx+0xd8]`）与
`new` 序列共同确定，**不能沿用内容对象的 `0x1B0` 或信封的 `0x698` 尺寸猜测**。

---

## 十九、架构级根因：发送链依赖线程局部存储（TLS），不能在自建线程上调用（2026-10-13 17:08）

### 19.1 TaskContext 的完整构造参数已确定

由唯一调用者 `0x33FA754`（函数 `[0x33fa490, 0x33fb4fd)`）处的原生形态：

```
0x033fa6f5  mov  ecx, 0xf0
0x033fa6fa  call 0x64a7d1c              ; operator new(0xF0)   ← TaskContext 总大小
0x033fa703  mov  [rdi + 8], rbx         ; refcount = 0x100000001
0x033fa707  lea  rax, [rip + 0x525390a] ; → 控制块 vtable 0x864E018
0x033fa715  mov  [rdi], rax
0x033fa738  add  rdi, 0x10              ; body = block + 0x10
0x033fa754  call 0x34F0A70              ; 构造 TaskContext
0x033fa761  mov  [rax + 0x178], rdi     ; 存入父对象 +0x178 / +0x180
```

**精确 RVA（用 `wxdis.py` 解析 RIP 相对地址，非手算）**：

| 项 | RVA | 验证 |
|---|---|---|
| 基类 vtable | `0x865DEC8` | **与 frida 运行时实测逐位一致** ✅ |
| 派生类 vtable | `0x865DEF0` | 与基类相邻，间距 `0x28` |
| 控制块 vtable | `0x864E018` | 由 `0x33fa707` 处 lea 解析 |
| TaskContext 总大小 | `0xF0`（body `0xE0`） | 与析构路径读 `[rcx+0xd8]` 吻合 ✅ |

### 19.2 按此参数构造仍然崩溃 → 暴露真正的根因

按上述参数实现 `type=6`（只构造不发送，零风险），结果**微信崩溃**：

```
异常码   : 0xC0000005
操作码   : 0（读取）
访问地址 : 0x388          ← 几乎为 0
崩溃地址 : Weixin.dll + 0x39B99E
```

**崩溃点的汇编**（`0x39B8F0`，函数 `[0x39b8f0, 0x39b9d6)`）：

```
0x0039b8f6  mov  eax, [rip + 0xa1952a4]   ; TLS 索引（槽位在 0xA530BA0）
0x0039b8fc  mov  rdx, gs:[0x58]           ; TEB -> ThreadLocalStoragePointer
0x0039b905  mov  rax, [rdx + rax*8]
0x0039b909  mov  rdx, [rax + 0x1f0]       ; ★ 当前线程的服务对象（TLS）
0x0039b910  test rdx, rdx
0x0039b913  je   0x39b995                 ; 为空 → 走清理分支
...
0x0039b995  xorps xmm0, xmm0
0x0039b998  movups [rcx], xmm0            ; 清零输出 shared_ptr
0x0039b99b  mov  rax, [rcx]               ; rax = 0
0x0039b99e  cmp  dword [rax + 0x388], 3   ; ★ 崩溃：读 [0 + 0x388]
```

### 19.3 结论：调用线程错误，而非参数错误

`0x39B8F0` 是一个**从 TLS 取「当前线程服务对象」的通用工具**（**被 143 处调用**）。
它假定调用线程的 TLS 槽 `[+0x1f0]` 已被初始化。

**我们的 worker 线程是自建的，从未初始化该 TLS 槽** ⇒ `rdx = 0` ⇒ 走清理分支
⇒ 随后读 `[0 + 0x388]` 崩溃。

**这条链的本质**：
- 不是内容对象构造错（已逐字段核验，见第十七节）
- 不是信封错（工厂与布局已验证）
- 不是 TaskContext 尺寸/参数错（本轮已按原生形态复原）
- **而是「发起调用的线程不对」** —— 微信的发送链要求运行在**已初始化 TLS 的微信线程**上

**这同时解释了此前所有失败的共同特征**：
`0x16A60D0`、`0x16A77E0`、`0x34F0A70` 乃至更早的种种崩溃，
很可能都源于同一个「线程上下文缺失」，而非各自的参数问题。

（早先「fiber 栈」的猜测方向接近但说法不准：**真正缺的是 TLS 服务对象**，
不是 fiber 栈 —— 因 `Rsp` 经栈回溯已证实是我们自己的线程栈。）

### 19.4 可行的修复方向

**微信线程是现成可用的**：我们的 DLL 本就用 `SetWindowsHookExW(WH_GETMESSAGE)`
装了 hook，其回调 `WxGetMsgHook`（`lifecycle.c`）**就跑在微信的消息线程上**，
而且它**已经在调用 `poll_outbox()`**：

```c
__declspec(dllexport) LRESULT CALLBACK WxGetMsgHook(int code, WPARAM wparam, LPARAM lparam) {
    if (code >= 0 && wxb_paths_ready() && InterlockedCompareExchange(&g_worker_active, 0, 0)) {
        if (!file_exists(STOP_FILE)) {
            if (wxb_weixin_module() && !recv_hook_installed()) install_recv_hook();
            if (wxb_weixin_module()) poll_outbox();     // ← 已在微信线程上
        }
    }
    return CallNextHookEx(NULL, code, wparam, lparam);
}
```

**问题**：worker 线程（自建）**也在**调 `poll_outbox()`，
两者由 `g_processing` 互斥，**谁先抢到谁执行** —— 若 worker 先抢到就会崩。

**改造方案**：
1. **worker 线程不再直接执行发送**，只负责装 hook 与保活；
2. 发送统一由 `WxGetMsgHook`（微信线程）执行；
3. 为避免「没有窗口消息就不触发」，worker 在检测到 outbox 有待处理内容时，
   用 `PostMessage` 向微信窗口投一条 `WM_NULL` 唤醒消息线程；
   窗口句柄通过 `EnumWindows` + `GetWindowThreadProcessId` 匹配本进程获得。

**风险点**：hook 回调有严格的时间限制（系统会因超时摘除 hook），
因此发送逻辑必须足够快，或在回调内触发而非同步完成。

### 19.5 当前状态

| 项目 | 状态 |
|---|---|
| 内容对象构造 | ✅ 已核验（静态 + 运行时逐字段一致） |
| 信封构造 | ✅ 已验证 |
| TaskContext 参数 | ✅ 已复原（大小 `0xF0`、vtable `0x864E018`、ctor `0x34F0A70`） |
| 发送上下文 ctx | ✅ 可运行时扫描定位 |
| **调用线程** | ❌ **当前在自建 worker 线程上调用 → TLS 未初始化 → 崩** |
| 实际发送 | ❌ 未打通 |

**下一步**：实施 19.4 的线程改造（worker 只保活、发送移到微信线程），
再重测 `type=6`（仍然只构造不发送）验证 TLS 假设 ——
若 `type=6` 在微信线程上不再崩溃，则证明根因判断正确，随后即可推进 `type=4` 真实发送。

---

## 二十、第十九节被推翻 + 真实发送链完全解析（2026-10-13 18:13–18:55）

本节全部结论都来自**运行时实测**（frida 抓取用户真实发送 + 我们自己的构造），
不是静态推断。凡与旧节冲突，以本节为准。

### 20.1 第十九节的 TLS 归因被证伪

新增的两个诊断通道（`type=7` 重扫、`tls_threads.txt`）给出硬数据：

```
total=114  with_service=0
```

**进程内 69–114 个线程，无一持有 `[tls+0x1F0]` 服务**，包括微信窗口/消息线程。
更关键的是：**执行文本发送（已知可用）的 worker 线程，在其前后 TLS 状态都是
`service_0x1f0=0`**（`tls_report.txt` 的 `pre_exec` / `post_exec` 对照）。

⇒ **该 TLS 服务与发送能力无关**；`0x39B8F0` 在空服务时必然崩（`out=null` 后
仍执行 `cmp [rax+0x388]`），说明**自然发送根本不会调用它**。
第十九节"微信线程有服务、把工作挪过去即可"的判断据此作废；
`lifecycle.c` 的 hook 通道保留（它确实是可用的微信消息线程入口），
但不再是发送前置条件。

### 20.2 真实调用链（frida 抓取，用户手动发送收藏表情）

```
0x83D5D0  投递任务到调度器
  └ 0x262100（调度器）
     └ 0x8E07B0  发送逻辑（虚函数，rcx 是 this 调整量 0/1）
        └ 0x262100（二级调度）
           └ 0x1B13808
              └ 0x1AFD280
                 └ 0x160DCD0
                    └ 0x160DF80  emoji_ctor ★实测入口
                         ├ 0xDB40     构造任务配置 cfg
                         └ 0x160EBE0  pack 投递
```

命中证据（`reports/frida_hits.txt`，均为 tid=28800 / 16332 窗口线程）：

```
env_factory tid=28800 rcx=… rdx=… r8=… r9=0x14
emoji_ctor  tid=28800 rcx=0x40cb6fa600 …
db40        tid=28800 rcx=0x40cb6fa150 rdx=0x40cb6fa040 r8=0x40cb6fa000 r9=0x40cb6f9fc0
pack        tid=28800 rcx=0x1e5a2e6b560 rdx=0x40cb6fa150 models=1
```

注意 `pack` 的 `rdx` 恰是 `db40` 的 `rcx`（`0xDB40` 返回参数1）。

### 20.3 决定性对照：三个模型的逐字段差异

`reports/frida_pack_models.txt` + `compare_pack_models.py` / `compare_content.py`：

| 对象 | 结论 |
|---|---|
| 信封（pack 元素） | vtable `0x82CB8D8`，与原生**仅地址不同**；`+0x0C0/0x0C8` 是 wxid 长度/容量（因目标不同） |
| 内容对象 `0x1B0` | 12 个 std::string 槽 **len/cap 全部一致**（324/322/32 …） |
| 内容对象整数字段 | 差异 3 处，**已修正**：`+0x018`=3、`+0x160`=0x12<<32、`+0x168`=5（旧静态值 0/0/-1） |
| **cfg（`0xDB40` 输出）** | **完全不同 —— 最终卡点** |

**重要更正**：`pack` 的元素就是**信封**，不是"消息模型"。
微信自身发表情走的是 envelope 路径；文本路径之所以能用"消息模型"
（vtable `0x805E578`，由 `0x6A35B0` 写入），是因为**文本发送恰好走那条路**。

### 20.4 cfg 结构（`0x160EBE0` 的 rdx，由 `0xDB40` 填）

```
+0x00/+0x08  shared_ptr  ← 第 5 参数（或 0xDB40 内部 new(0x18) 块）
+0x10..+0x4F 委托 #1   (+0x48 = self/数据指针)
+0x50..+0x8F 委托 #2   (+0x88)
+0x90..+0xCF 委托 #3   (+0xC8)
+0xD0        第 6 参数（64 位标量）
```

**委托有两组，这是 type=8 之前失败的直接原因**：

| | 文本组（`wxb_send_text` 在用） | 信封组（表情） |
|---|---|---|
| d1 | `0x83661E8` | **`0x83677E8`** |
| d2 | `0x8366068` | **`0x8367888`** |
| d3 | `0x8366128` | **`0x8367928`** |

两组都是**空捕获的内联 std::function**（内联存储为 `0xAA`，`+0x38` 为自指针），
所以换 vtable 是必要且充分的委托侧修正 —— 已加入 `WX_OFF_STK_HC1/2/3`。

### 20.5 最终卡点：第 5 参数是微信内部的发送任务上下文

换用信封组委托后 `type=8` **导致微信崩溃**（此前用错组时是"静默不送达"），
证明委托确实被调用并使用了第 5 参数。

frida 下探该对象的层次（`reports/frida_cfg.txt`）：

```
p5_ptr=0x2d1faa20f50  p5_rep=0x2d1faa20f40
p5_ctrl_vt=0x7f5f398                      ← 与 0xDB40 内部 new(0x18) 同类型
p5_body[0] = 0x2d1fbde5d00                ← 普通指针
  └ body[0]+0x00 = 0x2d1fb8c6d80 …
  └ lvl2 内含循环引用（指回上级）、小整数（0x3E、0x1c10bd4）等
```

⇒ 该对象是**每次发送新建、多层嵌套、含自引用的发送任务上下文**，
**无法手工伪造**；`0xDB40` 在参数5 为 NULL 时退化为内部空块（body[0]=0），
而信封组委托要求它非空 —— 这正是崩溃点。

**参数6**：原生为 `0xd0b`（3339），来源是 `0x160DF80` 的某个入参
（`0x160E281: mov rbx,[rbp+0x2b8]` → `[rsp+0x20]`，即**调用者的第 6 个参数**）。

### 20.6 附带产出的静态资产

- **消息模型 vtable ↔ 构造器映射表**（`find_vtable_loaders.py`）：
  `0x805E088/0x128/0x1C8/0x268/0x308/0x3A8/0x448/0x4E8/0x578/0x708/0x768/
   0x7B8/0x848/0x8D8/0x978/0xA18/0xAB8/0xB58/0xBE8/0xC78/0xD18/0xDB8`
  共 22 个 vtable，各有一处 `lea` 写入点；A 组构造器在 `0x6Axxxx`，
  B 组在 `0x63xxxx`。文本模型 = `0x6A35B0 → 0x805E578`。
  （注意其中部分写入点是**清理/重置**函数，会 `free` 字符串缓冲，勿误用为构造器。）
- **TLS 索引槽 `0xA530BA0` 有 2868 处引用** → 它是全库通用的线程局部上下文入口，
  不是"发送服务"。
- 表情存储相关字符串：`0x07F61110`（`*.db / emoticon / favorite / sns`）、
  `0x0813FB59`（`PersistenceStore…EMOTICON`）；表情消息字段表
  `idbuffer / cdnurl / encrypturl / rewardtips` 在 `0x08426A78`。
- aixed 的 `SendCustomEmotion`（8 参数）参考实现见
  `ref\wxhelper_ReZeroS\src\manager.cc:1090`：
  `f(mgr, &path, temp, &recv, 2, temp, 0, temp)`，其 3.9.x 偏移 `0xec0a40`
  **不适用于 4.1.9.23**。

### 20.7 修正后的结论与唯一可行方向

| 项目 | 状态 |
|---|---|
| 文本发送 | ✅ 生产可用 |
| 接收/唤醒/诊断通道 | ✅ 可用（`WH_GETMESSAGE` 回调在窗口线程） |
| 信封构造 | ✅ 与原生逐字段一致 |
| 内容对象构造 | ✅ 与原生逐字段一致（含本轮 3 处修正） |
| pack 投递 | ✅ 可达（文本与表情路径均已实测命中） |
| 委托 vtable | ✅ 已确定信封组 |
| **发送任务上下文（第 5 参数）** | ❌ **无法手工伪造** |

⇒ **不能再走"手工拼装内部对象"的路线**。
唯一可行方向是**调用微信自身的发送入口**，让微信自己构造任务上下文，
而该入口位于 UI/调度层（`0x83D5D0` → `0x262100` → `0x8E07B0` → …），
其参数同样包含消息对象与会话上下文 ——
下一步应从这里继续上溯，找到**参数最少、可由"当前会话 + 表情标识"驱动**的那一层。

### 20.8 工程侧落地

- `lifecycle.c`：`wxb_write_tls_report` / `wxb_scan_threads_tls`（诊断，零风险）
- `send_sticker_tpl.c`：`wxb_send_sticker_pack`（pack 路线，含信封组委托与 3 处字段修正）
- `outbox.c`：新增 `type=7`（重扫线程 TLS）、`type=8`（pack 路线发送）
- 新工具：`find_tls_index_xref.py`、`find_tls_1f0.py`、`find_str.py`、
  `find_vtables.py`、`find_vtable_loaders.py`、`frida_probe_hits.py`、
  `frida_deep_dump.py`、`frida_cfg_dump.py`、`frida_hook_ctors.py`、
  `parse_pack_models.py`、`compare_pack_models.py`、`compare_content.py`、
  `compare_cfg.py`

**运维铁律（本轮用血换的）**：注入前**必须清空 `bridge\outbox\next.txt`** ——
残留命令会被新 worker 立即执行，粘性命令会导致微信崩溃（18:14 那次即为此因）。

---

## 二十一、图片消息通道打通（2026-10-13 19:25–19:35）

### 21.1 外部评审四点的核实结果

外部复核（`D:\Hermes work\微信收藏表情_第二十节与图片路线复核_2026-10-13.md`）提出四点，
**逐条用脚本核对原始 hex 后，四点全部或部分成立**：

| # | 评审意见 | 核实结论 |
|---|---|---|
| 1 | 图片字段坐标混用 raw/body | ✅ **成立**。`parse_cfg_models.py` 证实（body 坐标）：`+0xD0=1`、`+0xD8=3`、`+0xE0=堆指针`、`+0xE8=0`、`+0xF0/+0xF8=0x69/0x6F`。第二十节的手工解析整体错了一个 qword；且「脚本因 `0xE8` 为零而跳过」是**取值**而非越界异常 |
| 2 | 第 5 参数未证明是复杂上下文 | ✅ **成立**。`0xDB40` 默认块为 `new(0x18)`，控制头 0x10 之后仅 8 字节且只写 1 字节；此前「多级嵌套、含自引用」是把填充与邻接堆内存误当成员。**该对象结构未定，不可据此断言不可伪造** |
| 3 | `type=8` 漏传第六参数 | ✅ **成立**。旧调用只传 5 个；六参数已由 `0xDB40` 入口实测确认，原生 `p6` 为**递增计数**（0xf4b…0x1050，非固定 0xd0b） |
| 4 | 委托顺序与文本代码不同 | ✅ **成立**。实测顺序 `d1=0x83661E8、d2=0x8366128、d3=0x8366068`；旧文本代码用 `(HC1, HC3, HC2)` 反了（文本恰好也能发，但不宜沿用到其它类型） |

### 21.2 三类模型的确定性字段对照（脚本产出，非手工）

`compare_three_models.py`，以 **pack 元素 body**（`_Ptr`）为坐标原点：

| body 偏移 | TEXT(我们) | IMAGE(原生) | STICKER(原生) | 结论 |
|---|---|---|---|---|
| `+0x000` | `0x805E578` | `0x82CB658` | `0x82CB8D8` | 三者不同族 |
| `+0x0B0` | `filehelper` 内联 | 同 | 堆指针 | 接收方 wxid |
| `+0x0C0 / +0x0C8` | 10 / 15 | 10 / 15 | 19 / 31 | 字符串 len / cap |
| `+0x0D0` | 0 | **1** | 0 | 图片特有标志 |
| `+0x0D8` | **1** | **3** | **0x2F** | ★ **消息内容类型码** |
| `+0x0E0` | 0 | **堆指针** | 0 | ★ 图片内容 |
| `+0xF0 / +0xF8` | 0 / 7 | 105 / 111 | 0 / 7 | 图片特有 |

⇒ **`+0xD8` 即内容类型码**，且 **block 坐标 +0xE8 = body +0xD8** ——
`wxb_send_model` 写类型码的位置本来就是对的。

### 21.3 图片模型的内容对象

图片块 `model0_+0xE0` 指向的数据是一段 **UTF-16LE 字符串**：

```
4300 3a00 2f00 5500 7300 6500 7200 7300 ...  =  "C:\Users\api62\Pictures\Screenshots\..."
```

⇒ **图片消息的内容就是"文件路径"本身**（不是内容对象、不是 XML）。

### 21.4 实现与实测结果

新增 `wxb_send_image_model_ex(wxid, path_utf8, type_code, flag_d0)`：

1. 用 `0x6A35B0` 造出与文本同构的模型骨架（已验证可用）；
2. 把对象体 vtable 覆盖为 `0x82CB658`（与原生构造器 `0x1702E50` 一致）；
3. 填入 `block+0xE0=flag_d0`、`block+0xE8=type_code`、
   `block+0xF0=宽字符串指针`、`block+0x100/+0x108=字符数`；
4. 委托改用**实测顺序** `HC1/HC2/HC3`；
5. `0xDB40` 按 **6 参数**调用（`p6 = GetTickCount() & 0xFFFF`）。

**实测验收**（用户逐个确认）：

| 用例 | 类型码 | 结果 |
|---|---|---|
| 本地 PNG 截图 | 3 | ✅ **送达，正常显示** |
| 自制三帧动画 GIF | 3 | ⚠️ 送达，但**只显示首帧（静态）** |
| 同一 GIF | 47 | ❌ **不送达** |

⇒ 结论：
- **图片通道（类型码 3）已完全打通**，任意本地图片可程序化发送；
- **GIF 走图片通道会被静态化** —— 微信按类型码 3「图片」处理，只取首帧；
- **类型码 47 不被图片模型接受** —— 动画表情必须走信封路径（vt `0x82CB8D8`），
  即第二十节那条仍未打通的链。

### 21.5 同时被实测否定的一个顾虑

评审第 4 点曾提示「同族虚表不足以证明整个文本发送骨架可复用」。
实测表明：**图片模型（vt `0x82CB658`，基类 `0x805E708`）直接复用文本骨架 +
文本组委托 + pack 即可送达** ⇒ 同族骨架复用成立。
但该结论**只对** `0x805Exxx` 族成立；信封族（`0x82CBxxx`）此前的失败不能由它推翻。

### 21.6 新增/更新工具与命令

- 命令：`type=10`（图片模型，固定类型码 3）、
  `type=11`（图片模型，`content = "<type_code>\t<path>"`）
- 新脚本：`parse_cfg_models.py`、`compare_three_models.py`、
  `frida_cfg_dump.py`（已扩为同时抓 pack 元素、`+0xE0` 内容、`0xDB40` 六参数与三委托）
- 测试素材：`<PROJECT_ROOT>\test_anim.gif`（三帧 160×160，600ms/帧）

### 21.7 仍未打通与下一步

| 目标 | 状态 |
|---|---|
| 文本发送 | ✅ |
| **图片发送（任意本地图片）** | ✅ **本轮打通** |
| 接收任意消息（含 XML） | ✅ |
| GIF 保留动画 | ❌ 图片通道静态化；需信封路径 |
| 收藏表情显示 | ❌ 需信封路径的发送任务上下文 |

按评审建议，下一步顺序为：**先补「完整原生工厂及所有权」**
（`0x1702E50` 的入参内容对象、`0x1AFE710` 信封工厂的所有权语义），
**再重估第 5 参数**（其真实结构尚未定型，不能沿用旧结论），
最后才规划信封路径的发送。

---

## 二十二、信封路径重测：从「崩溃」到「发送失败」（2026-10-13 19:44–19:58）

### 22.1 本轮按评审核实并修复的三处

| # | 评审意见 | 核实 | 处置 |
|---|---|---|---|
| 1 | `type=8` 仍是五参调用 | ✅ 成立（第六参数只补到了图片路径） | `wxb_send_sticker_pack` 改用 `WxbFn6` 传六参 |
| 2 | 信封组 d2/d3 并非空捕获 | ✅ 成立。实测确认 `+0x08/+0x10/+0x18` 均为非零指针 | 新增 `wxb_find_delegate_ctx()` 运行时定位并回填 |
| 3 | p6 含义未定 | ✅ 成立。值域 0xf4b…0x175d 且**存在重复**，只能说「非常量」 | 保持「未定」，暂用 `GetTickCount() & 0xFFFF` |

**所有权缺口（评审#4）确认并修复**：`send_runtime.c` 原为 16 槽环形且**直接 `VirtualFree` 最旧块**，
发送频率高时会在微信异步读完前把内存还掉。现改为 64 槽 + **仅当旧块年龄 > 30s 才释放**，
仍年轻时放弃追踪而不释放（宁可泄漏，绝不提前释放）。

### 22.2 委托捕获是共享对象，不是每条消息的上下文

frida 记录显示：**文本组与信封组的 d2/d3 捕获的是同一组堆指针**：

```
文本组 d2/d3: +0x08 = 0x2d1fa8d8ea0, +0x10 = 0x2d1fa91c6e0
信封组 d2/d3: +0x08 = 0x2d1fa91c6e0, +0x10 = 0x2d1fa8d8ea0   （顺序不同，对象相同）
```

其中 `0x2d1fa91c6e0` 的 vtable = `base + 0x8365848`，而该 vtable 的槽 **[+5] = 0x1AFEA70**
（紧邻信封工厂 `0x1AFE710`）⇒ 它属于**发送/会话侧的长生命周期对象**，跨消息类型、跨多次发送保持不变。

⇒ 因此它**不必伪造**，可用与 `send_ctx` 相同的方式运行时扫描定位
（已在 `send_sticker_tpl.c` 实现 `wxb_find_delegate_ctx`）。
**注意**：d1 的捕获含一个**栈地址**（文本组样本里 `+0x10` 指向调用者栈），
这一项无法跨调用复用，目前仍未填。

### 22.3 实测结果：不再崩溃，改为「发送失败」

补齐三处后重发模板 0：

| 版本 | 行为 |
|---|---|
| 五参 + 空捕获（旧） | ❌ 微信**崩溃** |
| **六参 + 实测顺序 + 回填 d2/d3 捕获（新）** | ⚠️ **微信弹出「发送失败」** |

⇒ 定性变化很重要：**信封被识别、发送流程被启动**，失败发生在内容／服务端校验环节，
而不再是参数错位导致的崩溃。

### 22.4 已排除的原因：模板未过期

用户新发的自定义收藏表情即模板 0（`b90ff3bb…`），frida 当场读出的槽位内容：

```
slot0 = b90ff3bbdb9eb50b8324bb7d6631a3ef
slot2 = 957d07571c034bba8d2ecfec7266f181
slot6 = http://vweixinf.tc.qq.com/110/20401/…&filekey=…6e01004fb1534819ec117156cb3474c…
slot7 = http://vweixinf.tc.qq.com/110/20403/…&filekey=…6e03004fb3534819ec117156cb34781…
slot8 = 245b5f04c2d19a6ea5cc7a63bb978aae
slot9 = http://vweixinf.tc.qq.com/110/20402/…&filekey=…6e02004fb2534819ec117156cb3476a…
```

与 4 小时前采集的模板**逐字节一致** ⇒ **CDN filekey 未过期**，
「发送失败」不能归因于模板时效。同时确认内容对象的 `+0x008 = 3` 与旧样本一致。

### 22.5 附带的分类发现：两类「表情」不可混谈

用户新添加的动态表情，其内容对象（vt `0x8755528`）只有：

```
slot0 = 69eb21b31e40ab6713746cf05b072889
slot1 = com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd
```

**没有 CDN URL**，`+0x008 = 5`（自定义收藏表情为 3）⇒ 这是**表情商城下载的表情包贴纸**，
与**自定义收藏表情**是两条不同链路。此前把两者混为「收藏表情」会误导判断；
后续取样必须明确要求「从图片添加的自定义表情」。

### 22.6 仍未确定 / 下一步

- **cfg（`0xDB40` 输出）的完整契约未复原**：d1 的栈捕获、六参数中 p6 的业务含义、
  以及各字段的「迁移 / 调用 / 销毁」契约都不清楚；
- 观察到同一进程内 `0xDB40` 被多种场景复用，d1 的 vtable 在 `0x83661E8 / 0x83677E8 /
  0x8B53AE8 / 0x86D9ED8` 之间变化 ⇒ **不能假设存在固定的「信封组」**，
  必须按调用场景配对（建议给 frida 记录加全局序号，把 `0xDB40` 与紧随的 `pack` 配起来）。

⇒ 按评审建议，下一步以**客户端自然成功发送的自定义收藏表情**为对照，
把 `0xDB40` 与 `pack` 成对记录，恢复 cfg 的完整契约，再重估第 5/6 参数。

---

## 二十三、cfg 侧验证与委托存储模式（2026-10-13 23:51–23:57，自主推进）

### 23.1 补上 cfg 侧记录（此前只看了「输入委托」）

frida 脚本新增：在 `pack` 入口 dump **cfg 内部的三个委托块**
（`cfg+0x10` / `+0x50` / `+0x90`，各 0x40 字节）与 `cfg+0xD0` 起的尾部。

**这一步的意义**：此前所有「委托捕获」结论都来自 `0xDB40` 的**入口参数**，
无法证明捕获是否真的进入了 cfg。现在可以逐字节复核。

### 23.2 实测：d2/d3 的 `[A,B,A]` 确实进入 cfg，且与原生完全一致

我们（注入 A/B 之后）：

```
cfg_d2_hex = 88783ca7fc7f0000 e0c691fad1020000 a08e8dfad1020000 e0c691fad1020000 …
             vtable 0x8367888  A=2d1fa91c6e0    B=2d1fa8d8ea0    A
cfg_d3_hex = 28793ca7fc7f0000 e0c691fad1020000 a08e8dfad1020000 e0c691fad1020000 …
```

与原生样本**逐字节一致** ⇒ **d2/d3 已可排除**（评审第 3 点要求的复核已完成）。

### 23.3 d1 的存储模式差异（本轮的关键发现）

`0xDB40` 对每个委托都先取 `[d+0x38]`：

```
[d+0x38] == d      → 调用 move-ctor（rax = [d]，call [rax+8]），结果写到 cfg 的委托块
[d+0x38] != d      → 直接把该指针写入 cfg 的 self 槽（即“外部数据对象”模式）
```

实测两点：

1. **d1 这一类委托的 move 分支只拷贝 vtable**：我们先把捕获填在 `d1+0x08/+0x18`
   时，`cfg_d1_hex` 里 vtable 之后的捕获**全是 0**；
2. **原生 d1 用的是外部存储**：它的 `cfg+0x48` 是**栈地址**（`0x40cb6fa160`），
   指向调用者栈上的数据对象（该对象内含 vtable `0x83677E8` + 三个捕获
   `[堆指针, 栈地址, 析构函数 0xA3E5]`）。

⇒ 因此把我们的 d1 改为**外部存储**：自备 `d1_data`（`arena+0xB00`），写入
`vtable / D1_08 / 0 / base+A3E5`，再令 `[d1+0x38] = d1_data`。实测：

```
修正后 cfg_d1_hex = 0000000000000000 … 000bee81d1020000(= arena+0xB00)
```

即 `cfg+0x48` 现在指向自备数据对象，**形态与原生一致**（原生的那个对象在其栈上）。

其中 `+0x18` 经反汇编确认为 **scalar deleting destructor 的非删除分支**
（`0xA3D0` 处 `test dl,1` → `call operator delete`，`0xA3E5` 为不删除路径）；
`+0x10` 是**栈地址**，天然无法跨调用复用，显式留 0。

### 23.4 p5 的读取宽度已确定

评审要求「查自然对象的写入过程，以及消费者按 byte / dword / pointer 读取」。
`0xDB40` 对第 5 参数的读取是：

```
rax = [rdi]        ; 8 字节
rcx = [rdi + 8]
```

⇒ **按 pointer 读取**，且 `0xDB40` 只把这对 `{_Ptr, _Rep}` **拷贝**进 cfg，
**不解引用** `body[0]`。我们的空包装会让 `0xDB40` 保留自己 `new(0x18)` 生成的
`{body, control}`（已由既有 cfg 转储确认存在）。
⇒ **在 `0xDB40` 这一层，p5 的内容不是判据**；若要跟进，方向是观察 cfg 之后的消费者。

### 23.5 注入通道（工程侧）

新增 `bridge\control\delegate_caps.txt`，由 frida 抓取、DLL 读取：

```
A=<hex>          d2/d3 的共享对象（vtable 0x8365848）
B=<hex>          d2/d3 的第二个捕获
D1_08=<hex>      d1 的 +0x08（堆指针）
D1_18=<rva hex>  d1 的 +0x18（析构函数 RVA）
```

解析结果已用诊断回写验证：`caps: n=61 A=…B=…D1_08=…D1_18rva=0xA3E5`。
注意这些地址**只在本次进程生命周期内有效**，微信重启后必须重抓。

### 23.6 待验收

上述改动已编译部署（微信 PID 33760 正常、worker 在跑），
但**「是否送达」尚未确认**——需要一次人工目视：
发到「文件传输助手」后看消息是否出现（此前同参数版本会弹「发送失败」）。

---

## 二十四、post-pack 链路分层探针（2026-10-14 12:47–13:00）

**前提修正**：本轮开始时微信已于 12:45 重启（新 PID 26460，后为 33548），
`delegate_caps.txt` 中的 A/B/D1 地址随之失效（已清空），需重抓。

### 24.1 分层结论（每层均为实测）

| 层 | 地址 | 实测结果 |
|---|---|---|
| pack 入口 | `0x160EBE0` | ✅ 命中，`rcx`/`rdx` 确为我们的 container / cfg |
| pack 内部投递 | `0x160EBE0` 内 `call 0x290390` | ✅ 正常调用、**正常返回**（DLL 侧打点：`before call` → `after call (returned)`，无异常） |
| 投递函数 | `0x290390` | ✅ 被调用；开头 `cmp [rcx+0x10],0` 实测**非零**（该对象 +0x10 = `0x18e38183950`）⇒ **不走错误分支** |
| 真正入队 | `0x28F2F0` | ✅ 被调用（`rcx`=全局服务对象、`rdx`=栈、`r8`=`[rcx+0x10]`、`r9`=栈） |
| 分支判定 | `0xC13360`（检查 `r8+8`） | 返回 **0** ⇒ 走 `0x28F354` 分支，**不是** `0x28EF10` |

### 24.2 关键对照：文本与表情走同一条入队路径

用同一套探针分别触发**文本发送（已知成功）**与**表情发送（发送失败）**：

```
文本  → ENQUEUE 命中，ENQUEUE_PATH_A 未命中
表情  → ENQUEUE 命中，ENQUEUE_PATH_A 未命中
```

⇒ **分叉点不在入队这一层**，而在**入队之后的异步阶段**。
那一层再往下即进入网络/服务端；客户端侧可读证据到此为止
（`mm_20261013.xlog` 为 Mars 加密格式，头部 `07 01` + 随机字节，无密钥不可解）。

### 24.3 因此当前证据支持的状态

| 组成部分 | 状态 |
|---|---|
| 信封 / 内容对象 | ✅ 与原生逐字段一致（含 12 个字符串槽） |
| cfg（含 `[A,B,A]` 捕获、`d1` 外部存储） | ✅ 与原生一致（d2/d3 逐字节相同） |
| pack 调用与返回 | ✅ 正常 |
| 入队 `0x28F2F0` | ✅ 与文本同路径 |
| **入队之后的异步阶段** | ❌ **此处被判失败** |

### 24.4 事故记录（方法论教训）

**在同一函数内挂多个内部断点会让微信退出**：frida 重写函数入口后，
同一函数的多个内部 hook 互相破坏，进程随即崩溃（12:53 那次）。
改用两种安全方式：**DLL 侧打点**（关键结论即由此得到）与
**每次只 hook 互不相同的函数**。

### 24.5 仍未闭合与可选方向

1. **自然发送截获**：在 `0x160DF80` / `0x1AFE710` 被调用时替换内容——
   可行是因为上下文由微信自己构造，我们只改内容；但需要一次真实发送触发，
   且替换"内容对象"需依赖内存中已存在的等价对象。
2. **图片通道承载**：已打通，任意本地图片可全自动发送（静态）；GIF 只取首帧。
3. **失败详情**：微信弹「发送失败」时若有可展开的详情/错误码，是唯一能直接
   指出拒绝原因的线索。

---

## 二十五、XML 承载试验与被排除的组合（2026-10-14 13:05）

### 25.1 试验：把表情 XML 当普通 XML 消息发送（type=1）

依据：接收日志中「腾讯新闻」推送就是 `type=1` + XML（`<mmreader>…`），
且接收端会把它渲染成卡片 ⇒ 推测 `type=1` 可承载结构化内容。

实现：`send_sticker_xml.py <target> 1`（`type=9` 命令 + 类型码 1 + 真实表情 XML）。

**实测结果**：

| 组合 | 送达 | 渲染 |
|---|---|---|
| 表情 XML + `type=1` | ✅ **送达** | ❌ 显示为 **XML 原文** |
| 表情 XML + `type=47` | ❌ 不送达 | — |

⇒ 两个结论：
1. **文本通道确实能携带任意内容**（1550 字节的表情 XML 完整送达）；
2. **是否渲染成表情取决于消息类型码，而不是 XML 内容本身**——
   微信认得 `<mmreader>`+`type=1` 这个组合（渲染成卡片），
   但不认 `<msg><emoji>`+`type=1`（按未知 XML 显示原文）。

### 25.2 为什么这不构成一条通路

渲染需要 `type=47`，而 `type=47` + 文本模型**直接不送达**；
送达需要 `type=1`，而 `type=1` **不渲染**。两条路互斥，
且 `type=47` 的合法载体是**信封**（第二十四节已证明信封侧全部一致，
失败发生在其后的异步阶段）。

### 25.3 至此已排除的组合（完整清单）

| # | 方式 | 结果 |
|---|---|---|
| 1 | 手工构造信封 + `0xDB40` + pack（文本组委托） | 静默不送达 |
| 2 | 同上，换**信封组**委托（空捕获） | **崩溃** |
| 3 | 信封组委托 + 补齐第 6 参数 + 实测委托顺序 | 「发送失败」 |
| 4 | 同上 + 回填 d2/d3 的 `[A,B,A]` 捕获（真实地址） | 「发送失败」 |
| 5 | 同上 + `d1` 改为外部存储（原生同构） | 「发送失败」 |
| 6 | 图片模型 + `type=47` | 不送达 |
| 7 | 表情 XML + `type=1` | 送达但显示原文 |
| 8 | 表情 XML + `type=47`（文本模型） | 不送达 |

### 25.4 结论

纯客户端 hook 路径下，**信封的构造与投递已经做到与原生逐字段/逐字节一致**，
而失败稳定发生在**入队之后的异步阶段**（第二十四节），客户端侧无更多可读证据。

剩余可行方向仅两条：
1. **自然发送截获**（`0x160DF80` / `0x1AFE710` 被调用时替换内容）——
   上下文由微信自己构造，成功率高，代价是需要一次真实发送触发；
2. **图片通道承载**（已可用，任意本地图片全自动；GIF 只取首帧）。

---

## 二十六、载体替换：收藏表情发送打通（2026-10-14 13:30，决定性突破）

**本节结论经对端实测确认**（不只是本地显示），推翻上文"客户端侧无更多可读证据、
无法打通"的终局判断。

### 26.1 结论先行

**收藏表情的程序化发送已打通**。但路线与前二十五节完全不同：
**一个字节的对象都不构造。**

让用户自然发送任意一个收藏表情充当"载体"，在 pack 提交点 `0x160EBE0` 的**入口**处，
把该消息**内容对象的 6 个 `std::string` 槽就地覆写**成目标表情的数据。
任务上下文、信封、委托、cfg、队列、序列化——全部由微信自己产生。

### 26.2 为什么这条路能成（与前 25 节的关系）

把 §20.5 与 §24 合起来看，结论其实已经指向这里：

| 节 | 已证明的事实 |
|---|---|
| §20.5 | 发送任务上下文（`0xDB40` 第 5 参数）**无法手工伪造**；参数 5 为 NULL 时 `0xDB40` 退化为内部空块 |
| §24 | 即使信封与内容对象**逐字段一致**、入队走**同一条路径**，消息仍在入队**之后**被判失败 |

⇒ 失败既不在"内容"，也不在"入队"，而在**承载内容的那套上下文**。

本节的做法把这套上下文整个让给微信产生，我们只改最后 6 个字符串。
这正是 §25.4 所列"剩余方向 1（自然发送截获）"的落地，且比它更保守——
§25.4 设想的是"替换成我们构造的内容对象"，本节**连内容对象都不构造**，只改它的字段。

### 26.3 内容对象布局（本次实测坐实）

```
信封 vtable                        0x82CB8D8
信封 +0x660                        内容对象（裸指针，指向对象体）
内容对象 +0x000                    对象体 vtable = 0x8755528
内容对象 +0x010 + k*0x20           第 k 个 std::string
                                   buf @ +0x00（16 字节 SSO 区）
                                   len @ +0x10（int）
                                   cap @ +0x18（int，cap<=0xF 表示 SSO）
```

实测槽位（6 个有效槽，其余为空 SSO）：

| 槽 | 偏移 | 字段 | 实测 len / cap | 富余 |
|---|---|---|---|---|
| slot0 | `+0x010` | `lib_md5` | 32 / 0x2f (47) | 15 |
| slot2 | `+0x050` | `spec_md5` | 32 / 0x2f | 15 |
| slot6 | `+0x090` | `url_20401` | 324 / 0x14f (335) | 11 |
| slot7 | `+0x0b0` | `url_20403` | 322 / 0x14f | 13 |
| slot8 | `+0x0d0` | `aux_md5` | 32 / 0x2f | 15 |
| slot9 | `+0x0f0` | `url_20402` | 324 / 0x14f | 11 |

**定长性**：`md5` 恒 32 字符；三个 URL 恒 324/322 字符（filekey 内嵌 md5 与 storeid
均为定长）。⇒ **cap 永远够用**，就地覆写不会触发任何重新分配、不调用 `operator new`、
不释放任何缓冲。这是本方案最重要的安全依据。

`body_hex` 逐字段交叉核对通过：`+0x10+k*0x20` 的 buf / `+0x20` 的 len / `+0x28` 的 cap
全部与上表一致。

### 26.4 实测证据

**dry-run（只观察）**：
```
PACK tid=29476 models=1                 ← tid=29476 即窗口线程（见 channel.txt window_tid）
  model0 vt=0x82cb8d8
    content=0x18e40e9d460 vt=0x8755528
      slot0  lib_md5  len=32  cap=47  : cbab1418a65ab56a82b228ea2a27c621
      slot6  url_20401 len=324 cap=335
      slot7  url_20403 len=322 cap=335
      slot8  aux_md5  len=32  cap=47
      slot9  url_20402 len=324 cap=335
```

**live（就地覆写）**：
```
carrier=cbab1418a65ab56a82b228ea2a27c621  ->  target[0]=0fbdd73cc59f210845f4d2457b0167b8
  write slot0/2/6/7/8/9  ->  OK ×6
  after slot0 : 0fbdd73cc59f210845f4d2457b0167b8
  after slot2 : 9558c0a6b75d4821b7b68c2eecb19eac
  SWAP#1 完成
```

**端到端**：用户点击载体（idx4「单手托下巴」）发送后，**对端实际收到并显示的是
idx0「正面微笑」**——确认改动影响的是真正发出去的字节，而非本地 UI 显示。

### 26.5 复现步骤

1. `python frida_sticker_swap.py`（dry-run，确认能读到内容对象与 6 个槽）
2. `python frida_sticker_swap.py --live --target <idx>`（就地覆写）
3. 在微信里手动发送**任意**一个收藏表情 → 实际发出的是模板 `<idx>`
4. 脚本 `MAX_SWAPS=1`，只替换第一条；`before[0] == target` 时自动改用 `(idx+1)%7`，
   保证一次点击就能看出差异

### 26.6 剩余限制（下一步的真实起点）

| 限制 | 说明 |
|---|---|
| **仍需一次真实点击** | 任务上下文只能由微信产生。这是当前唯一未解决的环节 |
| 模板集固定为 7 个 | 取自 `reports/sticker_templates.json`；扩表情需重新采集内容对象 |
| URL 有效期 | 实测同一天内稳定（11:49 采集的模板与 12:48 的自然发送逐字节一致），长期有效性未验证 |

**下一阶段两个方向**：
1. **复用任务上下文**：hook `0xDB40` 捕获第 5 参数（`cfg[0]/cfg[8]`，shared_ptr 对，
   需 `lock inc [ctrl+8]` 保活），在自建发送流程里传进去——成功即"点一次、之后全自动"。
2. **上溯到更少参数的入口**：§20.7 已指出应找"参数最少、可由当前会话+表情标识驱动"的层
   （`0x83D5D0 → 0x262100 → 0x8E07B0 → 0x1B13808 → 0x1AFD280 → 0x160DCD0 → 0x160DF80`）。

### 26.7 新增工具

| 脚本 | 用途 |
|---|---|
| `frida_sticker_swap.py` | 载体替换探针/执行器（dry-run 与 `--live` 双模式，7 模板内置） |
| `fetch_sticker_images.py` | 从 CDN 拉 7 个模板原图（CDN 上是明文 PNG，本地 `Persist` 是加密态） |
| `reports/frida_swap_<pid>.txt` | 每次运行的 before/after 全量记录 |

### 26.8 附带结论：本地表情文件是加密态，但 CDN 副本是明文

`business\emoticon\Persist\<hh>\<md5>` 为加密存储（magic `D0 B1 68 C5 3A C9 50 57`，
9~13 KB），而同一表情的 CDN 副本（`url_20401`）**直接返回明文 PNG**（114~142 KB）。
⇒ 需要表情实物时不必解密本地文件，直接用模板里的 URL 取。

---

## 二十七、任务上下文复用：免点击自动发送（2026-10-14 13:50，第二处突破）

### 27.1 结论

**收藏表情可以无人值守自动发送**——不再需要每次人工点击。

做法：捕获一次**自然发送时的真实任务上下文**，之后在自建的发送流程里复用它。
已实测：**t+5s、t+60s 两次复用均送达对端**（t+300s 数据见 §27.6）。

### 27.2 根因精确定位到一行

§20.5 说"发送任务上下文无法手工伪造"，但当时没有定位到**具体的代码行**。本节把它钉死了。

`wxb_send_sticker_pack`（`send_sticker_tpl.c`）调用 `0xDB40` 时：

```c
result = ((WxbFn6)(base + WX_OFF_SEND_CALL2))(
    (int64_t)cfg, (int64_t)d1, (int64_t)d2, (int64_t)d3,
    (int64_t)d4,                            /* ← 第 5 参数 */
    (int64_t)(GetTickCount() & 0xFFFF));
```

其中 `d4 = arena + 0x0A80`，而 arena 在调用前被 `ZeroMemory` 过 ⇒
**第 5 参数是一个全零的假上下文**。

而 `0xDB40` 会把 `[d4]` / `[d4+8]` **原样搬进 `cfg[0]` / `cfg[8]`**（即 cfg 头部的 shared_ptr）。
自然发送时这两个值是真实的 `shared_ptr<TaskContext>`。⇒ 这就是"发送失败"的直接原因。

### 27.3 做法

```
1) hook 0x160EBE0(pack)  —— 自然发送时捕获真实 cfg[0]/cfg[8]
2) hook 0xDB40           —— 自建发送到达时，把 d4 指向的 16 字节改成真实值
```

任务上下文、信封、队列仍全部由微信产生；我们只是**借用**一次微信自己的发送资格。

### 27.4 两个踩过的坑（重要）

**坑一：捕获条件写错，靠数据才发现。**
初版写成 `ctrl.add(0x10).readPointer().equals(body)`——把 `+0x10` 当成"存对象体指针的位置"
去解引用。按 §8.3 的构造序列（`lea rdi,[r12+0x10]`），对象体是**紧邻**控制块的，
正确判据是 **`ctrl.add(0x10).equals(body)`**（地址相等，不解引用）。
写错时 `captures` 恒为 0，而 pack 明明是命中的——表现为"静默不捕获"。

**坑二：脚本静默 return 会让"没调用"与"调用了但条件不满足"无法区分。**
初版 pack hook 在 cfg 为空时直接 `return`，不打日志；结果一轮实验完全无法判读。
修正做法：
- 给 pack hook 加**无条件记录**（前 6 次）；
- 加 `setInterval` **心跳（TICK）**，每 5 秒写一行计数器。
  ⇒ `TICK packHits=0 emojiHits=0`（没走到）与 `PACK#1 cfg0=... cfg8=...`（走到了）一目了然。

### 27.5 安全设计（三条）

| 措施 | 说明 |
|---|---|
| 只写自己的内存 | 注入只改 `d4` 指向的 16 字节（DLL 自己 `VirtualAlloc` 的 arena），不碰任何微信对象 |
| 只对表情路径注入 | 先校验 `args[1]`（d1）的 vtable RVA == `0x83677E8`（信封组），不污染文本/图片发送 |
| 双存活探测 | ① `readable(body, 0x40)`；② **`ctrl` 的 vtable RVA 必须仍为 `0x7f5f398`**（§20.5 实测值）。任一不过就跳过注入 ⇒ DLL 退回假上下文，只会「发送失败」不会崩 |

**为什么用 `ctrl` 而不是 `body` 做存活判据**：`body` 的首字段会随堆内存复用而变
（实测 `0xffff8192e62eef00` → `0xffff800ca4b90010` → `0xffff800ea4b90010`），
本身不是 vtable（§20.5 已注明"body[0] 是普通指针"），不可用作判据；
`ctrl` 的 vtable 在对象存活期内稳定。

### 27.6 实测数据

```
EMOJI_CTOR#1 tid=29476 rcx=0x38d018a9e0          ← 自然发送（窗口线程 29476）
PACK#1      tid=29476 cfg0=0x18e418c7450 cfg8=0x18e418c7440
CAPTURE#1   body=0x18e418c7450 ctrl=0x18e418c7440 ctrl_vt=0x7f5f398
INJECT#1    tid=25188 d4=0x18e40890a80 <- 真实上下文          ← t+5s
PACK#2      cfg0=0x18e418c7450 cfg8=0x18e418c7440  → ok:true
INJECT#2    tid=25188 d4=0x18e408a0a80 <- 同一上下文（校验通过）← t+60s
PACK#3      cfg0=0x18e418c7450 cfg8=0x18e418c7440  → ok:true
INJECT#3    tid=25188 d4=0x18e38820a80 <- 同一上下文（校验通过）← t+300s
PACK#4      cfg0=0x18e418c7450 cfg8=0x18e418c7440  → ok:true
```

**复用时效**：t+5s / t+60s / t+300s 三次注入**全部通过 `ctrl_vt` 存活校验并成功提交**，
即**同一任务上下文在 5 分钟后依然有效**。三次发送的 arena / cfg 地址各不相同
（每次 `wxb_send_sticker_pack` 新分配），说明上下文是跨调用被复用的，不依赖单次 arena。

对端实收（**三条全部确认送达**）：
- **t+5s 那条：送达**（对端确认收到「正面微笑」= tpl0）
- **t+60s 那条：送达**
- **t+300s 那条：送达**
- 内容由**我们的内容对象**决定（不是"手动那次的副本"），证明上下文只提供发送资格，
  不带走消息内容——这是本方案能任意发表情的前提

**结论：捕获一次，5 分钟内可反复自动发送。** 这就是"免点击"的落地形态。

### 27.7 诊断工具与方法

| 工具 | 用途 |
|---|---|
| `frida_peek.py <rva> [n]` | 比对**文件原始字节 vs 运行时字节**，判定某地址是否被 hook（`e9` = jmp rel32） |
| `frida_ctx_reuse.py` | 捕获 + 注入 + 时效测试；`--schedule 5,60,300` 控制复用时间点 |

**排障时先用 `frida_peek.py` 分清三件事**：hook 没装上 / hook 装上了但函数没被调用 /
函数被调用了但脚本条件不满足。三者表现相似，只有字节比对 + 心跳计数能区分。

### 27.8 仍待确认

1. **复用时效上限**：已确认 **≥300 秒**（t+5s / t+60s / t+300s 三次注入全部通过校验并提交）。
   更长（30 分钟 / 跨操作）仍待测；`ctrl_vt` 校验可安全兜底。
2. **是否需要保活**：目前未对上下文增加引用计数（`lock inc [ctrl+8]`）。若发现长时复用失效，
   可加引用计数延长寿命。
3. **并发安全**：多次发送共用同一上下文是否会在高并发下互相干扰，未测。
4. **落地形态**：目前靠 frida 常驻；下一步可把"捕获 + 注入"写进 DLL，
   由 `reinject_daemon` 保活，对调用方暴露成一个普通命令类型。
   —→ **已于 §28 完成**。

---

## 二十八、生产形态固化：DLL 独立发送（2026-10-14 14:06）

### 28.1 结论

**收藏表情发送已完全脱离 frida**：DLL 自己读一个地址文件即可发送，无需任何外部进程常驻。
实测：**停掉全部 frida 之后**，DLL 独立发出 tpl=0 与 tpl=1，对端两次均收到。

### 28.2 分工取舍：为什么不把 hook 写进 DLL

直觉做法是在 DLL 里 inline hook `0x160EBE0` 捕获上下文。**放弃它的理由有两条**：

1. **DLL 现有的 trampoline 不可复用**：`receive.c` 的 `build_trampoline` 是**为接收函数定制**的
   （内含硬编码的 `0x48,0x8B,0x46,0x18` load 序列与 7 字节还原），不是通用 trampoline。
2. **`0x160EBE0` 的前几字节对 7 字节 patch 不友好**：开头是
   `55 / 41 56 / 56 / 57 / 53 / 48 81 EC …`，按 7 字节切会**切断** `sub rsp,0x1e0`
   的前缀字节 `48`，trampoline 里就是半条指令 ⇒ 必崩。要用就得自己写按指令边界的
   （≥5 字节处正好是 6 字节边界）版本，而 §24.4 已经昭示在这条链上动手的代价。

**改用分工**：frida 只负责**捕获并落盘**，DLL 负责**读取并注入**。DLL 侧零 hook，风险最低。

```
frida（只在需要时跑一次）           DLL（常驻，reinject_daemon 保活）
  hook 0x160EBE0 捕获 cfg[0]/cfg[8]   →   读 control\ctx_override.txt
  → 写 control\ctx_override.txt            → 存活校验
                                           → 填 d4 的 16 字节
                                           → 0xDB40 → pack → 发送
```

### 28.3 落地细节

**落盘格式**（`bridge\control\ctx_override.txt`，UTF-8 **无 BOM**）：
```
BODY=18e469a1850
CTRL=18e469a1840
PID=33548
```

**DLL 侧新增**（`send_sticker_tpl.c`）`wxb_load_ctx_override()`，校验两项（与 frida 侧一致）：
- `body == ctrl + 0x10`（MSVC `_Ref_count_obj2` 对象体紧邻控制块）
- `[ctrl] == base + 0x7F5F398`（`WX_OFF_STK_TASKCTX_CTRL_VT`，§20.5 实测值）

**注入点**：`wxb_send_sticker_pack` 在调用 `0xDB40` **之前**，把 d4 处 16 字节替换成上面两个值；
校验失败则**保持全零假上下文**（后果只是「发送失败」，绝不会把悬空指针喂给 `0xDB40`）。
`tpl_debug.txt` 会打印 `ctx override: body=… ctrl=…` 或 `不可用` 以示分界。

**为什么扫描定位不可行**（顺带排除的路线）：vtable `0x7F5F398` **在一个进程里并不唯一**——
`frida_scan_ctx.py` 实测命中 **14+ 个**同 vtable 实例（`uses/weaks` 从 1/1 到 0/0 都有），
且多数 `body[0]` 是奇数值（非合法指针）。因此无法靠扫描挑出「发送任务上下文」，
**必须由 pack 入口捕获**。

### 28.4 踩坑：UTF-8 BOM 污染 seq（症状极具误导性）

手工用 PowerShell 写 outbox 时用了 `Set-Content -Encoding UTF8`，**PS 5.1 会加 BOM**：

```
文件头实测：ef bb bf 31 37 39   ← BOM + "179"
```

于是第一个字段 `seq` 变成 `<BOM>1791957871593`，`write_result` 拿它拼
`result_<BOM>…json` 去落盘 ⇒ **命令照常执行、`status.txt` 正常更新、pack 正常返回，
唯独 `result_*.json` 静默不出现**。极易被误判成「命令没被消费」。

**修复**：`outbox.c` 的 `wxb_poll_outbox` 在读入后跳过 `EF BB BF`。
验证：故意用带 BOM 的 PS 写法发 tpl=1，`result_1791958005735.json` 正常落盘、seq 干净、
对端收到「嘟嘴」。

**既有调用方不受影响**：frida 脚本与 `feizhi_pc/bridge.py` 都用 Python 的
`Path.write_text(..., encoding="utf-8")`，**默认不带 BOM**。

### 28.5 运维流程

| 时机 | 动作 |
|---|---|
| 微信重启后 | `ctx_override.txt` 里的地址失效 → **需要重新捕获一次**：跑 `python frida_ctx_reuse.py --dump-ctx --no-autosend`，然后手动发一个收藏表情 |
| 日常自动发送 | 直接写 `outbox\next.txt`（`type=8`），DLL 自行读取上下文并发送，**无需 frida** |
| 校验失效 | `tpl_debug.txt` 出现 `ctx override: 不可用` ⇒ 地址过期，按第一行重新捕获 |

**这是目前唯一的运维约束**：每次微信重启后需要一次真实点击来刷新上下文地址。

### 28.6 本轮验证清单

| 验证项 | 结果 |
|---|---|
| 新 DLL 编译注入 | `worker started`、`hooked=1` |
| frida 完全停止 | `frida_peek` 确认 `0x160EBE0` 字节 = 文件原始 `55 41 56 56 57 53 48 81` |
| DLL 独立发 tpl=0 | `ctx override` 应用成功，对端收到「正面微笑」 |
| DLL 独立发 tpl=1 | 对端收到「嘟嘴」 |
| BOM 输入下 result 落盘 | `result_1791958005735.json` 正常，seq 干净 |

### 28.7 新增/变更文件

| 文件 | 变更 |
|---|---|
| `src/modules/send_sticker_tpl.c` | 新增 `wxb_load_ctx_override()` + `0xDB40` 前的注入点 |
| `src/modules/outbox.c` | 跳过 UTF-8 BOM |
| `src/include/wx_bridge_offsets.h` | 新增 `WX_OFF_STK_TASKCTX_CTRL_VT = 0x7F5F398` |
| `frida_ctx_reuse.py` | 新增 `--dump-ctx`（捕获落盘，供 DLL 读取） |
| `frida_scan_ctx.py` | 新增：扫描定位尝试（结论：不可行，vtable 不唯一） |

---

## 二十九、表情包（表情商店添加）表情的发送可行性（2026-10-14 14:26）

### 29.1 结论

**能发。已实测验证**：在同专辑内「点一枚、发出另一枚」成立
（载体 `ca9d0631…` → 目标 `1b09ef50…`，对端确认收到的不是被点的那枚）。

**但不是"零成本复用收藏表情的模板"**——两者的内容对象布局不同，需要按表情包型构造。

### 29.2 协议同源，内容对象不同构

接收侧的消息原文（`bridge\inbox\` 里一条真实的 type=47）显示表情包表情的特征：

```xml
<emoji type="2" md5="77224fe0…" productid="" designerid=""
  cdnurl="http://wxapp.tc.qq.com/262/20304/stodownload?m=…&bizid=1023"
  encrypturl="…" externurl="…" externmd5="…" aeskey="ce704cb0…"
  width="240" height="240"/>
```

与收藏表情的区别：

| | 收藏表情 | 表情包（商店）表情 |
|---|---|---|
| CDN 域名 | `vweixinf.tc.qq.com` | `wxapp.tc.qq.com` |
| 通道 | `/110/20401`、`/110/20403`、`/110/20402` | `/262/20304`（三条同通道） |
| `bizid` | `1022` | `1023` |
| 独有字段 | — | `aeskey`、`encrypturl`、`externurl`、`designerid` |
| 协议层 | `type=47` | **`type=47`（同一种消息）** |

**发送侧内容对象逐字段对照**（两次实测 hex）：

| 偏移 | 收藏表情 | 表情包表情 |
|---|---|---|
| `+0x00` | vt `0x8755528` | vt `0x8755528`（同类对象） |
| **`+0x08`** | **3** | **5** |
| slot0 | `lib_md5`(32) | 该表情 md5(32) |
| slot1 | 空(SSO) | **专辑 ID**(65) `com.tencent.xin.emoticon.person.stiker_<…>` |
| slot2 | `spec_md5`(32) | 空 |
| slot6/7/9 | 三条 CDN URL(324/322/324) | 空 |
| slot8 | `aux_md5`(32) | 空 |
| `+0x158` | `0x12…` | `-1` |
| `+0x160` | 固定值 | **内联 SSO 字符串**（实测为专辑/表情名，如「空降」） |

⇒ 收藏表情**自带 CDN 地址**（所以要三个 URL 槽），表情包表情**只带 md5 + 专辑 ID**，
地址由微信自己解析。

### 29.3 两个关键稳定性实测

| 项 | 实测 |
|---|---|
| `slot0`（表情 md5） | 同一枚重复发送，逐字节相同 |
| `slot1`（专辑 ID） | **同专辑内不同表情也完全相同**（两枚 md5 不同、slot1 相同），且跨多次发送不变 |

`slot1` 里那段数字（`1785779393052`）换算成时间是 2026-08，**不是发送时刻**——
所以它是专辑的固有 ID，不是每次生成的会话号。**这是"能自动发送"的根据**：
值稳定，才能预先构造。

### 29.4 实测：同专辑内载体替换成立

`frida_pack_sticker_swap.py`（live）：

```
PACK#1 tid=29476
  +0x08=5  slot0=ca9d0631d936ad6fd5893f663d98650d  (len=32 cap=47)
  slot1=com.tencent.xin.emoticon.person.stiker_17857793930522dbd144c584fd
  载体 同专辑其它成员 -> 目标 1b09ef505de4501c4f77569207864e4b
  write slot0 -> OK
  SWAP#1 完成
```

对端确认：**收到的不是被点的那枚**。

**为什么只改 slot0 就够**：两枚都是 32 字符、cap 恒 0x2f=47 ⇒ 就地覆写零重分配；
专辑 ID（slot1）同专辑内相同，无需改动。这与收藏表情的载体替换（改 6 个槽）是同一战术，
只是字段落点不同。

### 29.5 与收藏表情的能力对照（当前状态）

| 能力 | 收藏表情 | 表情包表情 |
|---|---|---|
| 载体替换（点一枚发另一枚） | ✅ 已验证 | ✅ **已验证**（本节） |
| 免点击自动发送（复用任务上下文 + 构造内容对象） | ✅ 已验证（§27/§28） | ⏳ **待实现**——DLL 的 `wxb_build_content` 目前只按收藏表情布局构造 |
| 用 CDN URL 取原图做对照 | ✅ | ⏳ 未试（该表情走 `wxapp.tc.qq.com/262/20304`，且接收侧带 `aeskey`） |

### 29.6 要让表情包表情也免点击，需要做什么

1. **采集完整布局**：本节的 hex 已经拿到（`reports/frida_ctx_reuse` 报告里的 `body_hex`）。
2. **扩展 `wxb_build_content`**：支持"表情包型"——`+0x08=5`、填 slot0/slot1、
   写 `+0x160` 的名字字符串，其余槽置空。
3. **发送链路完全复用**：pack + 真实任务上下文（§27/§28）不需要任何改动。

**未知项**（实现前应实测确认）：
- `+0x158` 的 `-1` 与 `+0x160` 名字字段是否被服务端校验（若非必需，构造更简单）；
- **跨专辑**表情（slot1 不同、长度可能不同）是否只需改 slot1，还是要连带别的字段。

---

## 三十、表情包表情也免点击了 + 任务上下文的真实寿命（2026-10-14 14:56）

### 30.1 结论

**表情包（表情商店添加）表情现在同样可以免点击自动发送。** 新增命令 `type=12`。
实测：用户发一枚（`c226da26…`）→ 自动发出目标枚（`a6d3a7ab…`），对端确认收到。

至此收藏表情与表情包表情在能力上完全对齐：

| 能力 | 收藏表情 | 表情包表情 |
|---|---|---|
| 载体替换（点一枚发另一枚） | ✅ | ✅ |
| 免点击自动发送 | ✅（type=8） | ✅（**type=12**，本节） |

### 30.2 实现

**新增构造**（`send_sticker_tpl.c`）`wxb_build_content_pack()`：骨架与收藏表情的
`wxb_build_content()` 相同（控制块 0x1B0 / 对象体 0x158 / vtable 0x8755528），
差异只在三处整数字段与字符串槽落点（§29.2 的实测值）：

```c
w32(block + 0x018, 5);    /* body+0x08 = 5（收藏为 3） */
w64(block + 0x160, 0);    /* body+0x150 = 0（收藏为 0x12<<32） */
w32(block + 0x168, -1);   /* body+0x158 = -1（收藏为 5） */
slot0 = md5 ; slot1 = 专辑 ID ; slot10 = 名字
```

**发送入口**：把原 `wxb_send_sticker_pack()` 改名为
`wxb_send_sticker_pack_ex(tpl_index, to_wxid, is_pack)`，只把内容对象的构造
按 `is_pack` 分派；**信封 → pack → 真实任务上下文这条链路一行未改**。
保留 `wxb_send_sticker_pack()` 作为 `is_pack=0` 的包装，另加
`wxb_send_pack_sticker()`（`is_pack=1`）。命令侧新增 `type=12`（见 `outbox.c`）。

### 30.3 顺带修掉一个潜伏 bug：短字符串的 SSO 边界

`wxb_heap_string()` 原本按 `cap = len | 0xF` 处理所有非空串。但当 `len <= 15` 时
该式必然 `<= 0xF`，而 MSVC 的 `std::string` 用 **`cap <= 0xF` 判定「内联存储(SSO)」**——
buf 明明是堆指针，读取方却会去内联区取字，等于**静默读到垃圾**。

收藏表情的槽全是 32/324 字节，不会触发；而表情包的名字（如「空降」「香」）只有 6 字节，
正好踩到这个边界。已修正为：短串也抬到 SSO 阈值之上（`if (cap <= 0xF) cap = 0x1F;`）。

### 30.4 关键发现：任务上下文很短命，必须尽快使用

**这是本节最有价值的发现，直接决定生产流程的写法。**

| 观察 | 结果 |
|---|---|
| 捕获后 **约 30 秒**才使用 | ❌ 校验失败 —— `[ctrl]` 已不是任务上下文 vtable，引用计数字段是垃圾（实测 `0x18e41270850` 处 `uses=950358896`），内存已被回收复用 |
| 捕获后 **5 秒内**使用一次 | ✅ 成功，**并因此保活**（§27 实测 t+60s、t+300s 仍可用） |

**机理**：任务上下文是「每次发送新建、用后即释放」的对象。但一旦被用过一次，
`0xDB40` 复制它（shared_ptr 语义）会**增加引用计数**，从而延长寿命。

⇒ **生产流程必须是「捕获 → 立刻发送」，不能捕获后搁置。**
`frida_ctx_reuse.py` 的 `--schedule 3`（捕获后 3 秒自动触发）就是为此设计的，
而不是可选的调优项。

**安全兜底仍然有效**：失效的地址会被两项校验拒掉（`body == ctrl+0x10`、
`[ctrl] == base+0x7F5F398`），退回全零假上下文 ⇒ 只表现为「发送失败」，不会崩。

### 30.5 本轮验证记录

```
PACK#1 tid=29476  (自然发送)  cfg0=0x18e3f07e890 cfg8=0x18e3f07e880  slot0=c226da26…
CAPTURE#1 body=0x18e3f07e890 ctrl=0x18e3f07e880
PACK#2 tid=11128  (DLL 发送)  cfg0=0x18e3f07e890 cfg8=0x18e3f07e880  slot0=a6d3a7ab…（目标）
tpl_debug: ctx override: body=0000018E3F07E890 ctrl=0000018E3F07E880   ← 校验通过
```

对端确认收到目标表情。

### 30.6 新增/变更

| 文件 | 变更 |
|---|---|
| `send_sticker_tpl.c` | 新增 `wxb_build_content_pack()`、`wxb_send_sticker_pack_ex()`、`wxb_send_pack_sticker()`；修正 `wxb_heap_string()` 的 SSO 边界 |
| `outbox.c` | 新增命令类型 **`type=12`**（表情包表情） |
| `wx_bridge_send_sticker_tpl.h` | 新声明 |
| `frida_ctx_reuse.py` | 新增 `--cmd-type`（8/12），可自动触发任一类型 |
| `tmp/send_pack_sticker.py` | 手动发 type=12 的小工具 |
| `tmp/parse_content_hex.py` | 按真实偏移表解析内容对象（含第 11/12 槽） |
| `tmp/check_ctx.py` | 进程内校验上下文两条判据，定位校验失败点 |

### 30.7 仍未验证

- **跨专辑**表情：`slot1` 不同时是否只需替换 slot1（各专辑的专辑 ID 长度可能不同）；
- `+0x150` / `+0x158` 是否真被服务端校验（目前按实测值原样填）；
- 名字（slot10）是否必须准确 —— 目前按采集到的值填。

---

## 三十一、常驻 hook：自动捕获任务上下文（2026-10-14 15:03）

### 31.1 结论

**「上下文必须有人特意触发一次」这个约束已经消失。** DLL 现在常驻一个 `0x160EBE0`
的 hook，平时微信里**任何一次表情往来**都会自动把任务上下文落盘刷新。

实测：装上 hook 后用户随手发一个表情 → `ctx_override.txt` 在 **15:05:36** 自动刷新，
**全程没有任何 frida 进程**（残留计数 0）；随后 DLL 独立发出 `type=12`，对端收到。

至此生产链路上不再有需要人工介入的环节：

| 环节 | 之前 | 现在 |
|---|---|---|
| 刷新上下文 | 人工跑 frida 脚本 + 特意发一个表情 | **DLL 自动捕获**（平时正常用微信即可） |
| 发送表情 | 写 outbox（`type=8`/`12`） | 同左，无变化 |

### 31.2 实现

新增于 `send_sticker_tpl.c`：`wxb_install_pack_hook()` / `wxb_uninstall_pack_hook()` /
`wxb_pack_hook_installed()`，由 `lifecycle.c` 的 `bridge_init()` 在 worker 启动时自动安装。

**hook 点**：`0x160EBE0`（pack 提交）。该处前 16 字节为

```
55 41 56 56 57 53 48 81 EC E0 01 00 00 48 8D AC
│           │  └─ 第 7 字节 48 是 `sub rsp,0x1e0` 的前缀
│           └─ 前 6 字节恰好是 6 条完整指令
└ push rbp / push r14 / push rsi / push rdi / push rbx
```

⇒ **只能切 6 字节**（`E9 rel32` + 1 字节 `90` 填充）。按 7 字节切会切断 `sub rsp,0x1e0`，
trampoline 里就是半条指令，跳回去必崩——这也解释了为什么不能直接复用 `receive.c`
那套为接收函数定制的 7 字节 trampoline。

**trampoline**（自建，保存易失寄存器）：
```
pushfq / push rax,rcx,rdx,r8,r9,r10,r11 / sub rsp,0x28
mov rax,<回调> / call rax / add rsp,0x28
pop r11,r10,r9,r8,rdx,rcx,rax / popfq
<原 6 字节指令> / mov rax,<target+6> / jmp rax
```
栈对齐：入口 `rsp%16==8`，经 pushfq(8) + 7 寄存器(56) + 0x28 后为 `0`，满足调用约定。

**回调 `wxb_pack_probe(container, cfg, a3, a4)`**（与 x64 约定一致，直接接收 pack 的入参）：

```
container+0x08 → model      ，要求 [model] == base+0x82CB8D8（表情信封）
model+0x660    → content    ，要求 [content] == base+0x8755528（对象体）
content+0x08   → 类型字段    ，要求 ∈ {3, 5}（收藏 / 表情包）
cfg[0]/cfg[8]  → body/ctrl  ，要求 body == ctrl+0x10 且 [ctrl] == base+0x7F5F398
→ 满足则落盘 ctx_override.txt
```

### 31.3 安全性论证

| 风险 | 处置 |
|---|---|
| 切断指令 | 安装前逐字节比对站点 `55 41 56 56 57 53`，不匹配就**放弃安装**（不硬来） |
| 破坏调用方状态 | hook 在函数最开头，此时除入参寄存器外无有效状态；trampoline 保存全部易失寄存器 + flags |
| 读内存越界 | 回调整体 `__try/__except` 包裹，异常一律吞掉，**绝不冒泡到 pack 调用方** |
| 污染其它消息 | 三重判据（信封 vtable + 对象体 vtable + 类型字段 ∈ {3,5}），文本/图片不会命中 |
| 安装失败 | `bridge_init()` 里**不阻塞启动**，仅退化为「需要人工触发一次」 |

### 31.4 意外收获：系统会自我维持

我们自己发出的表情**同样要经过 pack**，因此 hook 也会捕获我们自己产生的上下文
（实测发送后 `ctx_override.txt` 从 15:05:36 刷新为 15:05:55）。
⇒ 只要出现过一次发送，上下文就会持续被刷新，**不会退回到「需要人工触发」的状态**。

### 31.5 验证记录

```
# 装 hook（DLL 注入时自动）
tpl_debug: pack hook installed: 自动捕获任务上下文已启用
weixin procs = 5（未崩）

# 用户随手发一个表情（无 frida）
ctx_override.txt  mtime = 15:05:36
BODY=18e45e64a90  CTRL=18e45e64a80

# DLL 独立发 type=12
result: {"ok":true,"message":"pack_sticker submitted (tpl=0)"}
tpl_debug: ctx override: body=0000018E45E64A90 ctrl=0000018E45E64A80   ← 校验通过
```

### 31.6 仍未验证 / 可继续

- **「什么时候该发哪一枚」是上层决策**，DLL 只提供能力。若要让飞知自动挑表情，
  在 `autoreply.py` 里加一个约定标记（类似现有的 `[img:名字]`，如 `[sticker:名字]`）
  并映射到 `type=12` 的模板序号即可。
- 跨专辑表情（`slot1` 不同）仍未验证。
- 模板表扩充：表情包当前内置 4 枚，名字（slot10）需逐枚采集。
