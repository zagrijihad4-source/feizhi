# 微信 PC Hook 项目 · 交接摘要

> 更新时间：2026-10-18 10:30
> **项目全景（架构 / 各模块实现路线 / 关键发现 / 实测数据 / 当前状态）见 `PROJECT_OVERVIEW.md`** —— 想一次看全貌就读它
> 完整技术档案见 `TASK_LOG_发送收藏表情.md`（**31 节**，含每步实测证据）
> 朋友圈（发纯文字动态）见 `TASK_LOG_朋友圈.md`：**已真实发布成功，并已做成无人值守**
> （`feizhi_pc\moments.py` UI 链路 + `post_moment.py` 单条入口 + `moment_scheduler.py` 定时调度）。
> 后台模式：切页/长按/写入走 PostMessage + WM_CHAR，不抢前台；
> 只有点「发表」需要真实鼠标，所以**锁屏时发不了**（调度器会自动顺延到解锁后）。
> 绯栀的长期记忆见 `TASK_LOG_记忆.md`（三层：24 条原始消息 + 模型抽取的事实/情节，`feizhi_pc\memory.py`）。
> 服务启动：`pythonw run.py both`（自动回复 + 主动搭话；记忆随回复自动更新）。
> 本文是**入口文档**：先读这里，需要细节再翻 TASK_LOG 对应小节。

---

## 一句话现状

**文本发送、图片发送、消息接收、收藏表情发送——四项全部打通。**

收藏表情的钥匙是「**载体替换**」（TASK_LOG §26）：让用户自然发送任意一个收藏表情充当
**载体**，在 pack 提交点 `0x160EBE0` 的**入口**处，把该消息内容对象的 6 个字符串槽
**就地覆写**成目标表情的数据。任务上下文、信封、委托、队列全部由微信自己产生。
**已由对端实测确认收到的是目标表情**，而非本地显示幻觉。

**当前唯一限制：每次发送仍需一次真实点击**（任务上下文只能由微信产生，无法自造）。

**免点击也已打通**（TASK_LOG §27）：捕获一次自然发送时的**真实任务上下文**，之后即可反复复用。
实测 t+5s / t+60s / t+300s 三次复用**全部送达对端**，且消息内容由我们的内容对象决定。
⇒ **一次点击即可解锁 5 分钟内的全部自动发送**。

**并已固化进 DLL**（TASK_LOG §28）：DLL 自己读 `bridge\control\ctx_override.txt` 完成注入与发送，
**完全不需要 frida 常驻**。实测停掉 frida 后 DLL 独立发出 tpl=0 / tpl=1，对端两次均收到。

> **运维约束**：微信重启后上下文失效，但**DLL 会自己重新捕获**——
> 只要微信里再有任何一次表情往来（你发的、或别人发你回的），
> `ctx_override.txt` 就会自动刷新，**不需要跑任何脚本、也不需要特意操作**。
> 前提是 `tpl_debug.txt` 里出现过 `pack hook installed: 自动捕获任务上下文已启用`（TASK_LOG §31）。
>
> 若该 hook 未装上（会打印 `pack hook install failed`），才需要退回人工方式：
> `python frida_ctx_reuse.py --dump-ctx --cmd-type 8 --schedule 3` 并手动发一个表情。
> 另外注意上下文在被使用前寿命很短（约 30 秒，§30.4），所以人工方式必须配 `--schedule 3`。
> 失效时 `tpl_debug.txt` 会打印 `ctx override: 不可用（缺失/校验失败）`，
> 此时只表现为「发送失败」，不会崩。

---

## 环境

| 项 | 值 |
|---|---|
| 目标 | 微信 PC 4.1.9.23（`C:\Program Files\Tencent\Weixin\Weixin.exe`） |
| 注入方式 | `SetWindowsHookExW(WH_GETMESSAGE)` + 远程 `LoadLibraryW`，导出 `WxBridgeWorker` |
| 桥根目录 | `<PROJECT_ROOT>\wx-basic-bridge`（工作目录 `bridge\`） |
| 构建 | `<PROJECT_ROOT>\build_clang.ps1`（clang / MinGW，无 MSVC） |
| 部署 | 产物 → `wx-basic-bridge\dist\wx_hook_bridge.dll`，**mtime 设 +2 天**，再跑 `python <PROJECT_ROOT>\force_inject.py` |
| 保活 | `reinject_daemon.ps1`（每 15 秒检查，进程常驻） |
| 源码 | `wx-basic-bridge\native\wx_hook_bridge\src\` |

### 运维铁律（用血换的）

1. **注入前必须清空 `bridge\outbox\next.txt`** —— 残留命令会被新 worker 立即执行，可能导致微信崩溃。
2. **同一函数内不要挂多个 frida 内部断点** —— 会互相破坏并让微信退出（12:53 那次的成因）。
   安全做法：**DLL 侧打点**，或每次只 hook **互不相同**的函数。
3. 编辑 `.ps1` 会丢 UTF-8 BOM，PS 5.1 按 GBK 解析导致中文乱码——改完必须补 BOM。
4. **载体替换路线不写 outbox、不构造对象**，只 hook `0x160EBE0` 并在入口改字符串。
   出问题把脚本停掉即自动恢复（hook 卸载后一切如常），无需重启微信。

---

## 可用能力

### 命令协议

写入 `bridge\outbox\next.txt`（UTF-8 无 BOM）：
```
<seq>\t<type>\t<to_wxid>\t<content>
```
结果落在 `bridge\control\result_<seq>.json`。

| type | 功能 | content |
|---|---|---|
| `1` | 文本 | 文本 |
| `3` | 收藏表情（旧链 `0x15F35C0`/`0x17040A0`） | 预设编号 —— 已知失效 |
| `4` | 收藏表情（模板路径：`0x1AFE710` 信封 + 发送入口 `0x16A60D0`） | 模板序号（0 起） |
| `5` | 只构造内容对象并 dump（**零风险**） | 模板序号 |
| `6` | 构造「内容对象→信封→TaskContext」全链并 dump（**零风险**） | 模板序号 |
| `7` | 重扫进程内线程 TLS（诊断） | 任意 |
| `8` | **收藏表情（pack 路线）** | 模板序号 —— 读 `ctx_override.txt` 取真实上下文后已实测送达（§27/§28） |
| `9` | 自定义类型码消息模型 | `<type_code>\t<payload>` |
| `10` | **图片** | 本地图片**绝对路径** |
| `11` | 图片（类型码可配） | `<type_code>\t<path>` |
| `12` | **表情包（表情商店添加）表情** | 模板序号 —— 见 §30 |

### 已验证可用的功能

| 功能 | 验证方式 | 备注 |
|---|---|---|
| **文本发送** | 对端实际收到 | 长期稳定 |
| **图片发送** | 对端实际收到并正常显示 | 只接受类型码 **3**；**GIF 会被静态化（只取首帧）** |
| **消息接收** | `bridge\inbox\*.json` | 含完整消息体（XML 原文） |
| **收藏表情发送** | 对端实际收到目标表情（2026-10-14 13:32） | 走**载体替换**，需一次点击，见 §26 |
| **收藏表情自动发送** | 对端实收「正面微笑」（2026-10-14 13:50） | 复用捕获的任务上下文，**免点击**，见 §27 |
| **表情包表情发送** | 对端收到的不是被点的那枚（2026-10-14 14:26） | **载体替换**已通，见 §29 |
| **表情包表情自动发送** | 对端实收（2026-10-14 15:05） | `type=12`，**免点击**，见 §30 |
| **上下文自动捕获** | `ctx_override.txt` 自动刷新（2026-10-14 15:05:36，无 frida） | DLL 常驻 hook `0x160EBE0`，见 §31 |
| 表情构造/对照工具 | 逐字段与原生一致 | 见 TASK_LOG §17、§21、§23 |

### 飞知自动回复（`<PROJECT_ROOT>\feizhi_pc\`）

已接入图片能力：

- `bridge.py` → `HookBridge.send_image(wxid, absolute_path)`（type=10）
- `stickers.py` → 本地图片库 `IMAGE_DIR = <PROJECT_ROOT>\feizhi_pc\images`
  - `list_images()` / `find_image(name)` / `image_prompt_hint()`
- `autoreply.py` → `_send_one(peer, text)` 支持三种整条形态：
  - `[img:名字]`  → 发本地图片库里的图
  - `[draw:场景]` → **现场生成**一张照片再发（`imagegen.py`，慢，1~3 分钟）
  - 其它 → 普通文本

**保活（2026-10-14 新增）**：`feizhi_daemon.ps1` + `start_feizhi_daemon_hidden.vbs`
—— 每 30 秒检查一次，进程不在就拉起（实测：杀掉后 1 秒内恢复）。
用 `([wmiclass]'Win32_Process').Create()` 拉起，不用 `Start-Process`（会阻塞调用方）。

**拟人化时序（`humanize.py`，2026-10-14 新增）**：
- 反应延迟按「正在看手机 / 在忙 / 离开了」三段抽样，再乘时段系数（深夜 ×5）
- 打字时长按字数算（不再写死 1.5 秒上限）
- **发送整体挪到后台线程 + 队列**：否则几十秒的拟人延迟会把收消息的主循环卡住
- 关闭方式：环境变量 `FEIZHI_HUMANIZE=0`

**人格（傲娇）—— 2026-10-15 重写，别再只改 persona.py**：
- 人格由**两处**共同决定：`feizhi_phone_bridge/reply_generator.py` 的 base prompt（骨头）
  + `persona.py` 的 `style_block()`（皮）。**只改 persona.py 治不了病。**
- 旧版病症（真实聊天 10-14 23:48~10-15 00:13）：他连问四次「你到底喜欢我吗」，
  绯栀四次全转成「你先说那个她是谁」；他要照片被「你先回答我」挡回。
- 根因：原版 base 把绯栀写成**理性审校者** ——
  「先判断对方说法是否合理、信息是否充分」「不要用无条件附和来假装亲近」。
  情话被当成待核查的命题，结构永远是「先质疑，再找补」。
- 修法（两层都动了）：
  1. `autoreply.FeizhiReplyGenerator._build_system` 里 `_OLD_CORE`/`_NEW_CORE`
     **整段替换**那段审校者文本 → 女朋友版（含"先接住，再嘴硬"）。
     若原版文本将来变了会打 warning 并退化为逐句替换，注意看日志。
  2. `persona.PERSONA_STYLE` 改成**正反例对照**（错法/对法各给句子），
     而不是光下禁令；`PROBE_STYLE` 明确禁止取证式追问。
  3. `proactive.py` 的 `PROACTIVE_SYSTEM` + `FALLBACK_LINES` 同步换成傲娇版
     （旧版是「主人」「任性地占一下消息列表」的黏人时期残留，且 LLM 失败会直接漏出）。
     并给 `_generate()` 注入最近 6 条历史——之前不带历史，同一天连发过两条「橘猫」。
- 验收脚本（只生成、不发送）：`tmp\test_persona2.py`、`tmp\test_proactive.py`，
  输出落在同目录 `persona_test2.txt` / `proactive_test.txt`。
- **改完必须重启本体**：Python 不热加载，`run.py both` 启动时就把模块读进内存了。
  `Stop-Process` 掉本体即可，`feizhi_daemon.ps1` 会在 30 秒内拉起新进程。
  重启前先确认 `bridge\outbox\next.txt` 是空的、没有待发的拟人延迟消息（队列在内存里，会丢）。

**人物一致性**：
- 外貌锚点在 `imagegen.PERSONA_ANCHOR`，每次出图都拼在场景前面
- **参考图锁脸已打通**：基准照经 `/api/uploads/raw` 上传成公网 URL，
  写进 `image_config.json` 的 `sanbao.personaRefUrl`，出图时以 `images: [url]` 传入。
  实测有效——换场景后仍是同一张脸。
- 本地副本：`images\_persona_ref.jpg`；换脸用 `tmp\switch_face.py <新图>`

**生图网关（`image_config.json`）**：
| 线路 | 域名 | 协议 | 备注 |
|---|---|---|---|
| 主 | `sanbaobeauty.com` | `POST /openapi/v1/images` + 轮询 `/{id}` | 返回 **201** 才算成功；`quality` 只认 high/medium/low；参考图字段是 **`images`**（URL 数组） |
| 备 | `synapse-ai.uk` | `POST /v1/images/generations` | OpenAI 兼容；比例映射到 size |
| 弃 | `api.video.aistarslab.com` | `/generation/create/image` | 账号积分不足，2026-10-14 停用 |

**三宝的两个坑**：
1. **prompt 越长越容易被拒**，且**人物外貌描写越具体越容易触发审查**——
   报错是「未生成预期内容，请调整提示词后重试」（**积分会退回，不损失**）。
   通过例：`19岁中国女孩，鹅蛋脸，细长杏眼，黑长直发中分，素颜，浅灰针织衫。`
   被拒例：`…圆脸饱满…酒窝`、`…小脸尖下巴，丹凤眼`。
2. **创建成功返回 201**（不是 200），轮询 status 为 `queued/processing/succeeded/failed`。

**换人物基准照的完整流程**（需要登录 token，token 约 4 天过期）：
```
tmp\gen_faces.py          生成候选正面照 -> images\faces\
tmp\switch_face.py <图>    上传 + 写配置 + 重启 feizhi
```

---

## 语音消息（AI 发语音）—— 2026-10-15 打通

**结论：微信 4.1.9.23 能发语音，而且不需要碰 CDN 协议。**
微信 4.1.9 是 PC 端首次支持发语音的版本（输入框右下角话筒，快捷键**按住右 Alt**说话、松开发送）。
语音消息走 **SILK v3**，编码器是 `VoipEngine.dll!SKP_Silk_SDK_Encode`（**导出**，可直接 hook）。
Weixin.dll 只静态导入 3 个 DLL，是靠 `GetProcAddress` 动态拿这个函数的。

### 注入点（实测参数）

| 项 | 值 |
|---|---|
| 编码器 | `VoipEngine.dll!SKP_Silk_SDK_Encode` @ 0x7ffb563eefa0（基址随进程变） |
| 采样率 / 声道 | **16000 Hz / 单声道 / s16le** |
| 每帧样本数 | **320**（= 20ms，标准 SILK 帧） |
| PCM 输入 | **第 3 个参数 `args[2]`**，指向微信自己的堆缓冲，可写 |
| 内部调用链 | `Weixin.dll+0x60c8537 → +0x60c86bf → +0x60c8fc3 → Encode` |

做法：在 `onEnter` 里把 `args[2]` 指向的 320 个 int16 覆写成 TTS 音频的对应帧，
按调用顺序推进读指针即可 —— **编码、上传、构造 voicemsg、发送全部由微信自己完成**。

### 触发方式

必须让微信**进入录音状态**：微信窗口在前台 + 输入框有焦点 + 按住**右 Alt**，松手即发送。
键盘层用 `keybd_event(0xA5, …, KEYEVENTF_EXTENDEDKEY)`（右 Alt = VK_RMENU）。

> ⚠️ **Windows 前台锁定**：`SetForegroundWindow` 会**静默失败**（只剩任务栏闪烁），
> 必须校验返回值并重试：先 `AttachThreadInput + SetForegroundWindow`，
> 仍失败则 `SW_MINIMIZE + SW_RESTORE`。不做这层，按键会打到浏览器上，
> 表现为「Encode 调用数为 0」（13:30 踩过）。

### 工具

| 文件 | 用途 |
|---|---|
| `<PROJECT_ROOT>\frida_voice_inject.py` | 主线：装 hook → 送 PCM → 切前台 → 按右 Alt → 喂完即松手发送 |
| `<PROJECT_ROOT>\frida_voice_recon.py` | 侦察：录音时加载了什么模块、`GetProcAddress` 拿了什么 |
| `<PROJECT_ROOT>\frida_voice_probe.py` | 参数探测：打印每帧样本数 / 采样率 / 调用栈 |
| `<PROJECT_ROOT>\feizhi_pc\tts.py` | 文本 → 16k 单声道 PCM（MiMo TTS + ffmpeg，带缓存） |
| `<PROJECT_ROOT>\feizhi_pc\tts_config.json` | TTS 凭据与音色（**含 key，勿外泄**） |
| `<PROJECT_ROOT>\tmp\record_voice.ps1` | 独立录音脚本（含分级强前台），用于「武装 hook 后手动按」的验证 |

一条命令发一条语音：
`python frida_voice_inject.py --pcm <tts.py 产出的 .pcm>`

### TTS 现状（2026-10-15 实测）

- ✅ **MiMo（小米）**：`https://api.xiaomimimo.com/v1/chat/completions`，模型 `mimo-v2.5-tts`，
  要合成的文本放在 **assistant 消息**里，音频在 `choices[0].message.audio.data`（base64 WAV）。
  预置中文女声：**冰糖 / 茉莉 / 苏打 / 白桦**（另有 Mia/Chloe/Milo/Dean/mimo_default）。
  还有 `mimo-v2.5-tts-voiceclone`（传音频样本克隆音色）和 `-voicedesign`（文字描述音色）。
- ❌ **豆包**（`D:\Hermes work\doubao_tts.py`）：v1 缺 `app.appid` 报 400，补上后
  **401 `appID requested grant not found in SaaS storage`** —— key 已失效/未开通。
- ❌ **edge-tts 7.2.8**：微软收紧 Sec-MS-GEC 校验，**403**（升级到最新版仍如此）。
- ⚠️ **MiniMax**：`.env` 里没有 `MINIMAX_API_KEY`，未验证。

### 免前台（2026-10-15 已解决）

原方案要把微信切到前台（右 Alt 是窗口级快捷键），无人值守时会打断用户。
解法是**两条腿，缺一不可**：

| 手段 | 作用 |
|---|---|
| `keybd_event(VK_RMENU, 0, KEYEVENTF_EXTENDEDKEY)` | 让**系统键盘状态**里 Alt 真的按下 —— 微信会校验这个 |
| `PostMessage(hwnd, WM_KEYDOWN, VK_RMENU, lParam)` | 把按键消息**单独投递**给微信窗口 —— 不需要它有焦点 |

实测：不切前台连续录音 112 帧（2.24 秒），前台从始至终没变。

- **只用 PostMessage 不行**：录音只能撑 12 帧（0.24 秒）就断，因为系统里 Alt 没按下。
- **`WM_SYSKEYDOWN` 也不行**（实测 0 帧），必须 `WM_KEYDOWN`。
- `lParam = 1 | (0x38<<16) | (1<<24) | (1<<29)`；抬起时再或上 `(1<<30)|(1<<31)`。

### 上层集成（2026-10-15）

`feizhi_pc/voice.py`：

- `VoiceSender` —— 常驻 frida 会话（attach 一次反复用）、线程安全、掉线自动重连
- `MOODS` —— 8 个情绪档位：傲娇 / 心虚 / 委屈 / 温柔 / 慵懒 / 开心 / 强撑 / 娇嗔，
  每档对应一段 MiMo 导演指令
- `say(text, mood)` —— 合成 + 发送

`autoreply.py._send_one` 加了 `[voice:档位:文本]` 分支（与 `[img:]` / `[draw:]` 并列）：

```
[voice:傲娇:切，谁想你啊……就是有点无聊而已。]
[voice:就你？赢谁了，人机吗。]          ← 不带档位则回落默认「傲娇」
```

LLM 的用法约束写在 `persona.VOICE_STYLE`：大多数时候用文字、一天最多两三条、
他明确要语音时必须发、除了标记不要写别的字。

`feizhi_pc/tts.py`：文本 → 16k 单声道 PCM（MiMo + ffmpeg，带缓存与 429 退避）。
音色已固化为克隆音色，样本 `voice\feizhi_B_sample.wav`，配置见 `tts_config.json`。

### ⚠️⚠️ TTS 语速坑：绝不要对 MiMo 提「停顿」

**MiMo 对「停顿 / 顿一下」这类词是反向响应 —— 提一次就疯狂插静音。**

同一句 22 字「你快点回我啊，我等半天了，手机都快看没电了。」的 A/B 实测：

| 风格指令 | 时长 | 字速 |
|---|---|---|
| 只有导演指令（无节奏描述） | 5.60s | 3.93 字/秒 |
| + 「语速偏快」 | **5.28s** | **4.17 字/秒** ← 最快 |
| + 「又急又快，像急着把话说完」 | 6.08s | 3.62 字/秒 |
| + 含「该顿的地方轻轻顿一下（0.1~0.2 秒）」 | **20.16s** | **1.09 字/秒** ← 灾难 |

所以节奏指令只用**正向、简短、不含停顿语义**的措辞 —— `voice.RHYTHM` 现在就是
一句「语速自然偏快，连贯地说完。」。「慢」本身无害（慵懒/委屈档一直偏慢也没出事），
**「停顿」才致命**。

推论：想让语音有顿挫，不要去描述停顿，而要**用文本和标点制造快慢对比**；
音色档位只描述音色、气息与情绪倾向。

诊断工具：
`ffmpeg -f s16le -ar 16000 -ac 1 -i x.pcm -af silencedetect=noise=-40dB:d=0.25 -f null -`

字速参考：慢/拖音 2.0~3.0、常速 3.0~4.0、快读/急 4.5~7.0 字/秒。
修复后四条实测：快读 4.30、结巴+加速 3.98、爆发短句 2.93、拖音+顿 2.60 字/秒。

### 已知限制

- 语音发到微信**当前打开的聊天窗口**：用户手动切过会话就会发错地方。
- 微信单条语音上限 60 秒；时长由按住时长决定，数据喂完自动补静音。
- 依赖 frida 常驻；微信重启后 VoiceSender 会在下一次 say 时自动重连。

---

## 收藏表情：两条路线

### ✅ 载体替换（已打通，走这条）

```
用户点击任意收藏表情
  → 微信自己走完 UI/调度/任务上下文/信封/委托/cfg 全链
  → 在 pack 提交点 0x160EBE0 入口，我们把内容对象的 6 个字符串槽改成目标表情
  → 微信继续序列化、入队、发送
```

- 工具：`python frida_sticker_swap.py`（dry-run）/ `--live --target <idx>`（真替换）
- 模板：内置 7 个（`reports/sticker_templates.json` → `include/wx_sticker_templates.h`）
- 限制：模板集固定 7 个
- 关键安全依据：md5 恒 32 字符、URL 恒 324/322 字符，槽位 cap 恒为 47/335，
  **就地覆写永不触发重新分配**（TASK_LOG §26.3）

### ✅ 免点击复用（已打通，TASK_LOG §27）

```
1) hook 0x160EBE0(pack)  —— 自然发送时捕获真实 cfg[0]/cfg[8]（任务上下文）
2) hook 0xDB40           —— 自建发送到达时，把 d4 指向的 16 字节换成真实值
3) 之后 DLL 的 type=8 即可送达，无需再点击
```

- 工具：`python frida_ctx_reuse.py [--schedule 5,60,300]`
- 根因：`wxb_send_sticker_pack` 调 `0xDB40` 时第 5 参数 `d4 = arena+0x0A80` 是**全零假上下文**，
  而 `0xDB40` 会把 `[d4]/[d4+8]` 原样搬进 `cfg[0]/cfg[8]`（§27.2）
- 实测：t+5s、t+60s、t+300s 三次复用**全部送达对端**，内容由我们的内容对象决定
- 安全：只写自己 arena 的 16 字节；只对信封组委托（`0x83677E8`）注入；
  注入前双探测（可读性 + `ctrl` vtable RVA == `0x7f5f398`），失效即跳过

### ✅ 表情包（表情商店添加）表情——载体替换已验证（TASK_LOG §29）

协议同源（都是 `type=47`），但**内容对象布局与收藏表情不同**：

| | 收藏表情 | 表情包表情 |
|---|---|---|
| `+0x08` | 3 | **5** |
| 字段落点 | slot0/2/8（md5 ×3）+ slot6/7/9（三条 CDN URL） | **slot0（该表情 md5）+ slot1（专辑 ID）** |
| CDN | `vweinf.tc.qq.com/110/2040x`，bizid 1022 | `wxapp.tc.qq.com/262/20304`，bizid 1023，带 `aeskey` |
| 尾部 | 固定值 | `+0x160` 内联名字（如「空降」） |

- **`slot1` = `com.tencent.xin.emoticon.person.stiker_<…>`，同专辑内所有表情完全相同**，
  且跨多次发送不变 ⇒ 是专辑固有 ID，不是会话号（这是能预先构造的根据）
- **载体替换已实测**：`python frida_pack_sticker_swap.py --live`，
  只改 slot0（同专辑两枚 md5 都 32 字符、cap 0x2f ⇒ 零重分配）
- **免点击已实现**（TASK_LOG §30）：新增命令 **`type=12`**，
  DLL 按表情包型布局构造内容对象（`+0x08=5`、slot0/slot1/slot10），
  发送链路与收藏表情完全共用。已实测对端收到目标表情

### ⚠️ 手工构造路线（装上真实上下文后已可用）

历史上"已排除的 8 种组合"（全部实测，详见 TASK_LOG §25）：

| 方式 | 结果 |
|---|---|
| 手工信封 + `0xDB40` + pack（文本组委托） | 静默不送达 |
| 同上，换信封组委托（空捕获） | **崩溃** |
| + 补齐第 6 参数 + 实测委托顺序 | 「发送失败」 |
| + 回填 d2/d3 的 `[A,B,A]` 真实捕获 | 「发送失败」 |
| + d1 改外部存储（原生同构） | 「发送失败」 |
| 图片模型 + type=47 | 不送达 |
| 表情 XML + type=1 | **送达但显示 XML 原文** |
| 表情 XML + type=47（文本模型） | 不送达 |

**为什么当时全败**：失败不在"内容"，也不在"入队"，而在**承载内容的那套上下文**——
`0xDB40` 第 5 参数当时传的是全零假上下文（§27.2 定位到具体代码行）。
**装上捕获到的真实上下文后，这条路线（DLL `type=8`）已实测送达**（§27.6）。

**已确认与原生一致的部分**：信封（vt `0x82CB8D8`）、内容对象（12 个字符串槽 + 3 个整数字段修正）、
cfg（`[A,B,A]` 捕获逐字节相同、`d1` 外部存储同构）、pack 调用与返回、入队 `0x28F2F0`。

---

## 关键事实速查

### 发送链（frida 实测）

```
0x160DF80 emoji_ctor
  ├ 0xDB40   构造任务配置 cfg（收 6 参，第 5 参为发送任务上下文）
  └ 0x160EBE0 pack 投递（★载体替换的 hook 点）
      └ 0x290390 投递（开头 cmp [rcx+0x10],0 实测非零）
          └ 0x28F2F0 真正入队（文本/表情同路径）
```

原生 UI 侧调用链（自然发送时）：
```
0x83D5D0 → 0x262100 → 0x8E07B0 → 0x262100 → 0x1B13808
→ 0x1AFD280 → 0x160DCD0 → 0x160DF80
```

### 三类消息模型（body 坐标 = `_Ptr`）

| 偏移 | 文本 | 图片 | 信封（表情） |
|---|---|---|---|
| `+0x000` | `0x805E578` | `0x82CB658` | `0x82CB8D8` |
| `+0x0B0` | 接收方 wxid（buf） | 同 | 同（堆指针） |
| `+0x0C0 / C8` | len / cap | 同 | 同 |
| `+0x0D0` | 0 | **1** | 0 |
| `+0x0D8` | **1** | **3** | **0x2F** ← **消息类型码** |
| `+0x0E0` | 0 | **UTF-16 文件路径** | 0 |
| `+0xF0 / F8` | 0 / 7 | 105 / 111 | 0 / 7 |

**关键**：`block 坐标 +0xE8` = `body 坐标 +0xD8` = **内容类型码**。

### 表情内容对象（§26.3 实测）

```
信封 +0x660            内容对象（裸指针 → 对象体）
内容对象 +0x000        对象体 vtable = 0x8755528
内容对象 +0x010+k*0x20 第 k 个 std::string（buf@+0x00 / len@+0x10 / cap@+0x18）

slot0 lib_md5   32 / 47      slot6 url 20401 324 / 335
slot2 spec_md5  32 / 47      slot7 url 20403 322 / 335
slot8 aux_md5   32 / 47      slot9 url 20402 324 / 335
```

### 委托（`0xDB40` 的三/六参数）

| | 文本组 | 信封组 |
|---|---|---|
| d1 | `0x83661E8` | `0x83677E8` |
| d2 | `0x8366128` | `0x8367888` |
| d3 | `0x8366068` | `0x8367928` |

- `0xDB40` 收 **六** 个参数（rcx/rdx/r8/r9 + 两个栈槽），第 6 个原生为**递增计数**（非固定）。
- 每个委托先取 `[d+0x38]`：等于自身 → move-ctor；否则**直接把该指针写进 cfg**（外部存储）。
- 信封组 d2/d3 的捕获是**共享对象** `A=0x2d1fa91c6e0`（vt `0x8365848`）、`B=0x2d1fa8d8ea0`，
  顺序 `[A,B,A]`；`d1` 的 `+0x10` 是**栈地址**（不可复用），`+0x18` = `base+0xA3E5`（析构函数）。

### 注入式捕获（`bridge\control\delegate_caps.txt`）

```
A=<hex>          d2/d3 共享对象
B=<hex>          d2/d3 第二个捕获
D1_08=<hex>      d1 的 +0x08（堆指针）
D1_18=<rva hex>  d1 的 +0x18（析构函数 RVA）
```

**地址只在本次进程生命周期内有效，微信重启后必须重抓。**
（2026-10-14 12:47 已清空待重抓；载体替换路线**不需要**它。）

---

## 文件与工具

### 交付物

- `TASK_LOG_发送收藏表情.md` —— 完整技术档案（**26 节**，权威）
- `HANDOFF.md` —— 本文
- `wx-basic-bridge\dist\wx_hook_bridge.dll` —— 当前部署的 DLL

### 载体替换（§26 新增）

| 脚本 | 用途 |
|---|---|
| `frida_sticker_swap.py` | **载体替换**探针/执行器。`--live --target <idx>` 真替换，缺省 dry-run |
| `frida_ctx_reuse.py` | **捕获任务上下文**。`--dump-ctx --no-autosend` = 只捕获落盘（生产用）；`--schedule 5,60,300` = 时效测试 |
| `frida_scan_ctx.py` | 扫描定位尝试（**结论：不可行**，同 vtable 实例 14+ 个，无法区分） |
| `frida_peek.py <rva> [n]` | 比对**文件原始字节 vs 运行时字节**，判定某地址是否被 hook |
| `fetch_sticker_images.py` | 从 CDN 拉 7 个模板原图到 `tmp\stk\`（CDN 明文 PNG，本地 `Persist` 是加密态） |
| `bridge\control\ctx_override.txt` | **生产链路上的关键文件**：DLL 读它取真实任务上下文（`BODY=`/`CTRL=`，无 0x 前缀） |
| `reports\frida_swap_<pid>.txt` | 载体替换每次运行的 before/after 全量记录 |
| `reports\frida_ctx_<pid>.txt` | 捕获实验记录（含 TICK 心跳、CAPTURE、INJECT、PROBE） |

模板 ↔ 实物对照（`tmp\stk\`）：

| idx | md5 前缀 | 内容 |
|---|---|---|
| 0 | `0fbdd73c` | 正面微笑 |
| 1 | `53dcede7` | 嘟嘴 |
| 2 | `7ed20638` | 惊讶张嘴 |
| 3 | `b90ff3bb` | 双手托腮 |
| 4 | `cbab1418` | 单手托下巴 |
| 5 | `ccfabb49` | 挥手打招呼 |
| 6 | `d727ccdf` | 委屈 |

### 静态分析（Python + pefile + capstone）

| 脚本 | 用途 |
|---|---|
| `wxdis.py <rva> [count]` / `entry <rva>` | 反汇编指定 RVA |
| `dump_vtable.py <rva>` | dump vtable 槽位 |
| `find_rip_refs.py <rva...>` | 找 RIP 相对引用 |
| `find_vtable_loaders.py` | 找 vtable 写入点（消息模型构造器映射） |
| `find_str.py <pattern...>` | 搜 DLL 内字符串 |
| `compare_three_models.py` / `compare_pack_models.py` / `compare_content.py` / `compare_cfg.py` | 逐字段对照 |

### 动态分析（frida）

| 脚本 | 用途 |
|---|---|
| `frida_cfg_dump.py [sec]` | pack 元素 + cfg 内三个委托块 + `0xDB40` 六参数 + 内容对象 12 槽 |
| `frida_sticker_swap.py` | **载体替换**（§26） |
| `frida_after_pack.py [sec]` | post-pack 链路探针（**每次只挂互不相同的函数**） |
| `frida_probe_hits.py [sec]` | 发送相关函数命中统计（文件式输出，不依赖 send 通道） |
| `frida_deep_stack.py [sec]` | 深栈（从 emoji_ctor 回溯到 UI 层） |
| `frida_read_addrs.py <hexaddr...>` | 直读指定地址（含内容对象字符串槽解析） |
| `frida_hook_ctors.py` | 22 个消息模型构造器批量 hook |

### XML / 表情工具

- `send_sticker_xml.py <target> <type_code>` —— 重放真实表情 XML
- `send_sticker_own.py <target> [idx]` —— 用本账号模板构造 XML
- `reports\sticker_xml_sample.xml` —— 真实收藏表情 XML（`type=47`）
- `reports\sticker_templates.json` → `include\wx_sticker_templates.h` —— 7 个表情的 md5 + 3 个 CDN URL

---

## 缺陷修复记录（2026-10-18 → 19）

> 来源：外部审查报告 R01–R14 + 现场事故。每条都带实测证据，不是推测。

### R15 上游安全标签泄漏进正文（当晚最严重）

**现象**：23:54:59 那条回复的全文是

```
<ds_safety>[用户未成年]否 [分类]其他 [判定]用户最后一句是询问聊天对象是否需要文件，
属于日常对话，不涉及政治敏感内容。 [规则]无</ds_safety>Safe
```

它被当成回复正文入库、发到微信、再被下一轮历史喂回模型（会自我强化）。

**根因**：`api.deepseek.com` 官方端点在特定输入（如孤立的「你还要不」）下，
把**内容审核判定过程的元数据**拼进了 `choices[0].message.content`。
不是我们的 prompt 造成的，属于上游行为。

**修法**（三层防御，`feizhi_pc\llm.py` + `autoreply.py`）：

1. `llm.strip_meta_tags()`：剥 `<ds_*>` 标签、未闭合标签、以及闭合后紧跟的判定词
   （`</ds_safety>Safe` 会一起吃掉，否则留下一个孤零零的 `Safe` 贴在正文前）。
   只在文本真含 `ds_`/`Safe` 时才动手，正常文本零成本原样返回。
2. `llm.chat()` 返回前调用它 —— 所有调用方（回复/记忆/生活/朋友圈/主动搭话）同时受益。
3. `FeizhiReplyGenerator._sanitize_output()` 再逐条剥一次；
   `_call_api()` 里若 `_reply_text_len(raw) == 0`（正文被元数据占满），**重试一次 LLM**，
   而不是把兜底的「…我刚走神了一下」发出去。

**验证**：`feizhi_pc\_test_dssafety.py` 14 个用例全 PASS（含"正文夹标签"、未闭合、
只 Safe、正常含 Safe 词）；`_test_live_ds.py` 真实调 LLM 一次，返回正文干净。
库内污染已清（删掉 messages id=334 与 outbound id=1）。

### R16 拟人延迟失控（160 秒才发出一条）

**现象**：23:54:59 生成 → **23:57:39** 才送达，中间 next.txt 一直是空的，
看起来像"发送队列卡死"，实际是 sleep 在拟人延迟里。

**根因**：`humanize.reaction_delay_ms` 上限 180 秒，且按字数放大
（`× (1 + len/400)`）。R15 把 12 字的正文撑成 105 字 → reaction 120 秒 + typing 20 秒。

**修法**（`humanize.py`）：reaction 上限 180s → **25s**，最慢档采样区间 30~90s → 25~50s，
字数放大 `/400` → `/2000`；typing 上限 20s → **9s**。
一条回复的最坏开销从 ~200 秒压到 **34 秒**，日常仍保留 2.5~25 秒的真实感抖动。

**验证**：105 字文本跑 50 次采样，reaction max=25000ms、typing max=9000ms。

### R09 连发里的语音从未被转写

**现象**：`_handle_batch` 里"只入库不回复"的前置消息走的是
`store.add(..., m.content, ...)`，而语音消息的 `content` 是 XML 原文
（`<msg><voicemsg voicelength="3000" …/></msg>`）—— 上下文里塞满尖括号，
模型看不到"他说了什么"，这条语音等于白录。

**修法**：跟触发点走同一条 `_transcribe_voice()` 路径；
新增 `BATCH_VOICE_LIMIT = 2` 预算（每条转写 5~10 秒，免得 5 条语音把主循环拖住），
超预算的记占位文本而非 XML。

### 打断改口（他在这期间又说了话）

**现象**：回复已入队但还卡在几十秒的拟人延迟里，此时对方又发新消息 ——
旧回复照样发出去，读起来像"她没在听"。

**修法**：`_has_newer_for(peer)` 检查发送队列里是否还排着同一联系人的更新回复，
有就整条丢弃（判断在真正发送**之前**，不会出现"发了半句就不发了"），
出站任务标 `superseded`，`recover_outbound` 不会把它重新捞出来重发。

**验证**：`feizhi_pc\_test_interrupt.py` 6 项全 PASS。

### 运维注意

- 清空 `bridge\outbox\next.txt` **不能用** `Set-Content -Value "" -Encoding UTF8`
  （PS 5.1 会写入 3 字节 BOM，桥接会读到 `\ufeff` 前缀）。
  必须用 `[System.IO.File]::WriteAllBytes($path, (New-Object byte[] 0))`。

---

## 事故：微信被 DLL 带崩（2026-10-19 00:12）

**这是本项目至今最严重的一次故障** —— 不是发不出消息，是把整个微信进程弄死了。

### 经过

- `00:11:19` 收到「你可以向我介绍一下自己吗」，她回 3 条文字，LLM 同时决定配一个表情「托腮」
- `00:12:10` 往 outbox 写入 `seq \t 8 \t wxid \t 4`（type=8 收藏表情，模板 4）
- `00:12:11` Windows Application Error 1000：
  `Faulting application name: Weixin.exe, version: 4.1.9.23`
  `Faulting module name: wx_hook_bridge.1792333597649.dll`
  `Exception code: 0xc0000005（访问违例）  Fault offset: 0x1b85`
- 微信进程消失，Python 服务还在，从 `00:15` 起日志全是 `hook_alive=False`
- 用户看到的表象就是「服务死了」

### 根因

`bridge\control\ctx_override.txt` 的 mtime 停在 `2026-10-18 19:35`（5 小时前）。
表情发送走的是「载体替换 + 复用真实任务上下文」链路，DLL 会拿这个上下文当任务句柄用。
文件结构校验能过（长度/字段都对），但里面**指向的堆对象早被微信回收了**，
解引用就是空指针 —— 0xc0000005。

`bridge.py` 里原来的注释写着「上下文失效时只表现为发送失败，不会崩」，**这句话是错的**，
已按实测改正。

### 处置步骤（下次照这个来）

1. 先清 `bridge\outbox\next.txt`（用 `[System.IO.File]::WriteAllBytes`，
   **不要**用 `Set-Content -Encoding UTF8`，PS 5.1 会写 BOM）——
   否则微信重启后新注入的 DLL 会立刻重放那条命令，再崩一次
2. 启动 `C:\Program Files\Tencent\Weixin\Weixin.exe`
3. 如果弹出「升级出现问题」对话框：它是 `WeixinUpdate.exe`，会挡住微信登录窗口。
   WM_CLOSE / ESC / SetWindowPos 都无效（Qt 自绘 + 更高权限），
   用 `Invoke-CimMethod -MethodName Terminate` 结束它
4. 微信会停在登录确认页（头像 + 「进入微信」绿按钮），点一下即可进入
   （`tmp/click_green.ps1` 就是扫绿色像素定位按钮的脚本）
5. **worker 不会自动跟着窗口重建**：`reinject.py` 看到「hook already loaded」就直接返回，
   而那时 worker 已经退了。用 `<PROJECT_ROOT>\restart_worker.py <hwnd>` ——
   它绕过那个检查，直接 `GetProcAddress(WxBridgeWorker)` + `CreateRemoteThread`，
   在已加载的 DLL 里起一个新 worker（DLL 还在进程里，LoadLibrary 不能重复调用）
6. 重启 Python 服务

### 已加的两道防护

- **`bridge.CTX_MAX_AGE_SEC = 300`**：`send_sticker()` 发送前检查 `ctx_override.txt`
  的 mtime，超过 5 分钟直接返回 False 并记日志，不往 outbox 写。
  宁可少发一个表情，不能再崩微信。
- **`bridge.worker_healthy()`**：`hook_alive()` 只看「DLL 模块在不在进程里」，
  worker 退了它照样报 True（这次就是这样，`channel.txt` 是 `phase=worker_exiting`
  而 `hook_alive` 仍然 True）。新判据看 `channel.txt` 是否 `phase=running` +
  `hooked=1` 且 30 秒内刷新过（worker 每 2 秒写一次）。idle 日志现在两个都打。

### 还没根治的

DLL 侧（`send_sticker_tpl.c`）自己没有时间戳校验，它只能分辨「缺失/校验失败」。
要彻底解决得在 C 里读 `ctx_override.txt` 的 FILETIME 比对当前时间，超时就退回空上下文。
改它要重编译 + 重注入（会再杀一次微信），所以先用 Python 侧的闸门挡着。

### 后续同一个坑：worker 反复退出、收不到消息

恢复微信时踩到的第二个坑（`00:55` 那次）：

**注入/重启 worker 必须在微信已经进入主界面之后做**。如果在登录确认页
（窗口 294x387）就注入，worker 会把自己的 msg hook 绑在那个登录窗口上
（`channel.txt` 的 hwnd 是登录窗口句柄），用户点「进入微信」后登录窗口销毁，
worker 就写 `phase=worker_exiting` / `status=worker stopped` 退出了 ——
表现就是**消息发得出去、但一条也收不到**。

判定与操作顺序：

1. `enum_win.ps1` 看窗口尺寸：294x387 = 登录页；885x640 = 主界面
2. 登录页就先点「进入微信」（`tmp/click_green.ps1` 扫绿色像素定位按钮），
   等窗口变成主界面尺寸
3. 再 `python restart_worker.py <主窗口hwnd>`
4. 监控 20 秒：`status=worker started` + `phase=running hooked=1` 且
   `worker_owner.txt` 有 `pid:instance` 才算是真的活着

**验证收消息不能发出站消息**：`send_text` 到 filehelper 只能证明发送链路通，
出站消息走的不是 recv hook 那条路径（`recv_debug.txt` 不会新增）。
唯一可靠的验证是**真实入站消息** —— 让人在微信里发一句话，看
`bridge\inbox\*.json` 有没有新文件、`recv_debug.txt` 有没有新行。

---

## 产品缺口补齐（2026-10-19）

用户提的 10 项"不够像人"里，`life.py` 解决连续性之后，这一轮补了五项。

### 回访：她记得自己问过什么（`life.py: open_loops`）

她问出口、他还没说结果的事会登记成待回访；过几小时聊天或主动找他时，
优先挑一件问结果（"你那个PPT到底交了没"）。这是"她真的记得你说过什么"
最直接的体现，比随机挑一件今天的小事更像人。

- 登记：`add_loop(text)` 从**真正发出去的**回复里提取问句
  （必须带问号或以「吗/呢/么」收尾、含「你」、4~40 字；祈使句不算）
- 时机：`due_loops()` 要求间隔 ≥2 小时、≤72 小时、同一件事最多问 2 次
- 他回话后 `note_answered()` 把状态转成 answered —— **答过了正是最能问"结果如何"的时候**
- 三路共用：`life.render()` 里带一段，主动搭话那边单独当明确指令用
  （`render(include_loops=False)` 避免重复注入）

### 记忆的把握程度（`memory.py: certainty`）

事实分 high / mid / low 三档。抽取时让模型标，渲染时 medium 后面加
「（记得是这样，可能记岔）」、low 加「（好像是这样，不太确定）」，
并在提示里明确"说的时候要带『好像』『我记得是』，允许他纠正你"。

真人记忆不是数据库；以前她连"语音没听清"的东西都敢当铁的事实说。

兼容：老数据是纯字符串也照读；元素是 `{"text","certainty"}` 对象时
**绝不能** `str(dict)`（那会把整串字典当事实存进去）。

### 允许安静结束（`autoreply.py: _should_end_quietly`）

真人不会每句都接。条件故意收得很窄，避免把"她不回我"变成 bug 报告：

1. 他发的只是纯应答词（嗯/哦/好/哈哈…），且没有问号（「好？」是在等回答，必须接）
2. 距她上一条 ≤3 分钟（是同一次对话的收尾，不是把人晾着）
3. 25% 概率闸门

语音、带媒体、长句、从没回过的情况一律照常回。
嫌她太冷淡设 `FEIZHI_QUIET_END=0` 关掉。

### 共同表达 + 情绪余温（`persona.py`）

- 「我们」：说到一起的事自然用"我们那盆绿萝""我们说好要去的店"，
  但不把他当全部 —— 她自己的事照样自己拿主意。
- 情绪有惯性：上一轮还在不高兴，这一轮不会立刻满血复活；被哄好也是
  先「……哼」再软下来。`life.py` 把 `mood.since` 换算成
  「这股劲压了一两天了 / 从几小时前就这样 / 情绪还热着」写进提示，
  模型有依据才不会一秒切换。

### R04 语音发送的降级保护（`autoreply.py: _peer_looks_active`）

语音是「按住键、对当前打开的会话录音」，不像文本能带 `to_wxid` ——
前台窗口不是他就发错人。桥没有"查当前会话"的接口（要改 DLL），
所以用时间窗近似：最近 5 分钟内他确实说过话才发语音，否则降级为文字。
宁可少发一条语音，不能发错人。

---

## 下一步（按优先级）

1. **让飞知用上表情能力**（最实际的一步）
   在 `autoreply.py` 里加一个约定标记（类似现有的 `[img:名字]`，如 `[sticker:名字]`），
   命中就映射到 `type=12` 的模板序号。**「什么时候该发表情、发哪一枚」属于上层决策**，
   由 LLM 判断即可——DLL 只负责把指定表情发出去。
2. **扩充模板集**
   - 收藏表情：当前内置 7 个（`wx_sticker_templates.h`）
   - 表情包表情：当前内置 4 枚（`g_wxb_pack_tpls`），**名字（slot10）需逐枚采集**
     —— 实测「空降」「香」各不相同
   - 新表情发一次即可采到（`frida_ctx_reuse.py --dump-ctx` 会 dump 全部 12 槽 + body_hex）
3. **验证跨专辑**：目前只在同一个专辑内验证过（`slot1` 相同）。跨专辑时是否
   只需替换 `slot1`、还是要连带别的字段，尚未实测。
4. **（可选，彻底方案）上溯更少参数的入口**
   找"参数最少、可由当前会话 + 表情标识驱动"的那一层（链路见上）。
   若找到，连「上下文」这一环都不再需要。

---

## 已验证可复用的技术要点

- **MSVC 字符串布局**：`std::string` 32 字节，buf@+0 / len@+0x10 / cap@+0x18；
  `cap <= 0xF` 表示 SSO；容量不含结尾 NUL，分配要 `cap + 1`。
  就地覆写时须同时写 `buf[len] = 0` 并更新 len。
- **shared_ptr 控制块**（`_Ref_count_obj2`）：`[0]`=vtbl, `[8]`=_Uses, `[0xc]`=_Weaks，body 在 `+0x10`。
- **`std::function` 自指针协议**：`[this+0x38] == this` 表示内联存储，否则 `+0x38` 指向数据对象。
- **x64 调用约定**：第 5 参数在调用者 `[rsp+0x20]`、第 6 个在 `[rsp+0x28]`；
  被调函数入口处对应 `[R+0x28]` / `[R+0x30]`。
- **消息模型 vtable 族**：`0x805Exxx`（文本/图片等普通消息）与 `0x82CBxxx`（信封）
  是**两个族，委托不可混用**。
- **hook 分配点比 hook 使用点更可靠**；**绝不手工做 RVA 换算**，必须程序化并用已知值反推基址自检。
- **"阶段 N 通过"不等于"该阶段成功"**：`memory.c` 的 `w64`/`w32`/`copy_bytes`
  用 `__try/__except` 吞异常，写入失败也会静默通过。
