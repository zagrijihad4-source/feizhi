import sys
sys.path.insert(0, ".")
import tts
cases = [
    "宝宝，我在呢。刚在改稿子。听见你叫我就过来了。",
    "你就顾着打游戏，也不问问我在干嘛。",
    "真的假的！你居然还记得呀……我还以为你早忘了。",
]
for t in cases:
    sents = tts.split_sentences(t)
    print("=" * 66)
    print("原文：%s" % t)
    for i, s in enumerate(sents):
        print("   %d. speed=%.2f  %s" % (i + 1, tts.sentence_speed(s, i, len(sents)), s))
