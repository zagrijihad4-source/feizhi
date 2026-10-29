"""feizhi_pc 统一入口。

用法:
  python run.py test        自检：hook 状态 / 桥连通 / LLM 可用 / 发送能力
  python run.py autoreply   只跑自动回复
  python run.py proactive   只跑主动消息
  python run.py both        两者同时跑（自动回复在前台，主动消息在后台线程）
  python run.py show        查看对话上下文最近记录
"""
from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge import HookBridge, IGNORE_PEERS      # noqa: E402
from store import ContextStore                    # noqa: E402
from llm import LLMClient, LLMConfig, PROVIDERS   # noqa: E402
from autoreply import AutoReplier, DEFAULT_ALLOW  # noqa: E402
from proactive import ProactiveSender, ProactiveConfig  # noqa: E402

LOG_DIR = Path(r"<PROJECT_ROOT>\feizhi_pc\logs")


def cmd_llm() -> int:
    cfg = LLMConfig.load()
    print("=" * 58)
    print("LLM 配置")
    print("=" * 58)
    print("配置文件 :", LLMConfig.__module__ and r"<PROJECT_ROOT>\feizhi_pc\llm_config.json")
    print("调用顺序 :", " -> ".join(cfg.order))
    print("超时     :", cfg.timeout, "s    重试:", cfg.max_attempts)
    print("\n已注册提供方:")
    for name, spec in PROVIDERS.items():
        mark = " *" if name in cfg.order else "  "
        print(f" {mark} {name:<16} {spec['model']:<28} {spec['base_url']}")
    print("\n连通性探测（逐个实测）:")
    client = LLMClient(cfg=cfg)
    for name, ok, detail in client.health():
        print(f"  {'[OK]  ' if ok else '[FAIL]'} {name:<16} {detail}")

    print("\n切换方式:")
    print("  直接编辑 llm_config.json 的 order 数组，或用：")
    print('  python run.py llm-set deepseek            # 只用 deepseek')
    print('  python run.py llm-set deepseek,synapse-claude')
    return 0


def cmd_llm_set(spec: str) -> int:
    names = [s.strip() for s in spec.split(",") if s.strip()]
    unknown = [n for n in names if n not in PROVIDERS]
    if unknown:
        print("未知提供方:", ", ".join(unknown))
        print("可选:", ", ".join(PROVIDERS))
        return 2
    cfg = LLMConfig.load()
    cfg.order = names
    cfg.save()
    print("已更新调用顺序:", " -> ".join(names))
    print("配置文件:", r"<PROJECT_ROOT>\feizhi_pc\llm_config.json")
    print("注意：常驻进程需要重启才会读取新配置。")
    return 0


def setup_logging(verbose: bool = False) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_DIR / "feizhi_pc.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_test() -> int:
    print("=" * 58)
    print("feizhi_pc 自检")
    print("=" * 58)
    b = HookBridge()
    print("\n[1] hook 桥状态")
    print("    bridge root :", b.root)
    print("    hook alive  :", b.hook_alive())
    print("    worker owner:", b.owner())

    print("\n[2] 待处理入站（只读，不会消耗消息）")
    seen_file = b.state_dir / "seen_inbox.txt"
    seen = set()
    if seen_file.exists():
        seen = {ln.strip() for ln in seen_file.read_text(
            encoding="utf-8", errors="replace").splitlines() if ln.strip()}
    pending = []
    if b.inbox.is_dir():
        import json as _json
        for path in sorted(b.inbox.glob("*.json"), key=lambda p: p.stat().st_mtime):
            if path.name in seen:
                continue
            try:
                data = _json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            key = "{}:{}:{}:{}".format(data.get("peerWxId", ""), data.get("msgId", ""),
                                       data.get("localId", ""), data.get("timestamp", ""))
            if key in seen:
                continue
            pending.append(data)
    print("    未处理消息数:", len(pending))
    for d in pending[:5]:
        print("      peer=%s incoming=%s type=%s content=%r"
              % (d.get("peerWxId"), d.get("isIncoming"), d.get("type"),
                 str(d.get("content", ""))[:40]))

    print("\n[3] LLM 可用性")
    try:
        sys.path.insert(0, r"D:\Hermes work\feizhi-wechat-phone-bridge\src")
        from feizhi_phone_bridge.reply_generator import _load_api_key
        key = _load_api_key("SYNAPSE_GROK_API_KEY")
        print("    API key:", "已读到(%d字符)" % len(key) if key else "未读到")
        from autoreply import HermesReplyGenerator
        plan = HermesReplyGenerator(timeout=45, attempts=1).generate_plan("在吗", [])
        print("    生成成功:", [m.text for m in plan.messages])
    except Exception as exc:  # noqa: BLE001
        print("    LLM 不可用:", type(exc).__name__, str(exc)[:120])

    print("\n[4] 上下文库")
    st = ContextStore()
    print("    记录统计:", st.counts())
    print("    最近 3 条:")
    for row in st.recent(3):
        print("      [%s] %s: %s" % (row["source"], row["role"], row["text"][:40]))

    print("\n[5] 允许自动回复的联系人:", DEFAULT_ALLOW or "(全部)")
    print("\n[6] 忽略的系统会话前缀:", ", ".join(sorted(IGNORE_PEERS)))
    print("\n自检完成。")
    return 0


def cmd_show() -> int:
    st = ContextStore()
    print("记录统计:", st.counts())
    for row in reversed(st.recent(20)):
        who = "<OWNER>" if row["role"] == "user" else "绯栀"
        print("[%s] %s: %s" % (row["source"], who, row["text"][:70]))
    return 0


def acquire_single_instance(tag: str) -> bool:
    """常驻模式单实例保护，避免自启与手动启动同时消费 inbox。"""
    import os
    lock = Path(r"<PROJECT_ROOT>\feizhi_pc\state") / ("run_%s.pid" % tag)
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            old = int(lock.read_text(encoding="utf-8", errors="replace").strip())
        except Exception:
            old = 0
        if old:
            try:
                import subprocess
                alive = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-Process -Id %d -ErrorAction SilentlyContinue | Measure-Object).Count" % old],
                    capture_output=True, text=True, timeout=20).stdout.strip()
                if alive.isdigit() and int(alive) > 0:
                    print("已有 %s 实例在运行 (pid=%d)，退出" % (tag, old))
                    return False
            except Exception:
                pass
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return True


def cmd_usage() -> int:
    """token 用量与成本统计，附余额查询。"""
    from llm import usage_summary, estimate_cost, PROVIDERS, LLMConfig, resolve_key
    import requests

    s = usage_summary()
    t = s["total"]
    print("=" * 62)
    print("Token 用量统计")
    print("=" * 62)
    if not t["calls"]:
        print("  还没有记录（每次 LLM 调用会自动累计）")
    else:
        print(f"  累计调用: {t['calls']} 次")
        print(f"  输入 token: {t['prompt']:,}   （其中缓存命中 {t['cached']:,}）")
        print(f"  输出 token: {t['completion']:,}")
        print(f"  合计 token: {t['prompt'] + t['completion']:,}")
        avg = (t["prompt"] + t["completion"]) / t["calls"]
        print(f"  单次平均: {avg:.0f} token")
        print(f"  估算花费: {t['cost']:.4f} 元")
        print(f"  缓存命中率: {(t['cached'] / t['prompt'] * 100) if t['prompt'] else 0:.1f}%")

        print("\n  按天:")
        for day in sorted(s["by_day"]):
            d = s["by_day"][day]
            print(f"    {day}  {d['calls']:>4} 次  "
                  f"tok {d['prompt'] + d['completion']:>7,}  "
                  f"¥{d['cost']:.4f}")

    print("\n" + "=" * 62)
    print("DeepSeek 账户余额")
    print("=" * 62)
    cfg = LLMConfig.load()
    spec = dict(PROVIDERS.get("deepseek", {}))
    spec.update(cfg.overrides.get("deepseek", {}))
    key = resolve_key(spec.get("key_env", ""), spec.get("api_key", ""))
    if not key:
        print("  未配置 deepseek key")
    else:
        try:
            r = requests.get("https://api.deepseek.com/user/balance",
                             headers={"Authorization": "Bearer " + key}, timeout=30)
            if r.status_code != 200:
                print(f"  查询失败 HTTP {r.status_code}: {r.text[:120]}")
            else:
                d = r.json()
                print(f"  可用: {d.get('is_available')}")
                for b in d.get("balance_infos", []):
                    print(f"  {b.get('currency')} 余额: {b.get('total_balance')}"
                          f"  （充值 {b.get('topped_up_balance')} / 赠送 {b.get('granted_balance')}）")
                try:
                    bal = float(d["balance_infos"][0]["total_balance"])
                    if t["calls"]:
                        per_call = t["cost"] / t["calls"]
                        print(f"\n  按实测单次 ¥{per_call:.6f} 估算:")
                        print(f"    余额还够约 {int(bal / per_call):,} 次调用")
                        for rate in (20, 50, 100, 200):
                            daily = per_call * rate
                            print(f"    {rate:>3} 次/天 -> ¥{daily:.3f}/天, "
                                  f"¥{daily * 30:.2f}/月, 可撑 {bal / daily:.0f} 天")
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            print(f"  查询异常: {type(exc).__name__}: {str(exc)[:100]}")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    setup_logging(verbose=("-v" in sys.argv))

    if cmd == "test":
        return cmd_test()
    if cmd == "show":
        return cmd_show()
    if cmd == "llm":
        return cmd_llm()
    if cmd == "usage":
        return cmd_usage()
    if cmd == "llm-set":
        if len(sys.argv) < 3:
            print("用法: python run.py llm-set <提供方>[,<提供方>...]")
            return 2
        return cmd_llm_set(sys.argv[2])

    bridge = HookBridge()
    store = ContextStore()

    if cmd == "once":
        # 单次处理：把当前待回复消息处理一遍就退出（用于验证）
        ar = AutoReplier(bridge=bridge, store=store)
        msgs = bridge.poll_new()
        print("发现 %d 条新消息" % len(msgs))
        for m in msgs:
            ok, why = ar.should_reply(m)
            print("  peer=%s in=%s content=%r -> %s (%s)"
                  % (m.peer_wxid, m.is_incoming, m.content[:30],
                     "回复" if ok else "跳过", why))
            ar.handle(m)
        print("统计:", ar.stats)
        return 0

    if cmd == "proactive-once":
        # 单次主动消息（忽略空闲/时段限制，用于验证）
        pc = ProactiveSender(bridge=bridge, store=store)
        ok = pc.send_once()
        print("主动消息发送:", "成功" if ok else "失败")
        return 0 if ok else 1

    if cmd == "autoreply":
        if not acquire_single_instance("autoreply"):
            return 1
        AutoReplier(bridge=bridge, store=store).run_forever()
        return 0

    if cmd == "proactive":
        if not acquire_single_instance("proactive"):
            return 1
        ProactiveSender(bridge=bridge, store=store).run_forever()
        return 0

    if cmd == "both":
        if not acquire_single_instance("both"):
            return 1
        pc = ProactiveSender(bridge=bridge, store=store)
        th = threading.Thread(target=pc.run_forever, name="proactive", daemon=True)
        th.start()
        print("主动消息线程已启动（daemon）")
        AutoReplier(bridge=bridge, store=store).run_forever()
        return 0

    print("未知命令:", cmd)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
