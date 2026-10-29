"""只读诊断：量化生产记忆里的「硬缺陷」。

不调用模型、不写任何状态。三类客观可判的缺陷：

  A. 正文带相对/瞬时时间词 —— 契约要求正文不含任何时间词，时间只放 time_raw。
     这类记录当初写进去是对的，但过期后正文仍然带着「明天/待会儿/还没回」，
     渲染进 prompt 时模型会当真。
  B. 瞬时状态被当成长期事实 —— 「还没回」「待会儿」这类表达天然只在一瞬间成立。
  C. 近似重复 —— 同一件事被多次复述，挤占 render 的配额。

A/B/C 全部是正则与文本相似度可判的，不含主观语义判断。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from memory import FeizhiMemory, _norm  # noqa: E402

# A: 相对时间词（含「明天/后天/昨天/前天/今天/今晚/这周/本周末/周末」等）
REL_PAT = re.compile(
    r"明天|后天|昨天|前天|今天|今晚|今早|明早|明晚|大后天|"
    r"这周|本周|下周|上周|这学期|本周末|周末|"
    r"待会|待会儿|等会儿|马上|刚才|现在")
# ★ 不含「刚刚」：「她觉得自己刚刚好」里的「刚刚好」是「恰好」义，
#   实测会被误判成时间词。「刚才」已覆盖同类时间语义。
# B: 瞬时状态表达
MOMENT_PAT = re.compile(r"还没回|没有回|没回|正在|还在|待会儿|一会儿|等下")

recs = FeizhiMemory()._view()

print("总记录 %d" % len(recs))
print()

hits_a, hits_b = [], []
for x in recs:
    t = str(x.get("text") or "")
    if x.get("archived"):
        continue
    ma = REL_PAT.findall(t)
    mb = MOMENT_PAT.findall(t)
    if ma:
        hits_a.append((x, ma))
    if mb:
        hits_b.append((x, mb))

print("=== A. 正文含相对/瞬时时间词：%d 条 ===" % len(hits_a))
for x, ma in hits_a:
    print("  %-10s kind=%-5s raw=%r  词=%s  | %s"
          % (x.get("id") or "<legacy>", x.get("kind"),
             x.get("time_raw"), "/".join(sorted(set(ma))), x.get("text")))
print()

print("=== B. 含「还没回」类瞬时状态：%d 条 ===" % len(hits_b))
for x, ma in hits_b:
    print("  %-10s kind=%-5s 词=%s | %s"
          % (x.get("id") or "<legacy>", x.get("kind"),
             "/".join(sorted(set(ma))), x.get("text")))
print()

# C: 近似重复 —— 先剥虚词，再用「短句二元组被覆盖的比例」判。
#    用 Jaccard 判不出本项目最常见的重复形态（一句是另一句的改写扩充）：
#      「<OWNER>周日没有课」vs「<OWNER>周日没课，绯栀让他别打游戏太晚」Jaccard 仅 0.20，
#      剥掉虚词后 containment 为 1.00。这是实测结论，不是猜的。
FILLER = re.compile(r"[有的了是在和也就都还又很把被给让跟向对]")


def core(s):
    return FILLER.sub("", _norm(s))


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


live = [x for x in recs if not x.get("archived")]
pairs = []
for i in range(len(live)):
    for j in range(i + 1, len(live)):
        a, b = live[i], live[j]
        ca, cb = core(str(a.get("text") or "")), core(str(b.get("text") or ""))
        if len(ca) < 4 or len(cb) < 4:
            continue
        if ca == cb:
            pairs.append((1.0, a, b, "同义"))
            continue
        ga, gb = bigrams(ca), bigrams(cb)
        cov = len(ga & gb) / min(len(ga), len(gb))
        if cov >= 0.7:
            pairs.append((cov, a, b, "覆盖"))

pairs.sort(key=lambda p: -p[0])
print("=== C. 近似重复对：%d 组（剥虚词后短句二元组覆盖率>=0.7）===" % len(pairs))
for jac, a, b, why in pairs:
    print("  %.2f %s" % (jac, why))
    print("     A %-10s | %s" % (a.get("id") or "<legacy>", a.get("text")))
    print("     B %-10s | %s" % (b.get("id") or "<legacy>", b.get("text")))
