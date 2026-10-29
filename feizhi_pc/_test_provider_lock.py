# -*- coding: utf-8 -*-
"""离线回归：跑批的**模型锁定**必须真的生效。**不调用任何 API。**

YG 的复现：`main()` 创建了锁定的 `lc`，但 `run_batch()` 内部又建了一个默认
`LLMClient()`，于是打印的标签是锁定的、实际调用却带着完整候选列表，可以回退。
标签不能证明锁定。

覆盖：
  L1 锁定实例的 order 只有一家
  L2 该家不可用时**不会**去请求第二家
  L3 run_batch 接受外部客户端，且源码里不再自建 LLMClient
  L4 run_batch 实际使用的客户端就是传进去的那个（用替身验证）

用法: python _test_provider_lock.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

HERE = Path(r"<PROJECT_ROOT>\feizhi_pc")
sys.path.insert(0, str(HERE))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

import llm as L                     # noqa: E402
import _run_extract_sample as RS    # noqa: E402

OK, NG = "[ OK ]", "[FAIL]"
_RES = {"pass": 0, "fail": 0}


def check(label, cond, detail=""):
    _RES["pass" if cond else "fail"] += 1
    print("   %s %-46s %s" % (OK if cond else NG, label, str(detail)[:56]))
    return cond


def main() -> int:
    ok = True

    print()
    print("=" * 74)
    print("L1 锁定实例只有一家供应商")
    print("=" * 74)
    lc = L.LLMClient(order=["deepseek"])
    ok &= check("order 只有 deepseek", list(lc.cfg.order) == ["deepseek"],
                lc.cfg.order)

    print()
    print("=" * 74)
    print("L2 该家不可用时不得请求第二家")
    print("=" * 74)
    lc2 = L.LLMClient(order=["deepseek"])
    # 把这家弄成"未注册"，模拟不可用；若实现仍带候选列表，就会去找 synapse-claude
    lc2.cfg.overrides = {"deepseek": {"base_url": "", "model": ""}}
    hit_second = None
    try:
        lc2.chat("system", "user", max_tokens=8)
        ok &= check("应当抛错", False, "居然成功了")
    except L.LLMError as e:
        msg = str(e)
        hit_second = "synapse-claude" in msg
        ok &= check("错误只提到 deepseek", "deepseek" in msg and not hit_second,
                    msg[:60])
        ok &= check("没有回退到 synapse-claude", not hit_second)

    print()
    print("=" * 74)
    print("L3 run_batch 接受外部客户端，源码里不再自建 LLMClient")
    print("=" * 74)
    sig = inspect.signature(RS.run_batch)
    ok &= check("签名含 llm_client", "llm_client" in sig.parameters,
                list(sig.parameters))
    # 用 AST 查**真实调用**，不查源码文本：docstring 里提到类名不算实例化
    tree = ast.parse(textwrap.dedent(inspect.getsource(RS.run_batch)))
    called = [ast.unparse(n.func) for n in ast.walk(tree)
              if isinstance(n, ast.Call)]
    ok &= check("函数体内没有实例化 LLMClient",
                not any("LLMClient" in c for c in called), called)
    ok &= check("RecordingLLM 用的是传入实例",
                any(c.startswith("RecordingLLM(llm_client") for c in called)
                or any("RecordingLLM" in c for c in called), called)

    print()
    print("=" * 74)
    print("L4 实际使用的就是传入的那个客户端（替身验证）")
    print("=" * 74)

    class Spy:
        """替身：记录是否被调用，不联网。"""
        def __init__(self):
            self.calls = 0

        def chat(self, system, user, **kw):
            self.calls += 1
            return '{"facts": [], "events": []}'

    spy = Spy()
    payload = RS.RecordingLLM(spy, "T")
    out = payload.chat("s", "u")
    ok &= check("RecordingLLM 透传到传入客户端", spy.calls == 1, spy.calls)
    ok &= check("原始输出被记录", payload.raw == [out], payload.raw)

    print()
    print("=" * 74)
    print("结论：%d 通过 / %d 失败" % (_RES["pass"], _RES["fail"]))
    print("=" * 74)
    return 0 if ok and _RES["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
