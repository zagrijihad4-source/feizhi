# wxhook — 微信 PC 4.1.9.23 Hook 桥

在本机把微信 PC 端降级到 **4.1.9.23**，注入自编译的 hook DLL，实现**程序化收发消息**。
选定 4.1.9.23 的唯一原因：这是唯一有现成偏移表（`wx-basic-bridge`）的 4.1 版本。

---

## 一、当前状态（已验证）

| 项目 | 状态 |
|---|---|
| 微信版本 | `C:\Program Files\Tencent\Weixin\Weixin.exe` = **4.1.9.23** |
| 登录账号 | 小号 `<WXID_SELF>_dfb4`（昵称「绯栀」） |
| Hook DLL | `<PROJECT_ROOT>\dist\wx_hook_bridge.dll`（clang 编译，70KB，x64） |
| 注入方式 | `SetWindowsHookEx(WH_GETMESSAGE)` + 远程 `LoadLibraryW` |
| 发送 | **已验证**，`send_text ok` |
| 接收 | hook 已装载（`DoAddMsg` 入口被 `E9` 改写，字节级确认），待真实入站消息触发 |
| 抗升级 | ACL 拒绝写入 + 更新器改名 + hosts 封锁 + 清理更新缓存，已验证版本不再被改 |
| 自动重注入 | 守护进程 + 开机自启，微信重启后 **约 10 秒内自动恢复 hook** |

---

## 二、目录结构

```
<PROJECT_ROOT>\
├─ weixin_4.1.9.23.exe          微信 4.1.9.23 官方安装包（SHA256 已校验）
├─ dist\wx_hook_bridge.dll      编译产物（注入用）
├─ build_clang.ps1              clang 构建脚本（绕过缺失的 MSVC C++ 负载）
├─ reinject.py                  一次性注入：找进程→校验版本→注入→退出
├─ reinject_daemon.ps1         常驻守护：检测 hook 缺失即重注入
├─ auto_login.ps1              尝试自动点掉"进入微信"确认页（尽力而为）
├─ lockdown.ps1                重新降级 + 锁死安装目录（提权运行）
├─ freeze_update2.ps1          冻结更新：改名更新器/清缓存/封 hosts（提权运行）
├─ start_daemon_hidden.vbs     无窗口启动守护
├─ logs\reinject.log           守护日志
├─ backup_xwechat_files\       微信数据全量备份（9.235 GB / 10485 文件）
├─ app_4.1.13.65\              原 4.1.13.65 安装目录副本
├─ reg_*.reg                   注册表导出（4 份）
└─ wx-basic-bridge\            上游工程（含注入器、文件桥协议）
```

启动文件夹已放置 `wxhook_reinject_daemon.vbs`，开机自动拉起守护。

---

## 三、日常使用

### 发送消息

```powershell
cd <PROJECT_ROOT>\wx-basic-bridge
python python\tools\wx_basic_bridge.py --root <PROJECT_ROOT>\wx-basic-bridge send <目标wxid> "内容" --timeout 25
```

成功返回：
```json
{"ok": true, "seq": "...", "command": "send_text", "message": "send_text ok"}
```

#### 目标必须用 wxid，不要用昵称

实测踩坑：用昵称（如 `<OWNER>`）当目标时，命令**照样返回 `send_text ok`**，但消息实际投递失败——
微信会新建一个名为「微信用户」的会话，界面显示 **「对方还不是你的朋友」+ 红色感叹号**。

`send_text ok` 只代表命令被 worker 接受，**不代表对方能收到**。判定真实投递要看界面：
- 会话列表预览是否更新为该条内容
- 聊天区气泡有无红色感叹号

已知可靠的目标：
- `filehelper` —— 微信内置的固定对象，实测稳定可用，适合自测
- `wxid_xxx` —— 好友的真实 wxid

查看某人的 wxid：微信里打开与其的聊天 → 右上角「…」→ 资料页可见微信号/wxid；
或用 `python python\tools\inject_bridge.py --list` 之外的方式从会话对象读取。

### 接收与归档

hook 把每条入站消息写成 `bridge\inbox\<...>.json`，用归档器落到 SQLite：

```powershell
cd <PROJECT_ROOT>\wx-basic-bridge
python python\tools\wx_basic_bridge.py --root . watch      # 持续归档
python python\tools\wx_basic_bridge.py --root . show --limit 20   # 查看最近消息
python python\tools\wx_basic_bridge.py --root . ingest     # 一次性导入
```

**重要：自己发出的消息不走 `DoAddMsg` 入站路径**，只有外部账号发来的消息才会进 `inbox`。
所以想验证接收，必须**用另一个账号给当前登录的小号发消息**，自己给自己发不会触发。

### 接收状态说明（诚实标注）

接收方向当前处于：**hook 已实装并字节级确认，但尚无真实入站消息触发过**。

已确认的部分：
- `DoAddMsg`（RVA `0x166A6BF`）入口 6 字节被改写为 `E9 3C 59 98 FE 90 90`
- **跳转目标解码**：`E9` 后 4 字节为有符号相对偏移，`target = entry+5+rel = 0x7FFEFFAA0000`
- **注意**：这个 target **不在 Modules 列表里**——trampoline 是 `VirtualAlloc` 动态分配的
  匿名内存，不属于任何模块。早先我拿它和 hook DLL 基址比，误判过一次。
- **trampoline 结构已完整反汇编验证**（`verify_recv_hook.py`）：

```
+00: 9C                               pushfq
+01: 50 51 52 41 50 41 51 41 52 41 53 保存 rax,rcx,rdx,r8,r9,r10,r11
+0c: 48 81 EC 80 00 00 00             sub rsp, 0x80
+13: F3 0F 7F 44 24 20 ...           保存 XMM0-5
+3a: 48 8B 46 18                      mov rax, [rsi+0x18]   <- 消息对象
+3e: 48 85 C0 / 74 0F                 test rax,rax ; jz
+43: 48 89 C1                         mov rcx, rax          <- msg_base 参数
+46: 48 B8 C0 36 B4 DC FF 7F 00 00    movabs rax, 0x7FFFDCB436C0
+50: FF D0                            call rax              <- process_message
+52..+7f:                            恢复 XMM / add rsp,0x80 / 恢复通用寄存器
+87: 48 B8 C6 A6 11 01 FF 7F 00 00    movabs rax, 0x7FFF0111A6C6
+91: FF E0                            jmp rax               <- 回到 DoAddMsg+7
```

关键校验点：
- `process_message` = `0x7FFFDCB436C0`，**落在 hook DLL 范围内** ✓
- 跳回目标 `0x7FFF0111A6C6` = `0x166A6BF + 7`，正好是覆盖区（6 字节）之后的下一条指令 ✓
- hook 用了 `call rax` 间接调用，所以扫 `E8` 相对调用是找不到的，要按 `48 B8 imm64` + `FF D0` 匹配
- 对照 `SEND_CALL1`（`55 56 57 48 83 EC 50`）、`SEND_CALL3`（`55 41 56 56 57 53`）仍是原始序言，
  说明只有接收侧打了 inline hook，发送侧走直接调用不经 hook，与设计一致

复验命令：

```powershell
python <PROJECT_ROOT>\verify_recv_hook.py    # 只看 hook 完整性
python <PROJECT_ROOT>\check_recv.py          # 一键体检：hook + inbox + 归档 + 状态文件
```

`check_recv.py` 是最省事的入口——它一次性输出 hook 校验结果、inbox 里有没有消息、
control 状态文件内容、SQLite 归档情况，并在结尾给出结论。

待验证的部分：收到外部消息后 `inbox` 是否落地 JSON 文件（需要一条真实入站消息）。

下列路径**已实测都不会触发接收**，不要用来做接收验证：
- 自己发消息给文件传输助手（自己发的消息不走 `DoAddMsg`）
- 点击会话列表里已有未读标记的订阅号/服务号会话（历史消息从本地库加载，不经过 `DoAddMsg`）
- 点击「腾讯新闻」等未读会话（同上，inbox 60 秒轮询无变化）



### 发送可见性验证方法（已实测）

想确认消息真的发出去了，用「PostMessage 点会话列表 + PrintWindow 截图」：

```powershell
# 1) 发送
python python\tools\wx_basic_bridge.py --root . send filehelper "VISIBLE-CHECK-020141" --timeout 25

# 2) 点会话列表第一行（要用 PostMessage，坐标取客户区）
#    窗口左上角 + (150,125) 即第一条会话，转客户区后 PostMessage WM_LBUTTONDOWN/UP

# 3) PrintWindow(hwnd, hdc, 2) 截图，肉眼确认气泡
```

实测结果：消息出现在会话列表预览与该会话聊天区，且**历史多条 hook 发送记录都在**，
证明发送链路真实落到了微信界面，不是只改了内部状态。


### 手动重注入（一般不需要，守护会做）

```powershell
python <PROJECT_ROOT>\reinject.py
```

它自己会在 hook 装载后立即退出，适合被脚本/守护调用。

### 查目标进程

```powershell
python <PROJECT_ROOT>\wx-basic-bridge\python\tools\inject_bridge.py --list
```

认准 `weixin_base` 非零、`version=4.1.9.23` 的那一行，其他 `Weixin.exe` 都是子进程。

---

## 四、微信重启后的流程

1. 重新打开微信（`C:\Program Files\Tencent\Weixin\Weixin.exe`，**必须以普通权限启动**）
2. 若停在「进入微信」确认页，守护会自动投递点击（`auto_login.ps1`）；若未生效，手动点一下
3. 守护进程会在 10 秒内检测到 hook 缺失并自动注入
4. 确认 `<PROJECT_ROOT>\logs\reinject.log` 出现 `INJECT VERIFIED`

### 「进入微信」自绘按钮的点击方式（实测结论）

这个按钮是 `mmui::XOutlineButton` 自绘控件，**只有 `PostMessage(WM_LBUTTONDOWN/UP)` 有效**：

| 方式 | 结果 |
|---|---|
| UIA `InvokePattern.Invoke()` | 返回成功但**无任何行为** |
| `SetCursorPos` + `mouse_event` 合成鼠标 | 无效 |
| `PostMessage(WM_LBUTTONDOWN/UP)` + `ScreenToClient` | **有效**（已验证） |

坐标要用客户区坐标：先取 UIA `BoundingRectangle`（屏幕坐标），再 `ScreenToClient`。

### 必须用普通权限启动微信

**提权启动的微信实例会出问题**：它的模块列表读不到（`MODULE_COUNT=0`），守护无法识别并注入 hook，
普通权限的 `Stop-Process` 也杀不掉它，它会占住微信单实例锁导致后续实例起不来。
如果误用了提权启动，跑 `<PROJECT_ROOT>\reset_stack.ps1`（提权）清理。

由守护调用的注入链始终是普通权限，所以正常流程不会踩到这个问题。

---

## 五、故障处置

### hook 没装上

看日志：`Get-Content <PROJECT_ROOT>\logs\reinject.log -Tail 30`

- `no Weixin host with Weixin.dll` → 微信没启动，或还在启动早期
- `version=X != 4.1.9.23 skip` → 微信被升级了，见下一节
- `inject NOT verified` → 手动跑 `python <PROJECT_ROOT>\reinject.py` 看具体报错

### 微信版本被升级了

**实测：更新防护会被绕过，必须重新降级。** 2026-10-13 02:20 微信自行升到 4.1.15.13，
整个 `4.1.9.23\` 目录连同我改名的 `.frozen` 更新器一起被替换掉，hosts 的 dldir 封锁也没拦住
（微信不在那些域下载）。所以**只锁更新器是不够的**。

**现在有两层处理：**

1. **被动防护**：`lockdown2.ps1` 用精确 ACL 阻止微信新建版本目录
2. **主动兜底**：守护进程检测到版本被改时，**自动**触发降级（`lockdown2.ps1`，提权静默执行），
   并在降级完成后把微信重新拉起来。带 10 分钟冷却，避免反复触发陷入循环。

所以理论上即使防护被绕过，守护也会在下一轮（默认 15 秒）内发现并把版本降回去。
日志里会看到：

```
pid=NNNN version=4.1.15.13 != 4.1.9.23 -> auto-downgrade
triggered lockdown2.ps1 (elevated, silent UAC)
relaunching Weixin after downgrade
```

手动降级仍可用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <PROJECT_ROOT>\lockdown2.ps1
```

`lockdown2.ps1` 做的事：杀进程 → 剥离旧 Deny 规则 → 清更新缓存 → 重装 4.1.9.23 →
**只拒绝 `CreateDirectories`**（而非全量 Deny）→ 改名更新器 → 校验。

#### 防护要点：只拒绝"创建目录"，不要拒绝"写文件"

| 方案 | 挡升级 | 微信能否启动 |
|---|---|---|
| 全目录 `Deny Everyone` 写入 | 挡住 | **不能**——微信启动即秒退（13/13 失败） |
| **只 Deny `CreateDirectories` + `DeleteSubdirectoriesAndFiles`** | 挡住（升级要新建 `<版本号>\` 目录） | **可以**（文件写入不受影响） |

`lockdown2.ps1` 的自检输出就体现了这个区别：

```
file write: OK            <- 微信仍能写文件
dir create: BLOCKED       <- 新建版本目录被拒 -> 升级失败
```

#### 更新链路（实测）

微信启动后自己下载新版分包到 `%APPDATA%\Tencent\xwechat\update\download\<版本>\`，
然后拉起 `WeixinUpdate.exe` 覆盖安装。改名安装目录里的更新器**无效**（新包会带新的更新器），
hosts 封 `dldir*` 也**无效**（不走那些域）。真正有效的是阻止它建新版本目录。

### hook 是否被调用过？看 recv_debug.txt

`process_message` 每次执行都会往 `bridge\control\recv_debug.txt` 追加一行：

```
recv id=... local=... type=N/M from=... to=... peer=... in=0 out=1
```

**这个文件存在 = hook 至少被调用过一次**；不存在 = 从未被调用。

实测结论：
- **出站消息（自己发的）不触发 `DoAddMsg`** —— 发送多条消息后该文件仍未创建
- 只有**入站消息**（对端发来的）才会触发

注意 `process_message` 内部**不过滤方向**：只要被调用，无论 in/out 都会写 inbox 和该日志。
所以它是个可靠的"hook 是否活过"探针。

### 守护进程没在跑

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File <PROJECT_ROOT>\reinject_daemon.ps1 -IntervalSec 10
```

开机自启项在：`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\wxhook_reinject_daemon.vbs`

### 完全回滚到 4.1.13.65

1. **先撤掉目录锁**（否则装不进去）：
   - 资源管理器 → 右键 `C:\Program Files\Tencent\Weixin` → 属性 → 安全 → 高级 → 删除所有 `拒绝` 项
2. 重新下载 4.1.13 安装包：`https://dldir1v6.qq.com/weixin/Universal/Windows/WeChatWin_4.1.13.exe`
   （或直接用本地副本 `<PROJECT_ROOT>\app_4.1.13.65\`）
3. 运行安装包覆盖安装
4. 撤销 hosts 封锁：编辑 `C:\Windows\System32\drivers\etc\hosts`，删掉 `# wxhook-freeze` 到 `# wxhook-freeze-end` 之间内容
5. 恢复更新器名字：把 `WeixinUpdate.exe.frozen` 改回 `WeixinUpdate.exe`
6. 数据如需恢复：用 `<PROJECT_ROOT>\backup_xwechat_files\` 覆盖 `D:\xwechat_files\`

---

## 六、关键事实与技术要点

**为什么要降级而不是改新版**：偏移表只对 4.1.9.23 有效。自己为新版定位 4 个函数地址约需 2~5 天，降级只需装一次。

**编译链**：本机 VS 2022 BuildTools **没有 C++ 工作负载**（无 `vcvars64.bat`），
所以用 winget 装的 LLVM-MinGW + `-fms-extensions`（该版本 clang 已无 `-fms-seh` 参数，
代码里的 `__try/__except` 靠前者才能过）。构建脚本 `build_clang.ps1`。

**注入器为什么不直接用上游的**：上游 `inject_bridge.py` 注入完会进入 `while True` 常驻循环，
不适合被守护同步调用，所以写了 `reinject.py`（注入后 `os._exit`）。

**守护里为什么不用 `Start-Process`**：在隐藏窗口的守护进程里 `Start-Process` 起 Python 会静默失败
（无进程、无报错），改用 .NET `ProcessStartInfo` 才稳定。

**微信的更新链路**（实测）：微信启动后自己下载新版分包到
`%APPDATA%\Tencent\xwechat\update\download\<版本>\`，然后拉起 `WeixinUpdate.exe` 覆盖安装。
改名安装目录里的更新器**无效**（新包会带新的更新器），必须靠目录 ACL 拒绝写入。

**接收 hook 的落地形式**：`DoAddMsg`（RVA `0x166A6BF`）入口被改写为 `E9 xx xx xx xx 90 90`，
跳向 DLL 内 trampoline；`SEND_CALL1`/`SEND_CALL3` 保持原始序言，发送走直接调用不经 hook。

---

## 七、风险提示

- Hook 属于非官方客户端行为，社区统计显示 hook 用户封号概率显著高于普通用户
  （WeChatFerry 作者 2025-04 调查：约 15% 从未被封，本地环境封号率最高）。**当前用的是小号，符合最小风险原则。**
- 数据已全量备份，但 hook 崩溃仍可能损坏库文件；出问题优先用备份覆盖。
- `hosts` 只封了 `dldir*.qq.com`（更新下载域），**没有**动 `weixin.qq.com` 等业务域，避免影响登录与消息通道。
