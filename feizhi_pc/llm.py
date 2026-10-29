"""可插拔 LLM 客户端（OpenAI 兼容协议）。

支持：
  - 任意 OpenAI 兼容端点（base_url + api_key + model）
  - 多提供方按顺序自动故障转移
  - 从 llm_config.json 读取配置（不存在则用内置默认）

用法：
    llm = LLMClient()                       # 用配置里的顺序
    llm = LLMClient(order=["deepseek"])     # 指定顺序
    text = llm.chat(system, user)
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

LOG = logging.getLogger("feizhi_pc.llm")

# ★ 2026-10-18 实测事故：上游网关会在正文**前面**塞一段安全判定元数据，
#   形如 `<ds_safety>[用户未成年]否 [分类]其他 [判定]… [规则]无</ds_safety>Safe`。
#   它被当成回复正文存进数据库、发到微信、再被下一轮历史喂回模型（自我强化）。
#   除了观感问题，它把 12 字的回复撑成 105 字 —— 拟人延迟按字数计算，
#   那条消息因此在队列里憋了 160 秒才发出去（实测 23:54:59 生成 → 23:57:39 送达）。
#   所有 LLM 返回值统一在这里剥干净，调用方拿到的永远是纯正文。
_META_TAG = re.compile(
    r"<ds_[A-Za-z0-9_]+>.*?</ds_[A-Za-z0-9_]+>\s*(?:Unsafe|Safe)?", re.S)
_META_OPEN = re.compile(r"<ds_[A-Za-z0-9_]+>.*\Z", re.S)
# 闭合标签后面往往紧跟判定结果（实测是 `</ds_safety>Safe`），一起吃掉，
# 否则剥完会留下一个孤零零的 "Safe" 贴在正文前面。
_META_CLOSE = re.compile(r"</ds_[A-Za-z0-9_]+>\s*(?:Unsafe|Safe)?", re.S)
_META_VERDICT = re.compile(r"\A\s*(?:Safe|Unsafe|safe|unsafe)\s*\Z")


def strip_meta_tags(raw: str) -> str:
    """剥掉上游注入的 <ds_*> 元数据标签及其判定残留。

    只在真的出现过 `ds_` 或判定词时才动手，正常文本原样返回（零成本）。
    剥完只剩一个 `Safe` / `Unsafe` 时返回空串 —— 空串会让调用方走兜底，
    比把判定词当回复发出去强。
    """
    s = raw or ""
    if "ds_" not in s and "Safe" not in s and "Unsafe" not in s:
        return s
    prev = None
    while prev != s:                     # 嵌套/不闭合都可能出现，剥到稳定为止
        prev = s
        s = _META_TAG.sub("", s)
        s = _META_OPEN.sub("", s)
        s = _META_CLOSE.sub("", s)
        s = s.strip()
    if s and _META_VERDICT.match(s):
        return ""
    return s

CONFIG_FILE = Path(r"<PROJECT_ROOT>\feizhi_pc\llm_config.json")
ENV_FILE = Path(r"D:\Hermes\.env")

# 内置提供方注册表。key_env 指向环境变量名（值从 .env 读）。
PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "synapse-claude": {
        "base_url": "https://synapse-ai.uk/v1",
        "key_env": "SYNAPSE_CLAUDE_API_KEY",
        "model": "claude-sonnet-4-6",
    },
    "synapse-grok": {
        "base_url": "https://synapse-ai.uk/v1",
        "key_env": "SYNAPSE_GROK_API_KEY",
        "model": "grok-4.5",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "anthropic/claude-3.5-sonnet",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
}

DEFAULT_ORDER = ["deepseek", "synapse-claude"]

_env_cache: dict | None = None


def load_env(force: bool = False) -> dict:
    global _env_cache
    if _env_cache is not None and not force:
        return _env_cache
    env: dict = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v and "your_" not in v:
                env[k] = v
    _env_cache = env
    return env


def resolve_key(key_env: str, inline_key: str = "") -> str:
    """密钥解析优先级：配置内联明文 > 环境变量 > <ENV_FILE>。

    内联明文用于在 llm_config.json 的 providers 覆盖里直接写 key；
    注意该文件是本地明文配置，不要提交到公开仓库。
    """
    if inline_key:
        return inline_key.strip()
    import os
    v = os.environ.get(key_env, "")
    if v:
        return v
    return load_env().get(key_env, "")


@dataclass
class LLMConfig:
    order: list[str] = field(default_factory=lambda: list(DEFAULT_ORDER))
    overrides: dict = field(default_factory=dict)   # name -> {base_url,key_env,model}
    timeout: int = 60
    max_attempts: int = 2

    @classmethod
    def load(cls) -> "LLMConfig":
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return cls(
                    order=raw.get("order", list(DEFAULT_ORDER)),
                    overrides=raw.get("providers", {}),
                    timeout=int(raw.get("timeout", 60)),
                    max_attempts=int(raw.get("max_attempts", 2)),
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("llm_config.json 解析失败，用默认: %s", exc)
        return cls()

    def save(self) -> None:
        CONFIG_FILE.write_text(json.dumps({
            "order": self.order,
            "providers": self.overrides,
            "timeout": self.timeout,
            "max_attempts": self.max_attempts,
        }, ensure_ascii=False, indent=2), encoding="utf-8")


class LLMError(RuntimeError):
    pass


# ---------- 用量统计 ----------
USAGE_FILE = Path(r"<PROJECT_ROOT>\feizhi_pc\state\token_usage.jsonl")

# DeepSeek 定价（元 / 百万 token）。缓存命中价约为未命中的 1/4。
PRICING = {
    "deepseek-chat":     {"in": 2.0, "in_cached": 0.5, "out": 8.0},
    "deepseek-reasoner": {"in": 4.0, "in_cached": 1.0, "out": 16.0},
    "claude-sonnet-4-6": {"in": 22.0, "in_cached": 2.2, "out": 110.0},
}
DEFAULT_PRICE = {"in": 2.0, "in_cached": 0.5, "out": 8.0}


def record_usage(provider: str, model: str, usage: dict) -> None:
    """把一次调用的 usage 追加到 jsonl，供统计与成本核算。"""
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": int(time.time() * 1000),
            "provider": provider,
            "model": model,
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
            "cached_tokens": int(usage.get("prompt_cache_hit_tokens")
                                  or usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
                                  or 0),
        }
        with USAGE_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        LOG.debug("记录用量失败: %s", exc)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int,
                  cached_tokens: int = 0) -> float:
    p = PRICING.get(model, DEFAULT_PRICE)
    miss = max(0, prompt_tokens - cached_tokens)
    return (miss * p["in"] + cached_tokens * p["in_cached"]
            + completion_tokens * p["out"]) / 1_000_000.0


def usage_summary() -> dict:
    """汇总 jsonl 用量。"""
    total = {"calls": 0, "prompt": 0, "completion": 0, "cached": 0, "cost": 0.0}
    by_day: dict[str, dict] = {}
    if not USAGE_FILE.exists():
        return {"total": total, "by_day": by_day}
    import datetime
    for line in USAGE_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        cost = estimate_cost(r.get("model", ""), r.get("prompt_tokens", 0),
                             r.get("completion_tokens", 0), r.get("cached_tokens", 0))
        total["calls"] += 1
        total["prompt"] += r.get("prompt_tokens", 0)
        total["completion"] += r.get("completion_tokens", 0)
        total["cached"] += r.get("cached_tokens", 0)
        total["cost"] += cost
        day = datetime.datetime.fromtimestamp(r.get("ts", 0) / 1000).strftime("%Y-%m-%d")
        d = by_day.setdefault(day, {"calls": 0, "prompt": 0, "completion": 0, "cached": 0, "cost": 0.0})
        d["calls"] += 1
        d["prompt"] += r.get("prompt_tokens", 0)
        d["completion"] += r.get("completion_tokens", 0)
        d["cached"] += r.get("cached_tokens", 0)
        d["cost"] += cost
    return {"total": total, "by_day": by_day}


class LLMClient:
    def __init__(self, order: list[str] | None = None, cfg: LLMConfig | None = None):
        self.cfg = cfg or LLMConfig.load()
        if order:
            self.cfg.order = order

    def _spec(self, name: str) -> dict:
        spec = dict(PROVIDERS.get(name, {}))
        spec.update(self.cfg.overrides.get(name, {}))
        return spec

    def chat(self, system: str, user: str,
             max_tokens: int = 500, temperature: float = 0.85) -> str:
        errors = []
        for name in self.cfg.order:
            spec = self._spec(name)
            base = spec.get("base_url", "")
            model = spec.get("model", "")
            key = resolve_key(spec.get("key_env", ""), spec.get("api_key", ""))
            if not (base and model):
                errors.append(f"{name}: 未注册")
                continue
            if not key:
                errors.append(f"{name}: key({spec.get('key_env')}) 未配置")
                continue
            url = base.rstrip("/") + "/chat/completions"
            for attempt in range(self.cfg.max_attempts):
                try:
                    t0 = time.time()
                    r = requests.post(
                        url,
                        headers={"Authorization": "Bearer " + key,
                                 "Content-Type": "application/json"},
                        json={"model": model,
                              "messages": [{"role": "system", "content": system},
                                           {"role": "user", "content": user}],
                              "max_tokens": max_tokens,
                              "temperature": temperature},
                        timeout=self.cfg.timeout,
                    )
                    dt = time.time() - t0
                    if r.status_code != 200:
                        errors.append(f"{name}: HTTP {r.status_code} {r.text[:100]}")
                        # 认证/额度类错误重试无意义，换下一家
                        if r.status_code in {401, 403, 404, 429, 500, 502, 503, 504}:
                            break
                        continue
                    txt = r.json()["choices"][0]["message"]["content"].strip()
                    txt = strip_meta_tags(txt)
                    if txt:
                        try:
                            record_usage(name, model, r.json().get("usage", {}) or {})
                        except Exception:  # noqa: BLE001
                            pass
                        LOG.info("LLM %s ok (%.1fs)", name, dt)
                        return txt
                    errors.append(f"{name}: 空响应")
                except requests.Timeout:
                    errors.append(f"{name}: 超时 {self.cfg.timeout}s")
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {type(exc).__name__} {exc}")
                    break
        raise LLMError("; ".join(errors[-5:]) or "没有可用端点")

    def health(self) -> list[tuple[str, bool, str]]:
        """逐个探测，返回 [(name, ok, detail)]。"""
        out = []
        for name in self.cfg.order:
            spec = self._spec(name)
            key = resolve_key(spec.get("key_env", ""), spec.get("api_key", ""))
            if not key:
                out.append((name, False, "key 未配置"))
                continue
            try:
                t0 = time.time()
                self.chat("只回复两个字", "可用", max_tokens=20, temperature=0) if False else None
                r = requests.post(
                    spec["base_url"].rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + key,
                             "Content-Type": "application/json"},
                    json={"model": spec["model"],
                          "messages": [{"role": "user", "content": "只回复两个字：可用"}],
                          "max_tokens": 20, "temperature": 0},
                    timeout=30,
                )
                dt = time.time() - t0
                if r.status_code == 200:
                    out.append((name, True, f"{dt:.1f}s"))
                else:
                    out.append((name, False, f"HTTP {r.status_code}"))
            except Exception as exc:  # noqa: BLE001
                out.append((name, False, type(exc).__name__))
        return out
