# 绯栀 AI 清唱 · 施工方案（2026-10-19 19:32 停在调研完成）

用户要的效果：她能用**自己的音色** AI 清唱（无伴奏），像抖音上那种 AI 歌声。

## 已确认的事实（都已实测，不用再查）

| 项 | 结论 |
|---|---|
| 候选方案 | [SoulX-Singer](https://github.com/Soul-AILab/SoulX-Singer)（零样本歌声合成，Apache 2.0） |
| SVS 模式 | 给歌词 + MIDI/F0 + 参考音色 → 直接生成歌声 |
| SVC 模式 | 给一段清唱 + 参考音色 → 转成她的音色；**不需要歌词/转谱**，这条更适合聊天场景 |
| `model.pt`（SVS） | 2688 MB |
| `model-svc.pt`（SVC） | 2665 MB |
| `rmvpe/rmvpe.pt` | 173 MB（F0 提取，SVC 必需） |
| 模型下载源 | `https://hf-mirror.com/...` **可直连（200）**；`huggingface.co` 直连超时；`modelscope.cn` 也可达 |
| 本机 GPU | NVIDIA RTX 4060 Laptop，**显存仅 4GB** |
| 本机内存 | 23.8 GB |
| F 盘余量 | 90.8 GB |
| 现有 Python | 3.13.13（F:\AI课程软件、F:\py313）、3.14.6（D:\Anaconda3）—— **都太新**，需要 3.10 |
| 可用的建环境工具 | `D:\Hermes\bin\uv.exe`（0.11.26，能装任意 Python 版本，最快）、`D:\Anaconda3\Scripts\conda.exe` |

## 决定：用 uv 建隔离环境，装在 <PROJECT_ROOT>\sing\

**不要**污染 `F:\AI课程软件\Python313` 和 `F:\py313`（那是 feizhi_pc 在用的）。

## 施工步骤

1. `D:\Hermes\bin\uv.exe venv <PROJECT_ROOT>\sing\.venv --python 3.10`
2. 装 torch（cu121 或 cu124，国内源慢就换阿里云镜像）：
   `uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124`
   —— 这一步 2.5GB 左右，**下载时别打游戏**（抢带宽 + 影响 ping）
3. 拉代码（github 可达）：
   `git clone https://github.com/Soul-AILab/SoulX-Singer.git <PROJECT_ROOT>\sing\SoulX-Singer`
4. 设 `HF_ENDPOINT=https://hf-mirror.com` 再下模型：
   ```powershell
   $env:HF_ENDPOINT = "https://hf-mirror.com"
   hf download Soul-AILab/SoulX-Singer --local-dir <PROJECT_ROOT>\sing\pretrained_models\SoulX-Singer
   hf download Soul-AILab/SoulX-Singer-Preprocess --local-dir <PROJECT_ROOT>\sing\pretrained_models\SoulX-Singer-Preprocess
   ```
   只需要 `model-svc.pt` + `rmvpe/rmvpe.pt` 的话可以单独 `hf download <repo> <file>`，省 2.5GB
5. 先跑官方 `example/infer_svc.sh`（Windows 上要翻译成 .ps1 或直接看脚本里那条 python 命令），
   **prompt 音色用现成的** `<PROJECT_ROOT>\feizhi_pc\voice\feizhi_B_sample.wav`
6. 跑通后封装 `<PROJECT_ROOT>\feizhi_pc\sing.py`：
   - 输入：歌词 / 一句哼唱文本
   - 输出：16k 单声道 PCM（复用 `tts.to_wechat_pcm` 的转换逻辑）
   - 再交给 `voice.VoiceSender.say_pcm()` 发出去（**发送链路已验证可用，不用动**）
7. 人格侧：`persona.py` 的 VOICE_STYLE 里，唱歌场景从「念歌词」改成走 sing 通道

## 最大风险

**4GB 显存**。2.67GB 权重 fp16 加载约 1.34GB，理论上放得下，但推理中间激活 + RMVPE 可能顶爆。
如果 OOM，退路：
- `--dtype fp16` + 关掉不必要的 batch
- 只跑 SVC 不跑 SVS（SVC 只需要 F0 + 波形，激活更小）
- 实在不行用 CPU 推理（慢，但"唱两句"这种几秒的片段可能 30~60 秒能出，聊天场景勉强能接受）

## 现状

- 她**现在就能发语音**（MiMo TTS，念歌词 + 拖长音），这条链路已验证（TTS 合成 → frida → PostMessage 按键，不抢前台）
- 只是因为用户在全屏游戏，语音按键能不能落到微信窗口还没实测
- **用户说等下再试** —— 恢复施工时先问他游戏打完了没，再开始下载
