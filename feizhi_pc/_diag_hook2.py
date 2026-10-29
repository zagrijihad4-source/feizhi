import logging, sys
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import voice
pid = voice._pick_pid()
hwnd = voice.find_wechat_window()
print("_pick_pid =", pid)
print("find_wechat_window =", hwnd)
s = voice.VoiceSender()
print("_ensure =", s._ensure())
print("_hwnd =", s._hwnd)
print("hook exports 可用 =", s._script is not None)
if s._script is not None:
    try:
        print("progress =", s._ex.progress())
    except Exception as e:
        print("progress 失败:", e)
s.close()
