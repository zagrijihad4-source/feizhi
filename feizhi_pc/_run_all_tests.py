"""跑全量测试并汇总。用 Python 而不是 .ps1：
   * PS 5.1 读 .ps1 时若没有 BOM 会按 GBK 解析，含中文的 python 路径直接变乱码
     （实测 `<PYTHON_HOME>` → `<PYTHON_HOME>`）。
   * `sys.executable` 天然是当前解释器，不必硬编码路径。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.stdout.reconfigure(encoding="utf-8")

TESTS = [
    "_test_memrec.py",
    "_test_memory_crud.py",
    "_test_extract_wiring.py",
    "_verify_migrate_dryrun.py",
    "_test_memory_cert.py",
    "_test_provider_lock.py",
    "_wire_eligible_to_memory.py",
    "_test_default_branch.py",
    "_test_reflect.py",
    # 2026-10-28 新增：多用户与记忆闸门
    "_test_gate.py",          # pending -> eligible 唯一出口
    "_test_mood_log.py",      # 情绪时间线
    "_test_loops.py",         # 待回访
    "_test_outguard.py",      # 输出守卫
    "_test_ctx_guard.py",     # 上下文闸门
    "_test_memory_input.py",  # 记忆输入校验
    "_test_quiet.py",         # 安静结束
    "_test_dssafety.py",      # 元数据泄漏
    "_test_voice_request.py", # 语音触发词
    "_test_interrupt.py",     # 打断改口
]

failed = []
for t in TESTS:
    if not (ROOT / t).exists():
        print("%-28s MISSING" % t)
        failed.append(t)
        continue
    r = subprocess.run([sys.executable, t], cwd=str(ROOT),
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = [ln for ln in (r.stdout or "").strip().splitlines() if ln.strip()]
    print("%-28s exit=%s  %s" % (t, r.returncode, tail[-1] if tail else ""))
    if r.returncode != 0:
        failed.append(t)
        for ln in tail[-6:]:
            print("      " + ln)

print()
print("ALL PASS" if not failed else "FAILED: " + ", ".join(failed))
sys.exit(1 if failed else 0)
