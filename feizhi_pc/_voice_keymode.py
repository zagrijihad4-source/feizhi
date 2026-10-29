# -*- coding: utf-8 -*-
r"""对照实验：Alt 到底该怎么按，微信才认为「在按住说话」。

背景：2026-10-28 12:44 语音连续 8 次 calls=0，而微信窗口可见、在前台、
尺寸正常。紧接着 PrintWindow 一查 —— 整窗白屏 98.3%。也就是说界面被某种
操作打坏了，输入框和「按住说话」按钮根本不存在。

目前嫌疑最大的是给微信投 PostMessage 键盘消息（Qt 对合成按键的扫描码很挑）。
这个脚本把三种按法分开测，用 hook 的 calls 判定哪种真的能让微信进录音态：

  A 现状    keybd_event 真按 + PostMessage 投递（voice._say_once 现在就是这样）
  B 纯真实  keybd_event 按下 -> 保持 -> 抬起，一个窗口消息都不投
  C 纯投递  只 PostMessage DOWN/UP，不碰系统键盘状态

★ 跑之前先确认两件事：微信界面是正常的（不是白屏）、当前会话是<OWNER>。
  白屏状态下三种全都会失败，测了也没意义 —— 脚本开头会先自检白占比。
"""
import ctypes
import ctypes.wintypes as wt
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

spec = importlib.util.spec_from_file_location("pw", str(ROOT / "_wx_printwin.py"))
pw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pw)

u32 = ctypes.windll.user32

VK_RMENU, EXT_KEY, KEYUP = 0xA5, 0x0001, 0x0002
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
PEER = "<WXID_FRIEND_A>"

PCM = ROOT / "state" / "_probe.pcm"


def ralt_lp(up: bool) -> int:
    """Alt 的 lParam：扫描码 0x38，扩展位 + 上下文位，抬起再加 PREV/TRANS。"""
    lp = 1 | (0x38 << 16) | (1 << 24) | (1 << 29)
    if up:
        lp |= (1 << 30) | (1 << 31)
    return lp


def white_ratio() -> float:
    hwnd = int(u32.FindWindowW(None, "微信") or 0)
    w, h, px = pw.grab(hwnd)
    if not px:
        return -1.0
    total = white = 0
    for i in range(0, len(px) - 3, 44):
        b, g, r = px[i], px[i + 1], px[i + 2]
        total += 1
        if r > 235 and g > 235 and b > 235:
            white += 1
    return 100.0 * white / total


def run(sender, name: str, on_down, on_up, hold_max: float = 10.0) -> bool:
    ex = sender._ex
    ex.arm()
    t0 = time.time()
    done = False
    st = {}
    try:
        on_down()
        while time.time() - t0 < hold_max:
            time.sleep(0.03)
            pr = ex.progress()
            if pr["total"] > 0 and pr["cursor"] >= pr["total"]:
                done = True
                break
            if pr["calls"] == 0 and time.time() - t0 >= 2.5:
                break
    finally:
        for fn in (on_up, lambda: st.update(ex.disarm() or {})):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                print("  清理失败:", exc)
    print("  %s -> calls=%s cursor=%s/%s %s"
          % (name, st.get("calls"), st.get("cursor"), st.get("total"),
             "成功" if done else "失败"), flush=True)
    return done


def main() -> int:
    import voice

    wx = int(u32.FindWindowW(None, "微信") or 0)
    wr = white_ratio()
    print("微信 hwnd=%d  白占比 %.1f%%" % (wx, wr))
    if wr > 40:
        print("★ 界面是白屏（%.1f%%），先恢复微信再跑这个实验，否则三种按法全都会失败。" % wr)
        return 3

    sender = voice.VoiceSender()
    if not sender._ensure():
        print("hook 不可用")
        return 2
    hwnd = sender._hwnd
    sender.open_recent_chat(PEER)
    time.sleep(0.8)

    n = sender._ex.loadfile(str(PCM))
    print("载入样本数:", n)
    if white_ratio() > 40:
        print("★ 切会话之后变成白屏了 —— 说明是 open_recent_chat 里的某个动作打白的。")
        return 4

    res = {}

    print("[B] 纯真实 keybd_event（一个窗口消息都不投）")
    res["B"] = run(
        sender, "B",
        lambda: u32.keybd_event(VK_RMENU, 0, EXT_KEY, None),
        lambda: u32.keybd_event(VK_RMENU, 0, EXT_KEY | KEYUP, None),
    )
    time.sleep(2.0)
    if white_ratio() > 40:
        print("  ⚠ 白屏了，之后的结果不可信")
    else:
        print("[C] 只 PostMessage，不碰系统键盘")
        res["C"] = run(
            sender, "C",
            lambda: u32.PostMessageW(hwnd, WM_KEYDOWN, ctypes.c_void_p(VK_RMENU),
                                     ctypes.c_void_p(ralt_lp(False))),
            lambda: u32.PostMessageW(hwnd, WM_KEYUP, ctypes.c_void_p(VK_RMENU),
                                     ctypes.c_void_p(ralt_lp(True))),
        )
        time.sleep(2.0)
        if white_ratio() > 40:
            print("  ⚠ 白屏了，A 不再测")
            sender.close()
            print("汇总:", res)
            return 0

        print("[A] 现状：真按 + 投递")
        res["A"] = run(
            sender, "A",
            lambda: (u32.keybd_event(VK_RMENU, 0, EXT_KEY, None),
                     u32.PostMessageW(hwnd, WM_KEYDOWN, ctypes.c_void_p(VK_RMENU),
                                      ctypes.c_void_p(ralt_lp(False)))),
            lambda: (u32.PostMessageW(hwnd, WM_KEYUP, ctypes.c_void_p(VK_RMENU),
                                      ctypes.c_void_p(ralt_lp(True))),
                     u32.keybd_event(VK_RMENU, 0, EXT_KEY | KEYUP, None)),
        )

    sender.close()
    print("=" * 60)
    print("汇总:", res)
    print("白色占比(结束): %.1f%%" % white_ratio())
    return 0 if any(res.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
