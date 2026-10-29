# -*- coding: utf-8 -*-
"""从磁盘派生微信 4.x 图片 AES key —— 不需要读进程内存。

算法（来源：wechat-decrypt / find_image_key_macos.py，已在 mac 上验证；
Windows 4.1.9.23 本机复验）：

    xor_key = uin & 0xFF
    aes_key = MD5(f"{uin}{wxid}").hexdigest()[:16]     ← 16 字符 hex，按 ASCII 取 16 字节

其中 uin 是微信内部用户号（十进制数字），关键结构性约束：
    **账号目录名后缀 4 位 hex == md5(str(uin))[:4]**
    例如本机目录 `<WXID_SELF>_dfb4` → uin 满足 md5(str(uin))[:4] == "dfb4"

而 xor_key 可以从 V2 .dat 末尾反推（JPEG EOI = FF D9）。
于是把 uin 的搜索空间压到 2^24（低字节固定 = xor_key），单核几秒就能枚举完。

命中判定用**已知明文-密文对**：AES-ECB 解出的首块必须等于图片真实头部。

用法:
    python find_key_by_derive.py            # 自动读账号目录 / 已知明文
    python find_key_by_derive.py --verify   # 找到后顺便解一张图看看
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
import img_dat as M  # noqa: E402

ACCOUNT = M.ACCOUNT_ROOT
WXID_DIR = ACCOUNT.name                    # 形如 wxid_xxx_dfb4


def clean_wxid(name: str) -> str:
    """<WXID_SELF>_dfb4 -> <WXID_SELF>"""
    if name.lower().startswith("wxid_"):
        parts = name.split("_")
        # wxid_<seg>_<4位后缀>：取前两段
        if len(parts) >= 3 and len(parts[-1]) == 4:
            return "_".join(parts[:-1])
        return name
    return name


def dir_suffix(name: str) -> str:
    """取目录名末尾的 4 位 hex 后缀。"""
    tail = name.rsplit("_", 1)[-1]
    if len(tail) == 4 and all(c in "0123456789abcdefABCDEF" for c in tail):
        return tail.lower()
    return ""


def xor_key_from_dats() -> tuple[int | None, int]:
    """扫多个 _t.dat，用末尾两字节投票反推 xor_key。"""
    votes: dict[int, int] = {}
    dats = sorted(M.ATTACH.rglob("*_t.dat"), key=lambda p: p.stat().st_mtime,
                  reverse=True)[:40]
    for p in dats:
        try:
            with p.open("rb") as fh:
                head = fh.read(6)
                fh.seek(-2, 2)
                tail = fh.read(2)
        except OSError:
            continue
        if head != M.V2_MAGIC or len(tail) != 2:
            continue
        k = tail[0] ^ 0xFF
        if (tail[1] ^ k) == 0xD9:
            votes[k] = votes.get(k, 0) + 1
    if not votes:
        return None, 0
    best = max(votes, key=votes.get)
    return best, votes[best]


def build_known_pair() -> tuple[bytes, bytes] | None:
    """用我们自己发出去的已知原图 + 它的 _h.dat 做验证对。"""
    src = Path(r"<PROJECT_ROOT>\feizhi_pc\images\gen_9f816f698803f168.jpg")
    dat = (M.ATTACH / hashlib.md5(b"filehelper").hexdigest()
           / "2026-10" / "Img" / "9e93939518f3d1932c4351236304064b_h.dat")
    if not (src.is_file() and dat.is_file()):
        return None
    return src.read_bytes()[:16], dat.read_bytes()[15:31]


def aes_ok(key_ascii: str, pair: tuple[bytes, bytes]) -> bool:
    from Crypto.Cipher import AES
    plain, cipher = pair
    try:
        return AES.new(key_ascii.encode("ascii"), AES.MODE_ECB).decrypt(cipher) == plain
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    wxid = clean_wxid(WXID_DIR)
    suffix = dir_suffix(WXID_DIR)
    print("账号目录 :", ACCOUNT)
    print("归一化 wxid:", wxid)
    print("目录后缀 :", suffix or "(无，无法用 md5 前缀过滤)")

    xor_key, votes = xor_key_from_dats()
    print("xor_key  :", ("0x%02x" % xor_key) if xor_key is not None else None,
          "（%d 票）" % votes)
    if xor_key is None:
        print("无法确定 xor_key，放弃")
        return 1

    pair = build_known_pair()
    if pair:
        print("已知明文 :", pair[0].hex(), "/ 密文", pair[1].hex())
    else:
        print("没有已知明文对 —— 找到候选后只能靠图像魔数判定")
    if not suffix:
        print("没有目录后缀，退回全空间枚举（很慢），先退出")
        return 1

    suffix_bytes = bytes.fromhex(suffix)
    t0 = time.time()
    found: list[tuple[int, str]] = []
    total = 1 << 24
    print("\n开始枚举 uin（2^24 = %d 个候选）…" % total, flush=True)
    for i in range(total):
        uin = (i << 8) | xor_key
        ub = str(uin).encode()
        if hashlib.md5(ub).digest()[:2] != suffix_bytes:
            continue
        aes_key = hashlib.md5(ub + wxid.encode()).hexdigest()[:16]
        if pair and not aes_ok(aes_key, pair):
            continue
        found.append((uin, aes_key))
        print("  命中 uin=%d  aes_key=%s  (%.1fs)" % (uin, aes_key, time.time() - t0),
              flush=True)
        if len(found) >= 8:
            break

    print("\n耗时 %.1fs，命中 %d 个" % (time.time() - t0, len(found)))
    if not found:
        print("没有命中 —— 可能与已知明文对不匹配（该图非全局 key，或结构假设有误）")
        return 1

    # 用第一个命中去解全部缓存，择优（解出图片数量最多的那个）
    best = None
    for uin, aes_key in found:
        ok = 0
        for p in sorted(M.ATTACH.rglob("*.dat"))[:30]:
            if M.decrypt_dat(p, aes_key.encode()):
                ok += 1
        print("  uin=%-12d 解开 %d/30 张" % (uin, ok))
        if best is None or ok > best[2]:
            best = (uin, aes_key, ok)

    uin, aes_key, ok = best
    print("\n选中 uin=%s  aes_key=%s（解开 %d 张）" % (uin, aes_key, ok))
    M.STATE_DIR.mkdir(parents=True, exist_ok=True)
    M.KEY_FILE.write_text(
        '{"aes_key": "%s", "aes_key_hex": "%s", "uin": %s, "xor_key": %d, '
        '"derived": true}'
        % (aes_key, aes_key.encode().hex(), uin, xor_key), encoding="utf-8")
    print("已写入", M.KEY_FILE)

    if "--verify" in sys.argv and ok:
        print("\n=== 验证：解一张并识别 ===")
        for p in sorted(M.ATTACH.rglob("*.dat"))[:40]:
            got = M.decrypt_dat(p, aes_key.encode())
            if not got:
                continue
            plain, ext = got
            print("%s -> %s %d B" % (p.name, ext, len(plain)))
            import vision
            print("识别:", vision.describe_bytes(plain) or "(失败)")
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
