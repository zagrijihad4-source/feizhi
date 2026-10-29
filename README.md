# 绯栀（Feizhi）

一个跑在**真实微信 PC 客户端**里的 AI 伴侣，不是外挂窗口、不是模拟器、不是网页套壳。

她在你自己的微信账号里，用你的账号给指定联系人发文字、图片、表情、语音，唱整首歌，发朋友圈，也自己决定什么时候主动找你说话。

实现方式是往 `Weixin.exe` 里注入一个 C 写的 bridge DLL，Python 侧通过文件桥收发消息。所有消息都走微信自己的发送链路，服务端看到的是一个正常客户端。

---

## 能力

| 能力 | 状态 | 实现位置 |
| --- | --- | --- |
| 接收任意会话的消息 | 可用 | `wx-basic-bridge` → `outbox` |
| 发送文字 | 可用 | `send_text.c` |
| 发送图片 | 可用 | `send_image.c` + `img_dat.py`（图片格式解密） |
| 发送收藏表情 | 可用 | `send_sticker.c` + `stickers.py` |
| 发送语音（真人音色 TTS） | 可用 | `voice.py` + `tts.py`，hook SILK 编码器 |
| 唱歌（整首） | 可用 | `sing.py` + RVC 管线（`sing/`） |
| 发朋友圈 | 可用（纯文字） | `moments.py` + `moment_scheduler.py` |
| 看图 | 可用 | `vision.py` |
| 生图 | 可用 | `imagegen.py` |
| 长期记忆 | 可用 | `memory.py` / `memrec.py` / `gate/` |
| 主动消息 | 可用 | `proactive.py` |
| 自己的生活线（自驱日程与情绪） | 可用 | `life.py` |
| 多联系人并发 | 可用（5 线程池） | `peer_state.py` + `autoreply.py` |

---

## 架构

```
                    ┌──────────────────────────────────┐
                    │  Weixin.exe  (Qt + CEF 渲染)      │
                    │                                  │
   注入 ────────────▶│  wx_hook_bridge.dll              │
                    │   · 收消息 hook                   │
                    │   · 发送各类型消息                 │
                    │   · 语音 SILK 编码器 hook          │
                    └──────────┬───────────────────────┘
                               │  文件桥（无网络、无 IPC）
                    ┌──────────▼───────────────────────┐
                    │  bridge/{inbox,outbox,control}   │
                    └──────────┬───────────────────────┘
                               │
                    ┌──────────▼───────────────────────┐
                    │  feizhi_pc  (Python 主控)         │
                    │   run.py → autoreply.py          │
                    │   ├─ persona  人设与关系档位       │
                    │   ├─ llm      DeepSeek / 备用      │
                    │   ├─ memory   三层记忆 + 门控      │
                    │   ├─ life     自驱日程与情绪       │
                    │   ├─ voice    TTS → PCM → SILK    │
                    │   └─ moments  朋友圈              │
                    └──────────────────────────────────┘
```

文件桥的协议极简，一行一条消息：

```
<seq>\t<type>\t<wxid>\t<content>
```

`type` 决定消息类型（text / image / sticker / voice）。这条设计的意义是把「和微信通信」和「思考怎么回」彻底解耦——bridge 挂了不影响 Python 侧，Python 侧崩了微信也不会死。

### 语音为什么要 hook SILK

微信发语音时，客户端自己把 PCM 编码成 SILK 再封包上传。要让 AI 用自己的声音说话，有两条路：

1. 自己实现 SILK 编码器再构造完整封包——协议细节随版本漂移，脆。
2. hook 客户端已有的编码器，把它当成纯函数调用，再由我们自己走正常的提交链路。

这里走的是第二条。`voice.py` 找到打包提交点之后，只做一件事：把消息模型里的接收者 wxid 改写成目标联系人。这样语音发到哪不再取决于当前打开的是哪个会话。

---

## 目录结构

```
feizhi_pc/           AI 主控（Python）
  run.py             入口：拉起所有后台线程
  autoreply.py       收到消息 → 决定怎么回 → 拆句 → 发出去
  persona.py         人设、关系档位、说话风格约束
  memory.py          三层长期记忆
  memrec.py          记忆记录的抽取、审核、淘汰
  gate/              记忆门控（分类 / 协调 / 账本 / 复核）
  life.py            自驱生活线：日程、情绪、项目
  voice.py           语音发送（含打包点重定向）
  tts.py             TTS 合成与变速拼接
  moments.py         朋友圈
  sing.py            唱歌链路
  llm.py             模型调用与故障转移
  *.example.json     配置模板（复制成 *.json 后填自己的值）

wx-basic-bridge/    注入层（C）
  native/            hook 与各类型发送实现
  python/            文件桥的 Python 客户端
  examples/          收发示例

wx_research/         微信客户端逆向过程中的脚本与工具
  frida_*.py         运行时探测、内存 dump、调用追踪
  parse_*.py         各类 dump 的解析
  find_*.py          特征定位
  TASK_LOG_*.md      各阶段的技术记录

sing/                歌声管线脚本（RVC / 分离 / 混音 / 投递）

panel/               本地调试面板
```

---

## 运行前提

- Windows，微信 PC 版 **4.1.9.23**（其他版本的偏移量不同，需重新定位）
- Python 3.13
- 已安装 frida（注入用）

启动：

```powershell
cd feizhi_pc
# 先按下一节填好配置
python run.py both
```

`both` 表示同时启动收消息与自动回复。

---

## 配置

仓库里的 `*.example.json` 是模板，**复制成同名去掉 `.example` 的文件**后填入自己的值：

```powershell
cd feizhi_pc
Copy-Item llm_config.example.json   llm_config.json
Copy-Item tts_config.example.json   tts_config.json
Copy-Item image_config.example.json image_config.json
```

| 占位符 | 含义 |
| --- | --- |
| `<YOUR_API_KEY>` | 各家 LLM / TTS / 生图服务的密钥 |
| `<BREEZE_API_KEY>` | Breeze TTS 的密钥 |
| `<PROJECT_ROOT>` | 项目在本机的绝对路径 |
| `<WXID_SELF>` | AI 自己所在的微信账号 |
| `<WXID_FRIEND_A>` / `<WXID_FRIEND_B>` | 对话对象 |
| `<OWNER>` | 人设故事里的「主人」，即使用者本人 |
| `<PEER_TEST>` | 诊断脚本里用的测试对象名 |

---

## 核心模块

| 模块 | 职责 |
| --- | --- |
| `autoreply.py` | 主循环。收消息 → 线程池分发 → 生成回复 → 按句拆分 → 逐条发送 |
| `persona.py` | 人设文本、关系档位（陌生 / 熟人 / 亲密）、反升级约束 |
| `memory.py` | 工作记忆（最近 24 条）、事实记忆、情节记忆 |
| `memrec.py` | 从对话里抽取记忆条目，走审核后入库 |
| `gate/` | 记忆门控：是否值得记、是否该覆盖、复核 |
| `life.py` | 绯栀自己的时间线——不依赖聊天内容推进 |
| `voice.py` | 语音发送全链路，包括跨会话重定向 |
| `tts.py` | 分句合成 + 按情绪调语速 + 拼接 |
| `outguard.py` | 输出守卫：拦截不该发的表述 |
| `peer_state.py` | 多联系人状态隔离（各自独立记忆与关系） |

---

## 技术要点

**注入点**：`Weixin.dll+0x160EBE0` 是打包提交函数，接收 `vector<shared_ptr<Model>>`。它只做复制与引用计数，不读会话状态——所以可以安全地在它之前改写 receiver。

**字符串增长**：wxid 是 19 字符，超过 SSO 内联缓冲上限（15）。要改 receiver 必须用微信自己的 `operator new`（`Weixin.dll+0x64A7D1C`）分配，否则跨堆 `delete[]` 会直接崩。

**语音必须走真实按键**：不要给微信的 Qt 窗口投递合成键盘消息——一次 `WM_KEYUP(VK_ESCAPE)` 就能让整个窗口白屏。语音的触发路径是 hook 编码器 + 真实 `keybd_event`。

**TTS 变速**：服务端会忽略文本里「说快点」这类指令，只有 `voice_settings.speed` 生效。所以是逐句合成再拼接，代价是 API 调用数变成三倍。

---

## 说明

仓库里**不含**任何聊天记录、联系人身份、声音样本、模型权重、密钥。所有标识符与凭据均已替换为占位符，见上一节。

代码按「它现在怎么工作的」原样归档，包括过程中留下的大量一次性实验脚本（`_` 开头的文件）——它们记录了每个能力是怎么一步步试出来的。
