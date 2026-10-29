# -*- coding: utf-8 -*-
"""探测哪些 LLM 端点真的能"看图"（OpenAI 兼容 image_url 内容块）。

判定标准不是 HTTP 200，而是返回内容与图实际内容相符 —— 所以脚本里附带
一张已知内容的测试图，人工核对输出即可。

用法:
    python vision_probe.py [图片路径]
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests

ENV_FILE = Path(r"D:\Hermes\.env")
DEFAULT_IMG = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4\cache\2026-10"
                   r"\HttpResource\4c706bab6f2f1ae22f1340ffdc333efb")


def load_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


CANDIDATES = [
    ("synapse-claude", "https://synapse-ai.uk/v1", "SYNAPSE_CLAUDE_API_KEY", "claude-sonnet-4-6"),
    ("synapse-grok", "https://synapse-ai.uk/v1", "SYNAPSE_GROK_API_KEY", "grok-4.5"),
    ("synapse-gpt4o", "https://synapse-ai.uk/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    ("synapse-gemini", "https://synapse-ai.uk/v1", "SYNAPSE_GEMINI_API_KEY", "gemini-2.5-flash"),
    ("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
     "anthropic/claude-3.5-sonnet"),
]

PROMPT = ("用一句中文说清这张图里有什么：人物、场景、主要物体。"
          "如果看不到图，只回复 NOT_AN_IMAGE。")


def main() -> int:
    img = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMG
    raw = img.read_bytes()
    b64 = base64.b64encode(raw).decode()
    print("测试图: %s (%.1f KB)" % (img.name, len(raw) / 1024), flush=True)
    env = load_env()

    for name, base, key_env, model in CANDIDATES:
        key = env.get(key_env, "")
        if not key:
            print("\n[%s] 跳过：%s 未配置" % (name, key_env), flush=True)
            continue
        payload = {
            "model": model,
            "max_tokens": 120,
            "temperature": 0,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": "data:image/jpeg;base64," + b64}},
                ],
            }],
        }
        try:
            r = requests.post(
                base.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"},
                json=payload, timeout=90)
        except Exception as exc:  # noqa: BLE001
            print("\n[%s] 异常 %s: %s" % (name, type(exc).__name__, exc), flush=True)
            continue
        if r.status_code != 200:
            print("\n[%s] HTTP %s: %s" % (name, r.status_code, r.text[:200]), flush=True)
            continue
        try:
            txt = r.json()["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001
            print("\n[%s] 响应结构异常: %s" % (name, r.text[:200]), flush=True)
            continue
        if isinstance(txt, list):
            txt = " ".join(seg.get("text", "") for seg in txt if isinstance(seg, dict))
        print("\n[%s / %s] OK -> %s" % (name, model, (txt or "").strip()[:300]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
