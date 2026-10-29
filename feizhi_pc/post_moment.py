# -*- coding: utf-8 -*-
"""发一条朋友圈（绯栀）。

安全性：**默认只走到发表前**（填好文案、截图、不点发表）。
真想发出去必须显式加 `--send`，避免"跑个测试不小心发出去"。

用法
    python post_moment.py --text "今天画了一整天的海报，糊糊在稿纸边上睡了三个小时。"
    python post_moment.py --generate              # 让模型按人格现写一条，填进去给你看
    python post_moment.py --generate --send       # 生成并直接发
    python post_moment.py --text "..." --send     # 指定内容直接发
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from moments import MomentsPublisher, shot, SHOT_DIR  # noqa: E402

HISTORY = HERE / "state" / "moments_posted.json"
WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

MOMENT_RULES = (
    "\n\n【当前任务：写一条朋友圈】\n"
    "你不是在回消息，而是在发一条朋友圈——给所有人看的一小段独白。\n"
    "要求：\n"
    "1. 40~90 字，第一人称，只写一件事或一个念头；\n"
    "2. 要有具体的生活细节（画、颜料、猫糊糊、天气、课、楼下的小店、吃的东西）；\n"
    "3. 不提问、不求回应、不称呼任何人，也不要出现「朋友圈」这三个字；\n"
    "4. 不要每句都用「今天」开头，不要写励志金句，不要总结人生；\n"
    "5. 最多一个 emoji，也可以一个都不用；\n"
    "6. 只输出正文本身，不要引号、不要标题、不要任何解释。\n"
)


def load_history() -> list[dict]:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def remember(text: str, mode: str) -> None:
    rows = load_history()
    rows.append({"text": text, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode})
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


def generate() -> str:
    """按人格现写一条朋友圈文案。"""
    from llm import LLMClient, LLMError
    from persona import style_block

    now = datetime.now()
    recent = load_history()[-8:]
    # ★ 朋友圈也要从"她正在做的事"取材，不能和聊天里说的对不上
    life = ""
    try:
        # 朋友圈只讲她自己的日子，读共享层就够（不掺任何人的关系私有层）
        from peer_state import self_life
        life = self_life().render()
    except Exception:  # noqa: BLE001
        pass
    user = "现在是 %s（%s）。写一条朋友圈。" % (
        now.strftime("%Y-%m-%d %H:%M"), WEEKDAY[now.weekday()])
    if life:
        user += "\n\n" + life
    if recent:
        user += ("\n\n最近已经发过的（换一个角度，不要重复，也不要写成同一个模子）：\n"
                 + "\n".join("- " + r["text"] for r in recent))

    try:
        text = LLMClient().chat(style_block(include_emoji=False) + MOMENT_RULES,
                                user, max_tokens=300, temperature=1.0)
    except LLMError as e:
        # ★ 抛普通业务异常，不用 SystemExit（审查 R10）：
        #   SystemExit 继承自 BaseException，常驻调度器里的 except Exception 捕不到，
        #   一次瞬时模型故障就会让整个日程循环退出。
        raise RuntimeError("文案生成失败：%s" % e) from e
    return text.strip().strip('"').strip("“”")


def main() -> int:
    ap = argparse.ArgumentParser(description="发朋友圈（默认只填到发表前）")
    ap.add_argument("--text", default="", help="直接指定文案")
    ap.add_argument("--generate", action="store_true", help="让模型按人格生成一条")
    ap.add_argument("--send", action="store_true", help="真的点发表（缺省只填不发表）")
    ap.add_argument("--no-humanize", action="store_true", help="关掉拟人节奏")
    ap.add_argument("--keep", action="store_true", help="收尾时保留发表框（默认 dry-run 后也关掉）")
    args = ap.parse_args()

    if args.generate and args.text:
        print("--text 与 --generate 不能同时用")
        return 2
    if not args.generate and not args.text:
        print("需要 --text 或 --generate")
        return 2

    if args.generate:
        try:
            text = generate()
        except RuntimeError as exc:
            print("生成失败：%s" % exc)
            return 1
    else:
        text = args.text
    print("\n文案（%d 字）：\n%s\n" % (len(text), text))

    pub = MomentsPublisher(humanize=not args.no_humanize)
    import moments as _moments
    prev_fg = int(_moments.u32.GetForegroundWindow() or 0)
    res = pub.post(text, dry_run=not args.send)
    print(json.dumps(res, ensure_ascii=False, default=str, indent=2))

    mode = "send" if args.send else "dry_run"
    if res.get("ok"):
        remember(text, mode)
        if mode == "send":
            print("\n已发表。")
        else:
            print("\n已填好并截图，未发表。确认后加 --send 真发。")
            if not args.keep:
                time.sleep(2.0)
                closed = pub.cancel()
                print("发表框清理=%s" % closed)
                print("前台归还=%s" % pub._restore_foreground(prev_fg))
    else:
        print("\n失败：%s" % res.get("open", res.get("write", {})))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
