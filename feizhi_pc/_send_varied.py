import logging, sys
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import voice
ok = voice.say("真的假的！你居然还记得呀……我还以为你早忘了。", "开心", "<WXID_FRIEND_A>")
print("发送:", "成功" if ok else "失败")
