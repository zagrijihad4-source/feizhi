import logging, sys
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
import sing
ok = sing.sing("雨爱", peer="<WXID_FRIEND_A>")
print("发送:", "成功" if ok else "失败")
