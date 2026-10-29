# -*- coding: utf-8 -*-
"""微信 4.x 图片缓存 .dat 解密（V2 格式）。

V2 文件布局（社区实测格式，本机 4.1.9.23 已对齐）：

    [0x00:0x06] 6B  签名  07 08 'V2' 08 07
    [0x06:0x0A] 4B  aes_size  (LE)
    [0x0A:0x0E] 4B  xor_size  (LE)
    [0x0E:0x0F] 1B  padding 占位
    [0x0F:0x0F+align16(aes_size)]   AES-128-ECB + PKCS7 密文
    [...          until len-xor_size] 明文段（原样）
    [len-xor_size: len]              单字节 XOR 段

AES key 是 16 字符 ASCII，存在于微信进程内存中；XOR key 单字节，
可从未尾 FF D9（JPEG EOI）反推。

对外只暴露两个函数：
    resolve_image(msg_raw)   -> Path | None   给一条 type=3 消息，找出本机图片文件
    decrypt_dat(path)        -> bytes | None  给一个 .dat，返回图片明文
"""
from __future__ import annotations

import ctypes
import json
import logging
import re
import struct
import threading
from ctypes import wintypes
from pathlib import Path

LOG = logging.getLogger("feizhi_pc.img_dat")

V2_MAGIC = b"\x07\x08V2\x08\x07"
STATE_DIR = Path(r"<PROJECT_ROOT>\feizhi_pc\state")
KEY_FILE = STATE_DIR / "image_key.json"


def _find_account_root() -> Path:
    """定位微信 4.x 的账号数据根目录（含 msg/attach）。

    优先级：环境变量 FEIZHI_WECHAT_HOME > 已知路径 > 自动扫常见位置。
    换机、换号、微信改存储位置时不用改代码。
    """
    import os
    env = os.environ.get("FEIZHI_WECHAT_HOME", "")
    if env and (Path(env) / "msg" / "attach").is_dir():
        return Path(env)
    fixed = Path(r"D:\xwechat_files\<WXID_SELF>_dfb4")
    if (fixed / "msg" / "attach").is_dir():
        return fixed
    for base in (Path(r"D:\xwechat_files"),
                 Path(r"C:\xwechat_files"),
                 Path.home() / "Documents" / "xwechat_files"):
        if not base.is_dir():
            continue
        try:
            for p in base.iterdir():
                if p.is_dir() and (p / "msg" / "attach").is_dir():
                    LOG.info("自动定位到微信数据目录: %s", p)
                    return p
        except OSError:
            continue
    LOG.warning("没找到微信数据目录，图片解密将不可用")
    return fixed


# 微信 4.x 账号数据根（活动目录）。
ACCOUNT_ROOT = _find_account_root()
ATTACH = ACCOUNT_ROOT / "msg" / "attach"

MAGICS = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"RIFF", "webp"),
    (b"wxgf", "hevc"),
    (b"GIF8", "gif"),
)


# ---------------------------------------------------------------- 图片明文判断
def sniff(plain: bytes) -> str | None:
    for magic, ext in MAGICS:
        if plain.startswith(magic):
            return ext
    return None


# ---------------------------------------------------------------- 头部解析
def parse_header(data: bytes) -> dict | None:
    if len(data) < 15 or data[:6] != V2_MAGIC:
        return None
    aes_size, xor_size = struct.unpack_from("<LL", data, 6)
    if aes_size > len(data) or xor_size > len(data):
        return None
    aligned = (aes_size + 15) // 16 * 16
    if 15 + aligned > len(data):
        return None
    return {
        "aes_size": aes_size,
        "aligned": aligned,
        "xor_size": xor_size,
        "raw_size": len(data) - 15 - aligned - xor_size,
    }


def xor_key_from_tail(data: bytes) -> int | None:
    """从未尾两字节推 XOR key（JPEG 以 FF D9 结尾）。"""
    if len(data) < 2:
        return None
    k = data[-2] ^ 0xFF
    if (data[-1] ^ k) == 0xD9:
        return k
    # PNG 结尾 IEND\xAE\x42\x60\x82
    k2 = data[-1] ^ 0x82
    if (data[-2] ^ k2) == 0x60:
        return k2
    return None


# ---------------------------------------------------------------- 解密
def decrypt_dat(path: Path, aes_key: bytes, xor_key: int | None = None) -> tuple[bytes, str] | None:
    """解密一个 V2 .dat。返回 (明文, 扩展名)；失败 None。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    hdr = parse_header(data)
    if not hdr:
        return None
    if xor_key is None:
        xor_key = xor_key_from_tail(data)

    from Crypto.Cipher import AES

    off = 15
    aes_part = data[off:off + hdr["aligned"]]
    try:
        dec = AES.new(aes_key, AES.MODE_ECB).decrypt(aes_part)
    except Exception as exc:  # noqa: BLE001
        LOG.debug("AES 段解密失败 %s: %s", path.name, exc)
        return None

    # ★ 不要做 PKCS7 unpad。实测（2026-10-25，用 578568 B 原图逐字节对照）：
    #   AES 段解密出来 **整段 1024 字节都是图片明文**，不需要也不允许 unpad
    #   （照社区脚本做 unpad 会抛 "Padding is incorrect"）。
    #   AES 段之后、XOR 段之前还夹着一段 `pad` 字节的占位，那才是要丢弃的东西：
    #       plain = AES明文(全 1024) + XOR明文
    #       1024 + 577544 = 578568 = 原图长度 ✅
    plain_aes = dec
    pad = hdr["raw_size"]
    if pad and pad != 16:
        LOG.debug("%s: 占位长度为 %d（通常 16），已按结构丢弃", path.name, pad)

    xor_part = data[len(data) - hdr["xor_size"]:]
    if xor_key is not None and xor_part:
        xor_part = bytes(b ^ xor_key for b in xor_part)

    plain = plain_aes + xor_part
    ext = sniff(plain)
    if not ext:
        return None
    return plain, ext


# ---------------------------------------------------------------- AES key 提取
class _MBI(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


_k32 = ctypes.windll.kernel32
_MEM_COMMIT = 0x1000
_PAGE_NOACCESS = 0x01
_PAGE_GUARD = 0x100
_RW = 0x04 | 0x08 | 0x40 | 0x80
_RE16 = re.compile(rb"(?<![a-zA-Z0-9])[a-zA-Z0-9]{16}(?![a-zA-Z0-9])")
_RE32 = re.compile(rb"(?<![a-zA-Z0-9])[a-zA-Z0-9]{32}(?![a-zA-Z0-9])")


def _wechat_pids() -> list[int]:
    import subprocess
    try:
        out = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq Weixin.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:  # noqa: BLE001
        return []
    pids = []
    for line in out.strip().splitlines():
        parts = line.strip().strip('"').split('","')
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def _try_aes(key: bytes, ciphertext: bytes) -> bool:
    try:
        from Crypto.Cipher import AES
        dec = AES.new(key, AES.MODE_ECB).decrypt(ciphertext)
    except Exception:  # noqa: BLE001
        return False
    return sniff(dec) is not None


def _sample_ciphertext() -> bytes | None:
    """取任一 V2 dat 的第一块密文，用于校验候选 key。"""
    for p in sorted(ATTACH.rglob("*_t.dat"), key=lambda x: x.stat().st_mtime, reverse=True)[:60]:
        try:
            with p.open("rb") as fh:
                head = fh.read(31)
        except OSError:
            continue
        if head[:6] == V2_MAGIC and len(head) >= 31:
            return head[15:31]
    return None


def _load_saved_key() -> bytes | None:
    """读 state/image_key.json。兼容两种写法：
        {"aes_key": "16位ASCII"}       （第一版扫描器）
        {"aes_key_hex": "32位hex"}     （后续扫描器，key 是二进制）
    """
    try:
        raw = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    ascii_key = raw.get("aes_key") or ""
    if len(ascii_key) == 16:
        return ascii_key.encode()
    hex_key = raw.get("aes_key_hex") or ""
    if len(hex_key) == 32:
        try:
            return bytes.fromhex(hex_key)
        except ValueError:
            return None
    return None


def extract_aes_key(force: bool = False) -> bytes | None:
    """拿到图片 AES key（16 字节），结果缓存到 state/image_key.json。

    顺序：缓存 → **磁盘派生**（确定性，不用碰进程）→ 扫内存（兜底）。

    派生的依据是微信的命名约定（社区算法，本机 4.1.9.23 复验通过）：
        xor_key = uin & 0xFF
        aes_key = MD5(f"{uin}{wxid}").hexdigest()[:16]
        uin 满足：账号目录名末 4 位 hex == md5(str(uin))[:4]
    因为已知 xor_key（从 dat 末尾反推），uin 的空间被压到 2^24，十几秒枚举完。
    """
    if not force:
        key = _load_saved_key()
        if key:
            ct = _sample_ciphertext()
            if ct is None or _try_aes(key, ct):
                return key
            LOG.warning("缓存里的图片 AES key 已失效，重新获取")

    derived = derive_aes_key()
    if derived:
        return derived

    LOG.info("磁盘派生失败，改为扫描微信进程内存")
    ct = _sample_ciphertext()
    if ct is None:
        LOG.warning("找不到 V2 .dat 样本，无法提取 key")
        return None

    pids = _wechat_pids()
    if not pids:
        LOG.warning("微信未运行，无法从内存提取图片 AES key")
        return None

    access = 0x0010 | 0x0400  # PROCESS_VM_READ | PROCESS_QUERY_INFORMATION
    for pid in pids:
        h = _k32.OpenProcess(access, False, pid)
        if not h:
            continue
        try:
            key = _scan_process(h, ct)
        finally:
            _k32.CloseHandle(h)
        if key:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            KEY_FILE.write_text(json.dumps(
                {"aes_key": key.decode(), "pid": pid}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            LOG.info("已提取图片 AES key（pid=%s）", pid)
            return key
    LOG.warning("扫描完所有微信进程仍未找到图片 AES key")
    return None


def _account_suffix_and_wxid() -> tuple[str, str]:
    """从账号目录名拆出 (末 4 位 hex 后缀, 归一化 wxid)。"""
    name = ACCOUNT_ROOT.name
    suffix = ""
    tail = name.rsplit("_", 1)[-1]
    if len(tail) == 4 and all(c in "0123456789abcdefABCDEF" for c in tail):
        suffix = tail.lower()
    if name.lower().startswith("wxid_"):
        parts = name.split("_")
        wxid = "_".join(parts[:-1]) if len(parts) >= 3 and len(parts[-1]) == 4 else name
    else:
        wxid = name
    return suffix, wxid


def _xor_key_from_dats(sample: int = 40) -> int | None:
    """扫多个 _t.dat 末两字节投票反推 xor_key（JPEG EOI = FF D9）。"""
    votes: dict[int, int] = {}
    dats = sorted(ATTACH.rglob("*_t.dat"), key=lambda p: p.stat().st_mtime,
                  reverse=True)[:sample]
    for p in dats:
        try:
            with p.open("rb") as fh:
                head = fh.read(6)
                fh.seek(-2, 2)
                tail = fh.read(2)
        except OSError:
            continue
        if head != V2_MAGIC or len(tail) != 2:
            continue
        k = tail[0] ^ 0xFF
        if (tail[1] ^ k) == 0xD9:
            votes[k] = votes.get(k, 0) + 1
    if not votes:
        return None
    return max(votes, key=votes.get)


def derive_aes_key(max_candidates: int = 24) -> bytes | None:
    """从磁盘派生出 aes_key（不读进程内存）。失败返回 None。"""
    import hashlib

    suffix, wxid = _account_suffix_and_wxid()
    if not suffix:
        LOG.info("账号目录名没有 4 位 hex 后缀，无法派生（%s）", ACCOUNT_ROOT.name)
        return None
    xor_key = _xor_key_from_dats()
    if xor_key is None:
        return None
    LOG.info("派生参数：wxid=%s 后缀=%s xor_key=0x%02x", wxid, suffix, xor_key)

    suffix_bytes = bytes.fromhex(suffix)
    wbytes = wxid.encode()
    found: list[tuple[int, bytes]] = []
    import time as _t
    t0 = _t.time()
    for i in range(1 << 24):
        uin = (i << 8) | xor_key
        ub = str(uin).encode()
        if hashlib.md5(ub).digest()[:2] != suffix_bytes:
            continue
        aes_key = hashlib.md5(ub + wbytes).hexdigest()[:16].encode()
        found.append((uin, aes_key))
    LOG.info("枚举完成 %.1fs，候选 %d 个", _t.time() - t0, len(found))
    if not found:
        return None

    # 先用 16 字节魔数快速筛（十几毫秒级），再对幸存者做完整解密验证。
    # ★ 注意必须遍历**全部**候选：md5 前缀命中约 200+ 个，正确那个位置不定，
    #   早先只验证前 64 个，正好漏掉了真的那把。
    ct = _sample_ciphertext()
    survivors = [(u, k) for u, k in found if ct and _try_aes(k, ct)] if ct else found
    LOG.info("魔数筛后剩 %d 个候选", len(survivors))

    probe = sorted(ATTACH.rglob("*_h.dat"))[:3] or sorted(ATTACH.rglob("*.dat"))[:3]
    best: tuple[int, int, bytes] | None = None
    for uin, aes_key in survivors:
        ok = sum(1 for p in probe if decrypt_dat(p, aes_key))
        if ok and (best is None or ok > best[1]):
            best = (uin, ok, aes_key)
    if not best and survivors is not found:
        # 魔数筛可能因样本异常全灭，退回全量验证
        for uin, aes_key in found:
            ok = sum(1 for p in probe if decrypt_dat(p, aes_key))
            if ok and (best is None or ok > best[1]):
                best = (uin, ok, aes_key)
    if not best:
        LOG.warning("派生出的候选都无法解密，可能 uin 规则与当前版本不符")
        return None
    uin, ok, aes_key = best
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(json.dumps(
        {"aes_key": aes_key.decode(), "aes_key_hex": aes_key.hex(),
         "uin": uin, "xor_key": xor_key, "derived": True},
        ensure_ascii=False, indent=2), encoding="utf-8")
    LOG.info("派生成功：uin=%s aes_key=%s（验证解开 %d/4 张）",
             uin, aes_key.decode(), ok)
    return aes_key


def _scan_process(h, ciphertext: bytes) -> bytes | None:
    addr = 0
    mbi = _MBI()
    regions = []
    while addr < 0x7FFFFFFFFFFF:
        got = _k32.VirtualQueryEx(h, ctypes.c_void_p(addr),
                                  ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not got:
            break
        if (mbi.State == _MEM_COMMIT and mbi.Protect != _PAGE_NOACCESS
                and not (mbi.Protect & _PAGE_GUARD)
                and 0 < mbi.RegionSize <= 80 * 1024 * 1024):
            if mbi.Protect & _RW:
                regions.append((mbi.BaseAddress, mbi.RegionSize))
        nxt = addr + mbi.RegionSize
        if nxt <= addr:
            break
        addr = nxt

    for base, size in regions:
        buf = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        if not _k32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size,
                                      ctypes.byref(read)):
            continue
        data = buf.raw[:read.value]
        for m in _RE16.finditer(data):
            cand = m.group()
            if _try_aes(cand, ciphertext):
                return cand
        for m in _RE32.finditer(data):
            cand = m.group()
            if _try_aes(cand[:16], ciphertext):
                return cand[:16]
            if _try_aes(cand, ciphertext):
                return cand
    return None


# ------------------------------------------------- 后台追 key（首次激活用）
_bg_lock = threading.Lock()
_bg_running = False


def _start_bg_key_hunt(max_sec: float = 240.0) -> None:
    """后台持续追图片 AES key。

    为什么要后台：key 只在微信**渲染图片**的那一刻才载入内存，而收到消息与
    渲染之间有几百毫秒到几秒的差。前台最多等 1 秒多，剩下的交给这条线程；
    拿到就写进 state/image_key.json，之后所有解密都不再需要扫描。
    """
    global _bg_running
    with _bg_lock:
        if _bg_running:
            return
        _bg_running = True

    def run() -> None:
        global _bg_running
        import time as _t
        deadline = _t.monotonic() + max_sec
        try:
            while _t.monotonic() < deadline:
                if extract_aes_key(force=True):
                    LOG.info("图片密钥已在后台激活完成，后续图片可直接解密")
                    return
                _t.sleep(4.0)
            LOG.warning("后台激活图片密钥超时（%.0f 秒）——"
                        "需要微信里真的显示过一张图片才会加载它", max_sec)
        finally:
            with _bg_lock:
                _bg_running = False

    threading.Thread(target=run, daemon=True, name="img-key-hunt").start()


# ---------------------------------------------------------------- 消息 → 文件
_XML_ATTR = re.compile(r'(\w+)="([^"]*)"')

def msg_attrs(content: str) -> dict:
    return dict(_XML_ATTR.findall(content or ""))


def candidate_dats(peer_wxid: str, ts: int) -> list[Path]:
    """按会话 + 月份 + 时间窗，列出可能属于这条消息的 dat。

    微信 4.x: msg/attach/<md5(peer_wxid)>/<YYYY-MM>/Img/*.dat
    """
    import hashlib
    import time

    peer_dir = ATTACH / hashlib.md5(peer_wxid.encode()).hexdigest()
    roots = [peer_dir] if peer_dir.is_dir() else []
    if not roots:
        return []
    out: list[tuple[float, Path]] = []
    for root in roots:
        for p in root.rglob("*.dat"):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            # 缓存写入时间 ≈ 消息时间（放宽到 1 小时，覆盖未及时下载的情况）
            if abs(mtime - ts) <= 3600 or ts == 0:
                out.append((abs(mtime - ts), p))
    out.sort()
    return [p for _, p in out]


def resolve_image(peer_wxid: str, ts: int, content: str,
                  aes_key: bytes | None = None,
                  prefer: str = "auto") -> tuple[Path, bytes, str] | None:
    """给一条 type=3 消息，找出并解密对应的本地图片。

    同一张图在缓存里有三档：`<id>.dat`（中图，常是微信自定义的 wxgf/HEVC）、
    `<id>_h.dat`（大图，jpg）、`<id>_t.dat`（缩略图，jpg）。

    定位靠三件事，按可靠性排序：
      1. 解出的明文 md5 == XML 的 md5 / originsourcemd5（原样保存时命中）
      2. 缩略图尺寸 == XML 的 cdnthumbwidth×cdnthumbheight（**最常用**，
         因为 `_h` 是重新编码的，md5/长度都对不上，但 XML 里带着缩略图尺寸）
      3. 明文长度 == XML length，或落盘时间最接近消息时间

    定位到某一「组」之后，再在同组里挑**最大的 jpg/png** 交给视觉模型
    —— wxgf/HEVC 那档 claude 不认识，缩略图又太糊。

    返回 (dat 路径, 明文, 扩展名)。
    """
    attrs = msg_attrs(content)
    want_md5 = {v.lower() for v in (attrs.get("md5", ""), attrs.get("originsourcemd5", "")) if v}
    try:
        want_len = int(attrs.get("length") or 0)
    except ValueError:
        want_len = 0
    try:
        want_tw = int(attrs.get("cdnthumbwidth") or 0)
        want_th = int(attrs.get("cdnthumbheight") or 0)
    except ValueError:
        want_tw = want_th = 0

    if aes_key is None:
        aes_key = extract_aes_key()
    if aes_key is None:
        # ★ 时序：DLL 收到消息 → 写 inbox 往往比微信 UI 渲染缩略图更快，
        #   而图片 AES key 是「渲染图片时才载入内存」的，所以第一次扫不到很正常。
        #   这里只再等一小会儿（一次），避免把第一条图片回复拖长；
        #   同时起后台线程持续追 key，下一张图就能正常解密。
        import time as _t
        _t.sleep(1.2)
        aes_key = extract_aes_key(force=True)
    if aes_key is None:
        _start_bg_key_hunt()
        return None

    cands = candidate_dats(peer_wxid, ts)
    if not cands:
        LOG.info("会话 %s 时间 %s 附近没有图片缓存", peer_wxid, ts)
        return None

    import hashlib

    def group_of(p: Path) -> str:
        name = p.stem
        for suf in ("_t", "_h", "_m"):
            if name.endswith(suf):
                return name[:-2]
        return name

    groups: dict[str, list[dict]] = {}
    for p in cands[:120]:
        got = decrypt_dat(p, aes_key)
        if not got:
            continue
        plain, ext = got
        w = h = 0
        if ext in ("jpg", "png", "webp", "gif"):
            try:
                from io import BytesIO
                from PIL import Image
                with Image.open(BytesIO(plain)) as im:
                    w, h = im.size
            except Exception:  # noqa: BLE001
                pass
        groups.setdefault(group_of(p), []).append({
            "path": p, "plain": plain, "ext": ext, "w": w, "h": h,
            "md5": hashlib.md5(plain).hexdigest(),
            "gap": abs(p.stat().st_mtime - ts) if ts else 0,
        })

    best_gid, best_score = None, -1
    for gid, items in groups.items():
        score = 0
        for it in items:
            if want_md5 and it["md5"] in want_md5:
                score = max(score, 200)
            if want_tw and want_th and it["w"] == want_tw and it["h"] == want_th:
                score = max(score, 180)
            if want_len and len(it["plain"]) == want_len:
                score = max(score, 170)
            # 缓存里的缩略图未必等于 XML 标注的那一档（实测 XML 常说 214x480，
            # 而 _t.dat 解出 94x210，是更小的一档），所以再按**宽高比**兜一层：
            # 连发多图时靠这个把「同一张图的不同尺寸」和「恰好同时间的另一张」分开。
            if want_tw and want_th and it["w"] and it["h"]:
                r1 = it["w"] / it["h"]
                r2 = want_tw / want_th
                if abs(r1 - r2) <= 0.02:
                    score = max(score, 120)
        if score == 0:
            score = 60
        # 同一张图的各档落盘时间一样，取组内最小间隔即可
        gap = min(it["gap"] for it in items)
        score -= min(gap / 60.0, 40.0)      # 每差 1 分钟扣 1 分，最多扣 40
        if score > best_score:
            best_gid, best_score = gid, score

    if best_gid is None:
        return None

    items = groups[best_gid]
    usable = [it for it in items if it["ext"] in ("jpg", "png", "webp", "gif")]
    if not usable:
        LOG.info("这一组只有 HEVC/wxgf，视觉模型不认识，跳过")
        return None
    # 同组里挑像素数最大的 jpg（_h 通常远大于 _t）
    pick = max(usable, key=lambda it: (it["w"] * it["h"], len(it["plain"])))
    LOG.info("图片匹配 score=%.0f %s %dx%d %.1f KB",
             best_score, pick["path"].name, pick["w"], pick["h"],
             len(pick["plain"]) / 1024)
    return pick["path"], pick["plain"], pick["ext"]


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    key = extract_aes_key()
    print("AES key:", key)
    if not key:
        raise SystemExit(1)
    n = 0
    for p in sorted(ATTACH.rglob("*.dat"))[:200]:
        got = decrypt_dat(p, key)
        if not got:
            continue
        plain, ext = got
        n += 1
        if n <= 8:
            print("  OK %-46s %-5s %8d B" % (p.name, ext, len(plain)))
    print("可解密 %d 个" % n)
