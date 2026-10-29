import ctypes, ctypes.wintypes as wt, importlib.util, sys
from pathlib import Path
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("pw", "_wx_printwin.py")
pw = importlib.util.module_from_spec(spec); spec.loader.exec_module(pw)
from PIL import Image

hwnd = int(ctypes.windll.user32.FindWindowW(None, "微信") or 0)
w, h, px = pw.grab(hwnd)
im = Image.frombytes("RGBA", (w, h), px).convert("RGB")
out = Path("state/_wx_own.png")
im.save(out)
print("微信自身画面:", out, "%dx%d" % (w, h))
