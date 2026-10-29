# -*- coding: utf-8 -*-
"""绯栀自动发朋友圈调度器（无人值守）。

策略（保守，可改 state/moment_policy.json）：
  - 每天最多 1 条
  - 只在 09:00–23:00 之间
  - 与上一条至少间隔 6 小时
  - 每天的目标时刻随机生成（不是整点，看起来像人）
  - 文案由 LLM 按人格现写，避开最近发过的内容

无人值守的前提与边界：
  1. 微信必须在运行且已登录；
  2. **电脑不能处于锁屏状态**。锁屏后 SendInput（真实鼠标/键盘）会被 Winlogon
     接管，而「发表」按钮只认真实鼠标（PostMessage 与 Enter 都试过，无效）。
     所以锁屏时本进程会把当天的发布顺延到解锁后再做，而不是硬发。
     切页/长按/写文案这几步走 PostMessage + WM_CHAR，锁屏也不受影响。

用法：
    python moment_scheduler.py --status          # 看今天计划与历史
    python moment_scheduler.py --once            # 检查一次，到点就发
    python moment_scheduler.py --once --dry-run  # 只填不发表（演练）
    python moment_scheduler.py --force           # 忽略时段，立刻发一条（测试用）
    python moment_scheduler.py --loop            # 常驻，每 5 分钟检查一次
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from ctypes import wintypes

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

STATE = HERE / "state" / "moment_schedule.json"
POLICY_FILE = HERE / "state" / "moment_policy.json"
LOG = HERE / "logs" / "moment_scheduler.log"

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
u32.OpenInputDesktop.restype = wintypes.HANDLE
u32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
u32.CloseDesktop.argtypes = [wintypes.HANDLE]

DEFAULT_POLICY = {
    "enabled": True,
    "max_per_day": 1,
    "window_start": "09:00",
    "window_end": "23:00",
    "min_gap_hours": 6.0,
    "jitter_minutes": 90,      # 目标时刻前后随机浮动，避免天天同一时间
}


def log(msg: str) -> None:
    line = "%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        print(line)          # pythonw 下没有控制台，打印失败不算错
    except Exception:
        pass
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_locked() -> bool:
    """当前工作站是否处于锁屏状态。锁屏时输入桌面不是 Default。"""
    h = u32.OpenInputDesktop(0, False, 0x0100)   # DESKTOP_READOBJECTS
    if not h:
        return True
    try:
        buf = ctypes.create_unicode_buffer(256)
        need = wintypes.DWORD()
        if not u32.GetUserObjectInformationW(h, 2, buf, 512, ctypes.byref(need)):  # UOI_NAME
            return True
        return buf.value.strip().lower() != "default"
    finally:
        u32.CloseDesktop(h)


def load_policy() -> dict:
    pol = dict(DEFAULT_POLICY)
    if POLICY_FILE.exists():
        try:
            pol.update(json.loads(POLICY_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return pol


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"days": {}, "last_post": None}


def save_state(st: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def today_key(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def plan_for_today(st: dict, pol: dict, now: datetime | None = None) -> dict:
    """确保今天有计划时刻（不存在就随机生成一个）。"""
    now = now or datetime.now()
    key = today_key(now)
    day = st.setdefault("days", {}).setdefault(key, {"posted": []})
    if not day.get("target"):
        h0, m0 = (int(x) for x in pol["window_start"].split(":"))
        h1, m1 = (int(x) for x in pol["window_end"].split(":"))
        start = now.replace(hour=h0, minute=m0, second=0, microsecond=0)
        end = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
        if end <= start:
            end = start + timedelta(hours=12)
        span = max(1, int((end - start).total_seconds()))
        # 落在中间 60% 区间，再叠加 jitter，避免贴着边界
        lo = int(span * 0.15)
        hi = max(lo + 1, int(span * 0.85))
        target = start + timedelta(seconds=random.randint(lo, hi))
        jit = random.randint(-pol["jitter_minutes"], pol["jitter_minutes"]) * 60
        target = target + timedelta(seconds=jit)
        if target <= now:
            target = now + timedelta(minutes=random.randint(5, 40))
        day["target"] = target.isoformat(timespec="seconds")
    return day


def due(st: dict, pol: dict, now: datetime | None = None) -> tuple[bool, str]:
    now = now or datetime.now()
    if not pol.get("enabled", True):
        return False, "策略已禁用"
    day = plan_for_today(st, pol, now)
    posted = day.get("posted", [])
    if len(posted) >= pol["max_per_day"]:
        return False, "今天已发够 %d 条" % pol["max_per_day"]
    last = st.get("last_post")
    if last:
        gap = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
        if gap < pol["min_gap_hours"]:
            return False, "距上一条仅 %.1f 小时（需 %.1f）" % (gap, pol["min_gap_hours"])
    target = datetime.fromisoformat(day["target"])
    if now < target:
        return False, "还没到计划时刻 %s" % target.strftime("%H:%M")
    # ★ 真实执行前再核一次时间窗（审查 R11）：
    #   锁屏顺延、或 tick 错过之后，now 可能已经越过 window_end，
    #   这时不该再发（例如配置 23:00 结束、顺延到 23:30 仍返回"该发"）。
    try:
        eh, em = (int(x) for x in pol["window_end"].split(":"))
        end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
        if now > end:
            return False, "已过发布窗口（%s 结束，现在 %s），顺延到明天" % (
                pol["window_end"], now.strftime("%H:%M"))
    except Exception:  # noqa: BLE001
        pass
    return True, "到点（计划 %s）" % target.strftime("%H:%M")


def do_post(dry_run: bool) -> tuple[bool, str]:
    """发一条：生成文案 -> 走朋友圈链路。返回 (是否成功, 文案)。

    ★ 这里**不写**文案历史 —— 记账顺序交给 run_once（审查 R07）。
    """
    import post_moment
    from moments import MomentsPublisher

    try:
        text = post_moment.generate()
    except Exception as exc:  # noqa: BLE001
        # 生成失败不能让常驻循环挂掉（审查 R10）：本轮跳过，下一次 tick 再试
        log("文案生成失败（本轮跳过，稍后重试）: %r" % (exc,))
        return False, ""
    log("文案：%s" % text)
    pub = MomentsPublisher(verbose=False)
    res = pub.post(text, dry_run=dry_run)
    if res.get("ok"):
        log("发布%s成功：%s" % ("（演练）" if dry_run else "", text))
        return True, text
    log("发布失败：%s" % json.dumps(res.get("open") or res.get("write") or {},
                                   ensure_ascii=False, default=str))
    return False, text


def record_post(st: dict, text: str) -> bool:
    """记当天配额。返回是否写入成功（失败要显式知道，否则会重复发布）。"""
    now = datetime.now()
    key = today_key(now)
    day = st.setdefault("days", {}).setdefault(key, {"posted": []})
    day.setdefault("posted", []).append({"time": now.isoformat(timespec="seconds")})
    st["last_post"] = now.isoformat(timespec="seconds")
    # 只保留最近 60 天，避免文件无限增长
    for k in sorted(st["days"])[:-60]:
        st["days"].pop(k, None)
    try:
        save_state(st)
        return True
    except Exception as exc:  # noqa: BLE001
        log("严重：配额写入失败 %r" % (exc,))
        return False


def run_once(dry_run: bool, force: bool) -> int:
    pol = load_policy()
    st = load_state()
    now = datetime.now()
    plan_for_today(st, pol, now)
    save_state(st)

    if force:
        ok, why = True, "force"
    else:
        ok, why = due(st, pol, now)
    log("检查：%s" % why)
    if not ok:
        return 0

    if is_locked():
        log("工作站已锁屏 —— 锁屏时「发表」按钮点不动（真实鼠标被锁屏界面接管），"
            "顺延到解锁后再发")
        return 2

    ok, text = do_post(dry_run)
    if ok:
        if not dry_run:
            # ★ 先记配额，再写文案历史（审查 R07）。
            #   旧顺序是 remember() 先落盘、失败就抛，配额没更新，
            #   下一次 tick 又认为该发 —— 结果就是重复发布。
            #   配额是"防重复"的唯一依据，必须最先落盘。
            if not record_post(st, text):
                log("严重：已发布但配额写入失败，请立刻检查 state/moment_schedule.json")
            try:
                import post_moment
                post_moment.remember(text, "auto")
            except Exception as exc:  # noqa: BLE001
                log("警告：文案历史写入失败（不影响配额，不会重复发布）: %r" % (exc,))
        return 0
    return 1


def show_status() -> int:
    pol = load_policy()
    st = load_state()
    now = datetime.now()
    day = plan_for_today(st, pol, now)
    print("策略：%s" % json.dumps(pol, ensure_ascii=False))
    print("今天：%s" % today_key(now))
    print("  计划时刻：%s" % day.get("target"))
    print("  已发：%d 条" % len(day.get("posted", [])))
    print("  上一条：%s" % st.get("last_post"))
    print("  当前锁屏：%s" % is_locked())
    ok, why = due(st, pol, now)
    print("  现在该发吗：%s（%s）" % (ok, why))
    hist = (HERE / "state" / "moments_posted.json")
    if hist.exists():
        try:
            rows = json.loads(hist.read_text(encoding="utf-8"))
            print("最近发布：")
            for r in rows[-5:]:
                print("    %s [%s] %s" % (r.get("time"), r.get("mode"), r.get("text", "")[:40]))
        except Exception:
            pass
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="绯栀自动发朋友圈调度器")
    ap.add_argument("--status", action="store_true", help="看计划与历史")
    ap.add_argument("--once", action="store_true", help="检查一次")
    ap.add_argument("--loop", action="store_true", help="常驻循环")
    ap.add_argument("--interval", type=int, default=300, help="循环间隔秒数")
    ap.add_argument("--dry-run", action="store_true", help="只填不发表")
    ap.add_argument("--force", action="store_true", help="忽略时段立即发")
    args = ap.parse_args()

    if args.status:
        return show_status()

    if args.loop:
        log("进入常驻循环（每 %d 秒检查一次）" % args.interval)
        while True:
            try:
                run_once(args.dry_run, False)
            except KeyboardInterrupt:
                log("收到中断，退出")
                return 0
            except Exception as e:  # noqa: BLE001
                log("检查出错：%r" % (e,))
            time.sleep(args.interval)

    return run_once(args.dry_run, args.force)


if __name__ == "__main__":
    sys.exit(main())
