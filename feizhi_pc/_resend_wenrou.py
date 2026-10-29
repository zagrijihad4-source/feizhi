import logging, sys
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import voice
for i in range(3):
    ok = voice.say("宝宝，我在呢，刚在改稿子，听见你叫我就过来了。", "温柔", "<WXID_FRIEND_A>")
    print("第 %d 次：%s" % (i + 1, "成功" if ok else "失败"))
    if ok:
        break
    import time; time.sleep(8)
