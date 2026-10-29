import sys
from pathlib import Path
sys.path.insert(0, ".")
from bridge import HookBridge

DROP = ("3475858840290998220", "3540344040840048612")
b = HookBridge()
lines = [ln for ln in b.seen_file.read_text(encoding="utf-8", errors="replace").splitlines()
         if ln.strip()]
keep = [ln for ln in lines if not any(k in ln for k in DROP)]
removed = len(lines) - len(keep)
b.seen_file.write_text("\n".join(keep) + "\n", encoding="utf-8")
print("删掉 %d 行标记（%d -> %d）" % (removed, len(lines), len(keep)))
