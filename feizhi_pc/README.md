# feizhi_pc — 绯栀自动回复 / 主动消息（PC hook 桥版）

把 `Feizhi` 的上层逻辑（绯栀人格、LLM 生成、拟人时序）接到 **PC 端 hook 注入桥**上，
取代原来的 ADB 操作手机微信方案。

## 为什么这么做

原方案 `D:\Hermes work\feizhi-wechat-phone-bridge` 靠 ADB 点击手机微信：
末次成功是 2026-07-30，之后所有失败都是 `AdbError`（手机链路断、`adb devices` 为空）。
而 PC 端 hook 桥已经打通收发，因此只需替换底层，上层完全沿用。

## 结构

```
<PROJECT_ROOT>\feizhi_pc\
├─ bridge.py      与 hook 桥交互：读 bridge/inbox、写 bridge/outbox
├─ store.py       SQLite 对话上下文（inbound / auto_reply / proactive）
├─ autoreply.py   自动回复：过滤 -> LLM 生成 -> 分段发送
├─ proactive.py   主动消息：时段/空闲/日限额控制 -> LLM 生成 -> 发送
├─ run.py         统一入口
└─ state/         去重记录与上下文库
```

复用关系：
- **`reply_generator.py` 直接导入复用**（只依赖 LLM API，与底层无关），
  路径 `D:\Hermes work\feizhi-wechat-phone-bridge\src`，提供绯栀人格、分段 plan、think/typing/delay 时序
- **`proactive_sender.py` 重写**（原实现全是 ADB 坐标点击，无法复用）

## 用法

```powershell
cd <PROJECT_ROOT>\feizhi_pc

python run.py test              # 自检：hook 状态 / 待处理入站 / LLM / 上下文库
python run.py once              # 单次处理当前待回复消息（验证用）
python run.py autoreply         # 常驻：自动回复
python run.py proactive         # 常驻：主动消息
python run.py both              # 常驻：两者一起（主动消息在后台线程）
python run.py proactive-once    # 单次主动消息（忽略空闲限制，验证用）
python run.py show              # 查看最近对话上下文
```

日志：`<PROJECT_ROOT>\feizhi_pc\logs\feizhi_pc.log`

## 真人感与表情

### 问题

原版接进来之后，实测输出明显偏「完整、正确、有礼貌」——像客服，不像真人：

```
用户: 在吗
  绯栀: 在呀，刚上完早课回宿舍，你咋啦？          ← 完整句 + 礼貌
用户: 随便说点什么
  绯栀: 刚在课上偷偷摸鱼，老师讲品牌字体我快听睡着了。
  绯栀: 你呢，今天干嘛呢？突然让我随便说，是不是也无聊了。   ← 有总结感
```

而且**完全不发表情**。

### 解决办法

**表情不需要改 hook**。微信的 `[微笑]` 这类表情代码**直接写在文本里就会被渲染成图标**，
发送的仍然是普通 type=1 文本消息。`stickers.py` 收录了完整的 108 个标准表情代码。

`persona.py` 追加两层约束（拼进 system prompt）：

1. **真人感**：允许不完整句/半截话；长短句混排；不总热情；
   禁书面语与总结腔（「总的来说」「不知道你有没有」「首先其次」）；
   不用敬语；自然用语气词；可以反问、可以只回一个「？」；有情绪波动；
   不复述对方、不给建议清单、不每句都提问。
2. **表情**：频率约三到四条用一次；可以整条只回一个表情；
   按情绪挑（开心→`[呲牙]`、无语→`[捂脸]`、撒娇→`[害羞]`、嫌弃→`[白眼]` …）。

**关键点**：约束的是「怎么说话」，不是「说什么」——不把人格写死成模板。

### 效果（同一组输入）

| 用户 | 增强后 | 关闭增强（`enhance_persona=False`） |
|---|---|---|
| 在吗 | `在呀` / `干嘛，你不是去上课了么` | `在呀，刚上完早课回宿舍，你咋啦？` |
| 今天好累啊 | `怎么啦，又熬夜了？` / `我早上画图眼睛都快瞎了[困]` | `怎么啦，是上课还是作业太折腾你了？` / `我现在在画室改一张海报…咱俩算难兄难弟。` |
| 随便说点什么 | `诶，你这开场也太敷衍了吧` / `困得要死[困]` / `你到底想聊啥呀` | `刚在课上偷偷摸鱼…` / `你呢，今天干嘛呢？` |
| 晚安 | `？` / `现在早上十点诶，你熬夜熬到语无伦次了？[白眼]` | — |

增强版会**只回一个「？」**、会吐槽、会发表情；对照版明显更完整客气。

### 成本影响：几乎为零

加长固定段后反而**大幅提高了缓存命中率**：

| 指标 | 增强前 | 增强后 |
|---|---|---|
| system prompt | 678 字符 | 1348 字符 |
| 缓存命中率 | 20.5% | **79.6%** |
| 单次平均 token | 453 | 886 |
| **单次成本** | ¥0.001258 | **¥0.001303** |

prompt 变长了 670 字符，但因为固定段（人格 + 风格约束）在前、且足够长，
把可缓存前缀推过了 DeepSeek 的缓存粒度阈值，命中率从 20% 升到 80%，
**单次成本只涨了 3.6%**。要关闭增强：`FeizhiReplyGenerator(llm=..., enhance_persona=False)`。

## LLM 接入（可插拔）

`llm.py` 是独立的 OpenAI 兼容客户端，支持任意端点 + 多提供方自动故障转移。
Feizhi 的绯栀人格 prompt、回复分句、think/typing 拟人时序全部保留，只替换了 API 调用层。

### 当前配置

`llm_config.json`：

```json
{
  "order": ["deepseek", "synapse-claude"],
  "timeout": 60,
  "max_attempts": 2,
  "providers": {
    "deepseek": {
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-…（你的密钥）",
      "model": "deepseek-chat"
    }
  }
}
```

密钥解析优先级：**配置内联 `api_key` > 环境变量 > `D:\Hermes\.env`**。
`providers` 里的字段会覆盖内置注册表同名字段，所以可以只写要改的那几项。

> 注意：`llm_config.json` 是**本地明文配置**，内含密钥，不要提交到公开仓库。

### 常用命令

```powershell
python run.py llm                              # 查看配置 + 逐个实测连通性
python run.py llm-set deepseek                 # 只用 deepseek
python run.py llm-set deepseek,synapse-claude  # 设主备顺序
```

改完配置需要**重启常驻进程**才会读取。

### 内置提供方

| 名称 | 模型 | 端点 |
|---|---|---|
| `deepseek` | deepseek-chat | api.deepseek.com/v1 |
| `synapse-claude` | claude-sonnet-4-6 | synapse-ai.uk/v1 |
| `synapse-grok` | grok-4.5 | synapse-ai.uk/v1 |
| `openrouter` | anthropic/claude-3.5-sonnet | openrouter.ai/api/v1 |
| `openai` | gpt-4o-mini | api.openai.com/v1 |

### 接自己的模型

本地 ollama、自建中转、任何 OpenAI 兼容服务，在 `providers` 里加一段即可：

```json
{
  "order": ["my-local", "deepseek"],
  "providers": {
    "my-local": {
      "base_url": "http://127.0.0.1:11434/v1",
      "api_key": "ollama",
      "model": "qwen2.5:14b"
    }
  }
}
```

也可以用 `probe_llm.py` 一次性探测 `.env` 里所有 key 的可用性。

### 实测记录（2026-10-13）

各端点连通性：

| 端点 | 结果 |
|---|---|
| deepseek | OK 0.7~1.0s |
| synapse-claude | OK 3.5s |
| synapse-grok | HTTP 401 Invalid token（原默认，已失效） |
| openrouter | HTTP 401 Missing Authentication |
| openai | HTTP 503 model_not_found |
| xai | 连接超时 |

生成样例（deepseek）：

```
用户: 今天好累啊
  绯栀: 怎么啦，画作业画到现在吗？
  绯栀: 还是又熬夜赶稿了，说给我听听。

用户: 帮我查一下杭州明天的天气
  绯栀: 杭州明天啊，我看看——不过我现在没法直接联网查实时天气，只能告诉你大概。
  绯栀: 十月中的杭州一般是白天二十出头、早晚偏凉，可能有小雨，出门带件薄外套和伞比较稳。
  绯栀: 你要出门干嘛呀？要具体到几点、去哪个区的话，我帮你想想怎么穿更靠谱。
```

主动消息样例：

```
proactive sent: '<OWNER>，刚在西湖边看到有人画速写，突然想到你上次说的那个展。'
```

## 设计约束（重要）

**发消息只走 hook 桥，不使用 computer use。**

具体含义：
- 发送 = 往 `bridge\outbox\next.txt` 写一条命令，由**微信进程内的 worker** 消费后真正发出
- **不**模拟鼠标点击、**不**模拟键盘输入、**不**做窗口控件/坐标操作
- 代码中不含 `mouse_event` / `SetCursorPos` / `SendKeys` / `PostMessage` /
  `uiautomation` / `pyautogui` / `SendInput` 之类的调用（可用下面命令自查）

```powershell
cd <PROJECT_ROOT>\feizhi_pc
Select-String -Path *.py -Pattern 'mouse_event|SetCursorPos|SendKeys|PostMessage|uiautomation|pyautogui|SendInput'
# 期望：无输出
```

**启动环节也不需要 UI 操作。** 实测微信重启后 20s 出现 `mmui::LoginWindow`、
**30s 自行切到 `mmui::MainWindow`**（登录态被记住），35s hook 注入完成——全程无需点击。
因此 `reinject_daemon.ps1` 里原本那段调用 `auto_login.ps1`（UIA + PostMessage 点"进入微信"）
的代码已**移除**。

## 自启

启动文件夹里两个 VBS 协同工作：

| 文件 | 作用 |
|---|---|
| `wxhook_reinject_daemon.vbs` | 拉起 hook 重注入守护（微信重启后自动注入） |
| `feizhi_pc_autoreply.vbs` | 拉起 `run.py both`（自动回复 + 主动消息） |

两者都用 `pythonw.exe` 无窗口运行。`run.py` 的常驻模式带单实例保护
（`state/run_<tag>.pid`），自启与手动启动不会撞车。

## 已实测（2026-10-13 08:25）

```
$ python run.py once
发现 2 条新消息
  peer=newsapp             -> 跳过 (system_peer(newsapp))     # 订阅号正确过滤
  peer=<WXID_FRIEND_A> -> 回复 (ok)                       # 用户消息正确识别
replied to <WXID_FRIEND_A> with 1 message(s)              # 发送成功
统计: {'seen': 1, 'replied': 1, 'skipped': 0, 'failed': 0}
```

`python run.py proactive-once` 同样成功：
`proactive sent: '来报个到。没什么事，就是确认一下这条线还连着。'`

上下文库：
```
记录统计: {'auto_reply': 1, 'inbound': 1, 'proactive': 1}
[inbound]    <OWNER>: 测试消息推送，验证是否能接收
[auto_reply] 绯栀: 收到啦~
[proactive]  绯栀: 来报个到。没什么事，就是确认一下这条线还连着。
```

界面上左侧聊天图标出现红「2」未读徽章 —— 消息确实发到了微信。

## 行为规则

**自动回复（`autoreply.py`）**

- 只回 `isIncoming=True` 的**文本**消息（`type=1`）
- 跳过系统会话：`newsapp`、`filehelper`、`floatbottle`、`medianote`、`weixin`、
  `notifymessage`、`weixinreminder`，以及 `gh_` 开头的公众号
- 群消息暂不回复（避免刷屏）
- **只回复白名单里的联系人**（默认 `<WXID_FRIEND_A>`，即你本人）
- 去重：同一条消息（peer+msgId+localId+timestamp）不会被回复两次
- 发送按 LLM 给的 plan 分段，带 think/typing/delay 停顿，模拟真人节奏

**主动消息（`proactive.py`）**

| 条件 | 默认值 | 说明 |
|---|---|---|
| `min_idle_minutes` | 180 | 距上次互动至少 3 小时才主动说话 |
| `quiet_hours` | (1, 8) | 凌晨 1 点到早 8 点不打扰 |
| `daily_limit` | 4 | 每天最多主动 4 条 |
| `check_interval` | 300 | 每 5 分钟检查一次 |
| `jitter_seconds` | 900 | 触发后随机延迟，避免整点规律 |

LLM 不可用时回落到内置模板（`FALLBACK_LINES`）。

## 需要注意的坑

### 坑 0：微信重启后方向判定失效（已修，双层防护）

**现象**：微信重启后发消息给绯栀，完全不回复。

**根因**：hook 注入在微信进程内，`self_wxid` 是**静态状态**，微信一重启就重置。
而 hook 里学习 `self_wxid` 的 fallback 分支要求"收发双方只有一个像 wxid"：

```c
if (is_wxid_like(from) && (!is_wxid_like(to) || str_eq(to, "filehelper"))) { ...学习 from... }
else if (is_wxid_like(to) && !is_wxid_like(from)) { ...学习 to... }
else { /* 双方都是 wxid 时走这里：不设方向、不学 self */ }
```

**而绯栀和<OWNER>都是 `wxid_` 形态账号**，两个分支都不命中 → `self_wxid` 永远学不回来
→ `direction=unknown` / `isIncoming=false` / `to=null`，消息被当成非入站丢弃。

实测对比（同一个 peer）：

| 微信 PID | 重启? | selfWxId | direction | isIncoming |
|---|---|---|---|---|
| 50480 | 否 | `<WXID_SELF>` | incoming | true |
| 48284 | 是 | *空* | unknown | **false** |

**双层修复**：

1. **hook 侧（治本）**：`receive.c` 的 `classify_message` 新增分支——双方都是 wxid 时，
   按"DoAddMsg 多为收到的消息，此时 `to` 是自己"把 `to` 学作 self 并判为入站。
   学习成功后，原有两条已知分支就会接管。
   改完需重新编译（`build_clang.ps1`）并重启微信让其重新注入。

2. **客户端侧（保险）**：`autoreply.resolve_direction()` 不再单纯依赖 hook 的 `isIncoming`。
   `isIncoming=true` 直接采信；否则退回用 `selfWxId`（消息里没有就用配置的 `SELF_WXID`）
   判断 sender/from 是否等于自己。即使 hook 状态丢失，也不会漏掉消息。

### 坑 1：`hook_alive()` 不能看 `heartbeat.txt`

那个文件是**注入器 python 进程**写的，注入器退出后就停更；
但 DLL worker 活在微信进程内，收发都正常。
正确判据是检查微信进程里有没有加载 `wx_hook_bridge*.dll`
（`bridge.py` 已按此实现）。`send_capable()` 是更直接的实测法。

### 坑 2：标记时机

`poll_new()` **只读不标记**，标记由 `mark_processed()` 在业务层确认处理成功后调用。
被跳过（系统会话/非白名单）的消息会标记；**LLM 失败或发送失败的不标记**，下一轮自动重试。
早期版本是"读到就标记"，导致生成失败的消息被永久吞掉，已修正。

### 坑 3：发送目标必须是 wxid

用昵称会静默失败——命令返回 `ok:true`，但微信会新建一个「微信用户」会话
并在界面显示「对方还不是你的朋友」+ 红色感叹号。

### 坑 4：`run.py test` 不会消耗消息

它只读排查待处理队列，不做标记；真正消费消息的是 `once` / `autoreply`。

## 上下文库

`state/context.sqlite3`，表 `messages`：

| 字段 | 说明 |
|---|---|
| peer_wxid | 对话对象 |
| role | `user`=<OWNER>发来 / `assistant`=绯栀发出 |
| text | 正文 |
| sent_at_ms | 毫秒时间戳 |
| source | `inbound` / `auto_reply` / `proactive` |
| dedupe_key | 唯一键，用于幂等 |

用 `python run.py show` 查看；`ContextStore.history(peer)` 返回给 LLM 的上下文
（`autoreply.py` 取 20 条）。
