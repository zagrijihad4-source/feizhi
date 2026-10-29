"""强制注入新 DLL：先停掉旧 worker，再加载新副本。

为什么需要它：
  reinject.py 是"一次性注入器"，检测到进程里已有 wx_hook_bridge 就直接跳过
  （hook_loaded 判断）。这导致改完代码后无法热更新，只能重启微信。

本脚本流程：
  1. 写 stop.txt，让旧 worker 主动退出（它会 uninstall_recv_hook 释放 hook 站点）
  2. 等几秒并删掉 stop.txt
  3. 直接调 inject_hook（不做 hook_loaded 检测），加载 dist 里的新 DLL
     —— 注入器会用带时间戳的新文件名，所以不会与旧模块冲突
  4. 等新 worker 报告 worker started

用法:
    python force_inject.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(r"<PROJECT_ROOT>\wx-basic-bridge")
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "python" / "inject"))

os.environ["WX_HOOK_DLL_FILE"] = str(ROOT / "dist" / "wx_hook_bridge.dll")

from wechat_inject import inject_hook  # noqa: E402
from wechat_native import choose_wechat_target, find_wechat_processes  # noqa: E402

SUPPORTED = "4.1.9.23"
CONTROL = ROOT / "bridge" / "control"
STOP = CONTROL / "stop.txt"
STATUS = CONTROL / "status.txt"
TIMEOUT = 90.0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass

    procs = find_wechat_processes()
    host = next((p for p in procs
                 if p.get("weixin_base") and p.get("weixin_version") == SUPPORTED), None)
    if not host:
        got = ", ".join(f"{p.get('pid')}:{p.get('weixin_version') or 'n/a'}" for p in procs)
        print(f"找不到 {SUPPORTED} 主进程（当前: {got}）")
        return 1
    pid = int(host["pid"])
    print(f"host pid={pid} version={host.get('weixin_version')}")

    # 1) 停旧 worker
    print("写 stop.txt 让旧 worker 退出 ...")
    STOP.parent.mkdir(parents=True, exist_ok=True)
    STOP.write_text("stop\n", encoding="utf-8")
    time.sleep(4)
    try:
        STOP.unlink()
        print("已删除 stop.txt")
    except OSError as e:
        print(f"删除 stop.txt 失败: {e}")

    # 清掉上一轮的启动握手残留
    for f in CONTROL.glob("worker_start_*"):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        STATUS.unlink()
    except OSError:
        pass

    # 2) 取注入目标
    target = choose_wechat_target()
    if not target or int(target.get("pid") or 0) == 0:
        print("找不到 UI 目标窗口")
        return 2
    tid = int(target.get("tid") or 0)
    hwnd = int(target.get("hwnd") or 0)
    print(f"注入: pid={pid} tid={tid} hwnd=0x{hwnd:X}")

    holder: dict = {}

    def worker():
        try:
            holder["rc"] = inject_hook(pid, tid, hwnd)
        except Exception as exc:  # noqa: BLE001
            holder["err"] = repr(exc)

    th = threading.Thread(target=worker, daemon=True)
    th.start()

    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        time.sleep(1.0)
        if STATUS.exists():
            txt = STATUS.read_text(encoding="utf-8", errors="replace")
            if "worker started" in txt:
                print(">>> 新 worker 已启动")
                # 立即退出，不等 daemon 线程（它进入常驻循环不返回）
                sys.stdout.flush()
                os._exit(0)
        if "err" in holder:
            print(f"inject 抛错: {holder['err']}")
            return 3
        if "rc" in holder and not th.is_alive():
            break

    print(f"未在 {TIMEOUT:.0f}s 内确认 worker 启动 (rc={holder.get('rc')})")
    if STATUS.exists():
        print("status:", STATUS.read_text(encoding="utf-8", errors="replace"))
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
