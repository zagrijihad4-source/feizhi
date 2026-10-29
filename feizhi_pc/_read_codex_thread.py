# -*- coding: utf-8 -*-
"""读取 Codex rollout jsonl 的尾部，提取最近几条对话消息。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

P = Path(r"C:\Users\api62\.codex\sessions\2026\10\26"
         r"\rollout-2026-10-26T13-49-40-01a176c1-e214-7dd1-bded-93bc64f609af.jsonl")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def tail_lines(path: Path, max_bytes: int = 900_000):
    size = path.stat().st_size
    with path.open("rb") as f:
        f.seek(max(0, size - max_bytes))
        data = f.read()
    lines = data.split(b"\n")
    if size > max_bytes:
        lines = lines[1:]          # 第一行可能被截断
    return [ln.decode("utf-8", "replace") for ln in lines if ln.strip()]


def text_of(payload) -> str:
    """从各种 payload 形状里抠出正文。"""
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "content", "text", "output"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v
        if isinstance(v, list):
            parts = []
            for it in v:
                if isinstance(it, dict):
                    t = it.get("text") or it.get("content")
                    if isinstance(t, str):
                        parts.append(t)
                elif isinstance(it, str):
                    parts.append(it)
            if parts:
                return "\n".join(parts)
    return ""


def main() -> int:
    msgs = []
    for raw in tail_lines(P):
        try:
            obj = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        typ = obj.get("type")
        pay = obj.get("payload") or {}
        role = pay.get("role") or pay.get("type") or ""
        txt = text_of(pay)
        if not txt:
            continue
        if typ not in ("response_item", "event_msg"):
            continue
        if role in ("user", "assistant"):
            msgs.append({"ts": obj.get("timestamp", ""), "role": role,
                         "type": pay.get("type", ""), "text": txt})

    print("尾部解析到 %d 条对话消息，取最后 %d 条：" % (len(msgs), N))
    print()
    for m in msgs[-N:]:
        print("=" * 78)
        print("[%s] %s  (%s)" % (m["ts"][:19], m["role"], m["type"]))
        print("=" * 78)
        print(m["text"][:3000])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
