"""接线验证：真实调用一次 maybe_reflect 到生产路径。

验证两件事：
  1. `state/reflection.json` 能正常落盘；
  2. `state/feizhi_memory.json` **一个字节都没变**。
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory  # noqa: E402
import reflect  # noqa: E402

MP = ROOT / "state" / "feizhi_memory.json"
before = hashlib.sha256(MP.read_bytes()).hexdigest()[:16]
res = reflect.maybe_reflect(FeizhiMemory())
after = hashlib.sha256(MP.read_bytes()).hexdigest()[:16]

print("memory before=%s after=%s unchanged=%s" % (before, after, before == after))
print("result=%s" % (res,))

rp = reflect.DEFAULT_PATH
print("report=%s exists=%s" % (rp, rp.exists()))
if rp.exists():
    rep = json.loads(rp.read_text(encoding="utf-8"))
    print("scanned=%d actionable=%d summary=%s"
          % (rep["scanned"], rep["actionable"], rep["summary"]))
    print("tmp_leftover=%s" % rp.with_suffix(".json.tmp").exists())

if not MP.read_bytes() or before != after:
    sys.exit(1)
