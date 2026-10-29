"""探测 <ENV_FILE> 里各 LLM 端点的可用性。

对每个 (env_key, base_url, model) 组合发一个最小请求，报告是否可用与延迟。
只读探测，不改任何配置。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

ENV_FILE = Path(r"D:\Hermes\.env")


def load_env() -> dict:
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def probe(name, base_url, api_key, model, timeout=45):
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        t0 = time.time()
        r = requests.post(
            url,
            headers={"Authorization": "Bearer " + api_key,
                     "Content-Type": "application/json"},
            json={"model": model,
                  "messages": [{"role": "user", "content": "只回复两个字：可用"}],
                  "max_tokens": 20, "temperature": 0},
            timeout=timeout,
        )
        dt = time.time() - t0
        if r.status_code == 200:
            try:
                txt = r.json()["choices"][0]["message"]["content"].strip()
            except Exception:
                txt = "(解析失败)"
            print(f"  [OK]   {name:<22} {dt:5.1f}s  model={model}  -> {txt[:30]!r}")
            return True
        else:
            print(f"  [FAIL] {name:<22} HTTP {r.status_code}  {r.text[:80]}")
            return False
    except Exception as e:
        print(f"  [FAIL] {name:<22} {type(e).__name__}: {str(e)[:70]}")
        return False


def main():
    env = load_env()
    print(f"读取 {ENV_FILE} : {len(env)} 个变量\n")

    # (显示名, base_url 的 env 名 或字面量, key 的 env 名, 模型)
    targets = [
        ("Synapse/grok",      "https://synapse-ai.uk/v1", "SYNAPSE_GROK_API_KEY",     "grok-4.5"),
        ("Synapse/claude",    "https://synapse-ai.uk/v1", "SYNAPSE_CLAUDE_API_KEY",   "claude-sonnet-4-6"),
        ("OpenRouter",        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",   "anthropic/claude-3.5-sonnet"),
        ("DeepSeek",          env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"), "DEEPSEEK_API_KEY", "deepseek-chat"),
        ("OpenAI",            env.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),     "OPENAI_API_KEY",   "gpt-4o-mini"),
        ("xAI",               "https://api.x.ai/v1",      "XAI_API_KEY",              "grok-4"),
    ]

    ok = []
    for name, base, keyname, model in targets:
        key = env.get(keyname, "")
        if not key or len(key) < 20 or "your_" in key:
            print(f"  [skip] {name:<22} {keyname} 未配置或为占位符")
            continue
        if probe(name, base, key, model):
            ok.append((name, base, keyname, model))

    print("\n可用端点：")
    for name, base, keyname, model in ok:
        print(f"  - {name}: base={base} key_env={keyname} model={model}")
    if not ok:
        print("  （无）")


if __name__ == "__main__":
    main()
