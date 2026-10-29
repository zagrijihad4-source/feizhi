"""反思层 dry-run：对生产记忆跑一次体检，报告落到 eval/_reflect_report.json。

只读，不改 memory.json，不改 state/reflection.json（避免污染正式报告）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import reflect  # noqa: E402

OUT = Path(__file__).resolve().parent / "eval" / "_reflect_report.json"
TXT = Path(__file__).resolve().parent / "eval" / "_reflect_report.txt"

rep = reflect.scan(FeizhiMemory())
OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

lines = []
lines.append("ts=%s today=%s scanned=%d actionable=%d"
             % (rep["ts"], rep["today"], rep["scanned"], rep["actionable"]))
lines.append("summary=%s" % (rep["summary"],))
lines.append("")
for i, f in enumerate(rep["findings"], 1):
    lines.append("%2d. [%s/%s] %s  action=%s auto_ok=%s"
                 % (i, f["check"], f["severity"], ",".join(f["refs"]),
                    f["action"], f["auto_ok"]))
    lines.append("    正文：%s" % f["text"])
    if f.get("text_b"):
        lines.append("    对照：%s" % f["text_b"])
    lines.append("    依据：%s" % f["evidence"])
TXT.write_text("\n".join(lines), encoding="utf-8")
print("wrote %s / %s" % (OUT.name, TXT.name))
