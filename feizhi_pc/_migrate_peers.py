# -*- coding: utf-8 -*-
r"""把单用户状态迁到多用户布局。默认 dry-run，只打印计划不落盘。

迁移什么

  state/feizhi_memory.json
      facts / events（全部关于<OWNER>）  ->  state/peers/<wxid>/memory.json  整份搬走

  state/feizhi_life.json
      projects / mood / last_tick      ->  state/feizhi_self.json        她自己的日子，共享
      shared / influences / open_loops ->  state/peers/<wxid>/life_private.json  关系私有

  另外新建 state/peers/<wxid>/relation.json，标成 intimate（<OWNER>是男朋友）。
  其他人的档位一律从 stranger 起步，宁可先客气也不能对陌生人喊"宝宝"。

安全

  · 默认 dry-run，只有 --apply 才写盘
  · 写盘前把原文件复制成 *.pre-peers.bak，随时可以退回去
  · 迁完立刻回读校验数量：facts / events / open_loops 一条都不能少

用法

  python _migrate_peers.py            # 看计划
  python _migrate_peers.py --apply    # 真迁
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

STATE = ROOT / "state"
MEM_SRC = STATE / "feizhi_memory.json"
LIFE_SRC = STATE / "feizhi_life.json"

PEER = "<WXID_FRIEND_A>"          # 现有数据全属于<OWNER>
SELF_DST = STATE / "feizhi_self.json"
PEER_DIR = STATE / "peers" / PEER
MEM_DST = PEER_DIR / "memory.json"
LIFE_PRIV_DST = PEER_DIR / "life_private.json"
REL_DST = PEER_DIR / "relation.json"

SHARED_KEYS = ("projects", "mood", "last_tick")
PRIVATE_KEYS = ("shared", "influences", "open_loops")

APPLY = "--apply" in sys.argv


def load(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def dump(obj: dict, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if APPLY:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    print("    %s %s  %d 字节"
          % ("写入" if APPLY else "将写入", p.relative_to(ROOT),
             len(json.dumps(obj, ensure_ascii=False).encode("utf-8"))))


def brief(name: str, obj: dict) -> str:
    bits = []
    for k, v in obj.items():
        if isinstance(v, list):
            bits.append("%s=%d" % (k, len(v)))
        elif isinstance(v, dict):
            bits.append("%s={%s}" % (k, ",".join(list(v)[:3])))
        elif v not in ("", None):
            bits.append("%s=%s" % (k, str(v)[:24]))
    return "%s: %s" % (name, " ".join(bits) or "(空)")


def main() -> int:
    print("=" * 70)
    print("多用户状态迁移  %s" % ("★ 真写盘" if APPLY else "dry-run（不写任何东西）"))
    print("=" * 70)

    mem = load(MEM_SRC)
    life = load(LIFE_SRC)
    if not mem and not life:
        print("两个源文件都不存在，没什么可迁的。")
        return 1

    print("\n[源]")
    print("   ", brief("memory", mem))
    print("   ", brief("life", life))

    # ---------- 备份 ----------
    if APPLY:
        print("\n[备份]")
        for src in (MEM_SRC, LIFE_SRC):
            if src.exists():
                bak = src.with_suffix(src.suffix + ".pre-peers.bak")
                if not bak.exists():
                    shutil.copy2(src, bak)
                    print("    已备份", bak.name)
                else:
                    print("    备份已存在，跳过", bak.name)

    # ---------- 1. 记忆整份搬到 peer ----------
    print("\n[1] 关系记忆 -> peers/%s/memory.json" % PEER)
    dump(mem, MEM_DST)

    # ---------- 2. 生活状态拆两层 ----------
    print("\n[2] 共享层 -> feizhi_self.json")
    self_obj = {k: life.get(k) for k in SHARED_KEYS if k in life}
    dump(self_obj, SELF_DST)

    print("\n[3] 私有层 -> peers/%s/life_private.json" % PEER)
    priv_obj = {k: life.get(k) for k in PRIVATE_KEYS if k in life}
    dump(priv_obj, LIFE_PRIV_DST)

    # ---------- 4. 关系档位 ----------
    print("\n[4] 关系档位 -> peers/%s/relation.json" % PEER)
    rel = {
        "peer": PEER,
        "relation": "intimate",
        "i_call_them": "<OWNER>",
        "they_call_me": "",
        "since": "",
        "note": "迁移时建立：现有全部数据都属于这个人",
    }
    if REL_DST.exists():
        print("    已存在，保留原样不覆盖")
    else:
        dump(rel, REL_DST)

    # ---------- 校验 ----------
    print("\n[5] 校验（数量必须一致）")
    want = {
        "facts": len(mem.get("facts") or []),
        "events": len(mem.get("events") or []),
        "open_loops": len(life.get("open_loops") or []),
        "shared": len(life.get("shared") or []),
        "influences": len(life.get("influences") or []),
        "projects": len(life.get("projects") or []),
    }
    print("    源：", want)
    if APPLY:
        got_mem = load(MEM_DST)
        got_self = load(SELF_DST)
        got_priv = load(LIFE_PRIV_DST)
        got = {
            "facts": len(got_mem.get("facts") or []),
            "events": len(got_mem.get("events") or []),
            "open_loops": len(got_priv.get("open_loops") or []),
            "shared": len(got_priv.get("shared") or []),
            "influences": len(got_priv.get("influences") or []),
            "projects": len(got_self.get("projects") or []),
        }
        print("    目标：", got)
        bad = [k for k in want if want[k] != got[k]]
        if bad:
            print("    ★ 不一致：", bad, "—— 立刻用 *.pre-peers.bak 回滚")
            return 2
        print("    全部一致 ✓")

        # ---------- 用真实类加载一遍，确认识别 ----------
        print("\n[6] 用运行时类实际加载")
        from peer_state import PeerRegistry
        reg = PeerRegistry()
        found = reg.warm_from_disk()
        print("    磁盘上发现联系人：", found)
        st = reg.get(PEER)
        print("    ", st)
        print("     stats:", st.stats())
        print("     life 在手项目:", [p.get("title") for p in st.life.ongoing()])
        print("     life 心情:", (st.life.data.get("mood") or {}).get("state"))
        print("     记忆渲染 %d 字" % len(st.memory.render()))
    else:
        print("    （dry-run 不做回读）")

    print("\n" + "=" * 70)
    if APPLY:
        print("迁移完成。原文件已备份为 *.pre-peers.bak，可随时回滚。")
    else:
        print("这只是计划。确认无误后加 --apply 真迁。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
