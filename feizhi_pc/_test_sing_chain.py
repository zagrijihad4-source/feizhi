import sys, time
sys.path.insert(0, ".")
import sing

for title in ("樱花树下的约定", "沦陷"):
    t0 = time.time()
    pcm = sing.make_pcm(title, sing.DEFAULT_START, sing.CLIP_SEC)
    if pcm is None:
        print("%-10s -> 取段失败" % title); continue
    dur = pcm.stat().st_size / 32000.0
    print("%-10s -> %s  %.1fs  (%.1fs 耗时)" % (title, pcm.name, dur, time.time()-t0))
