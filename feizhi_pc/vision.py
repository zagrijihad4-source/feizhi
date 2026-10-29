# -*- coding: utf-8 -*-
"""图片识别 —— 让绯栀真的"看见"他发来的图。

后端（2026-10-25 实测）：

  1. **deepseek-flash**（主）—— 同一个 key 通吃，2.2 秒，图片按 1024 token 计费
     （detail=low 缩到 512×512），约 0.0005 元/张。实测描述准确到能认出
     "黄色瓷砖墙面"这种细节。文档：api-docs.deepseek.com/zh-cn/guides/vision
  2. **claude-sonnet-4-6**（兜底）—— deepseek 不可用时顶上。
     实测 synapse-grok 401、gpt-4o 503、gemini 403、openrouter 401，只有这两家能用。

  注意：图片**只能出现在 user 消息里**（system/assistant 带图会 400）。

设计取舍：
  * **给"她"看的描述，不是给工程师看的**：输出"图里有什么 + 什么气氛"，
    她据此自然接话，不是复述一段机器分析。
  * **带文字就读出来**：聊天里大量图片是截图（订单、聊天记录、成绩单），
    读不出字等于没看见。
  * **失败绝不阻塞回复**：任何异常都返回空串，上层退回"没图也照常聊"。
  * **按内容 md5 缓存**：同一张图重复识别没有意义，也省钱。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from pathlib import Path

import requests

LOG = logging.getLogger("feizhi_pc.vision")

ENV_FILE = Path(r"D:\Hermes\.env")
CONFIG_FILE = Path(r"<PROJECT_ROOT>\feizhi_pc\llm_config.json")
CACHE_FILE = Path(r"<PROJECT_ROOT>\feizhi_pc\state\vision_cache.json")
CACHE_MAX = 300

TIMEOUT = 90
MAX_BYTES = 4 * 1024 * 1024

# 后端配置。
# ★ deepseek-flash 是**推理模型**：默认会先思考再回答，实测 reasoning_tokens 830、
#   耗时 5.9 秒。而 max_tokens 是「思考 + 正文」的总预算，给 400 时 400 全花在
#   思考上、正文返回空串（finish_reason=length）—— 看起来就像"模型看不见图"。
#   解法是 `thinking: {"type": "disabled"}`：关掉思考后 1.7 秒出结果，质量不降。
#   （`reasoning_effort` 无效；`thinking.type` 只认 disabled/auto。）
BACKENDS = (
    {"name": "deepseek-flash", "base": "https://api.deepseek.com/v1",
     "key_env": "DEEPSEEK_API_KEY", "model": "deepseek-flash",
     "detail": True, "max_tokens": 800,
     "extra": {"thinking": {"type": "disabled"}}},
    {"name": "claude", "base": "https://synapse-ai.uk/v1",
     "key_env": "SYNAPSE_CLAUDE_API_KEY", "model": "claude-sonnet-4-6",
     "detail": False, "max_tokens": 500, "extra": {}},
)

PROMPT = (
    "这是他在微信里发给女朋友的一张图。请用中文客观描述，供她自然接话使用：\n"
    "1) 先一句话说清整体是什么（自拍/风景/物品/截图/表情包/文档…）；\n"
    "2) 再说关键细节：人的样子与情绪、场景、物品、构图氛围；\n"
    "3) 图里有文字就**逐字读出来**（订单号、金额、聊天内容、标题都要）；\n"
    "4) 如果是表情包或梗图，说明它在表达什么情绪。\n"
    "总长控制在 120 字以内，不要用「这张图片」开头，直接说内容。"
    "如果确实无法识别，只回复 UNKNOWN。"
)

_env_cache: dict | None = None
_cache_lock = threading.Lock()


def _load_env() -> dict:
    global _env_cache
    if _env_cache is not None:
        return _env_cache
    env: dict = {}
    try:
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if v.strip():
                env[k.strip()] = v.strip()
    except OSError as exc:
        LOG.warning("读取 .env 失败: %s", exc)
    # llm_config.json 里可能有内联 key（她的实际配置），优先级更高
    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        inline = ((cfg.get("providers") or {}).get("deepseek") or {}).get("api_key")
        if inline:
            env["DEEPSEEK_API_KEY"] = inline
    except Exception:  # noqa: BLE001
        pass
    _env_cache = env
    return env


def _mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"GIF8":
        return "image/gif"
    return "image/jpeg"


# ---------------------------------------------------------------- 缓存
def _cache_get(key: str) -> str | None:
    with _cache_lock:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    v = data.get(key)
    return v if isinstance(v, str) else None


def _cache_put(key: str, desc: str) -> None:
    with _cache_lock:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            data = {}
        data[key] = desc
        if len(data) > CACHE_MAX:
            for k in list(data)[:len(data) - CACHE_MAX]:
                data.pop(k, None)
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False),
                                  encoding="utf-8")
        except OSError as exc:
            LOG.debug("写视觉缓存失败: %s", exc)


# ---------------------------------------------------------------- 主入口
def describe_bytes(data: bytes, hint: str = "") -> str:
    """识别一张图，返回中文描述；失败返回空串。"""
    if not data:
        return ""
    if len(data) > MAX_BYTES:
        LOG.info("图片过大（%.1f MB），跳过识别", len(data) / 1048576)
        return ""

    key = hashlib.md5(data).hexdigest()
    hit = _cache_get(key)
    if hit is not None:
        LOG.info("视觉缓存命中 %s", key[:8])
        return hit

    env = _load_env()
    prompt = PROMPT if not hint else (PROMPT + "\n（他同时说了：" + hint[:60] + "）")
    data_url = "data:%s;base64,%s" % (_mime(data), base64.b64encode(data).decode())

    for b in BACKENDS:
        name = b["name"]
        key_val = env.get(b["key_env"], "")
        if not key_val:
            LOG.debug("%s: %s 未配置，跳过", name, b["key_env"])
            continue
        img_block = {"url": data_url}
        if b["detail"]:
            img_block["detail"] = "low"   # 缩到 512×512，够认人认字，省 token
        payload = {
            "model": b["model"],
            "max_tokens": b["max_tokens"],
            "temperature": 0.2,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": img_block},
                ],
            }],
        }
        payload.update(b["extra"])
        try:
            r = requests.post(
                b["base"].rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + key_val,
                         "Content-Type": "application/json"},
                json=payload, timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("%s 识别请求失败: %s %s", name, type(exc).__name__, exc)
            continue

        if r.status_code != 200:
            LOG.warning("%s 识别 HTTP %s: %s", name, r.status_code, r.text[:140])
            continue
        try:
            txt = r.json()["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            LOG.warning("%s 响应结构异常: %s", name, r.text[:140])
            continue
        if isinstance(txt, list):
            txt = " ".join(seg.get("text", "") for seg in txt if isinstance(seg, dict))
        desc = " ".join((txt or "").split())
        if not desc or desc.upper().startswith("UNKNOWN"):
            LOG.info("%s 无法识别这张图", name)
            continue
        _cache_put(key, desc)
        LOG.info("图片识别完成（%s）%s -> %s", name, key[:8], desc[:60])
        return desc

    LOG.warning("所有视觉后端都失败了")
    return ""


def describe_file(path: str | Path, hint: str = "") -> str:
    p = Path(path)
    try:
        return describe_bytes(p.read_bytes(), hint)
    except OSError as exc:
        LOG.warning("读图失败 %s: %s", p, exc)
        return ""


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    target = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\cache\2026-10"
             r"\HttpResource\4c706bab6f2f1ae22f1340ffdc333efb"))
    print("图:", target)
    print("描述:", describe_file(target) or "(无)")
