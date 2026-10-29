import logging, sys
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import voice
ok = voice.say("测试一下，这条应该发到你那儿去", "温柔", "<WXID_FRIEND_A>")
print("结果:", ok)
