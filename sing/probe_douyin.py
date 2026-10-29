"""Probe a Douyin share page for a directly downloadable video URL."""
import re
import sys

import requests

H = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                   "Mobile/15E148 Safari/604.1"),
    "Referer": "https://www.iesdouyin.com/",
}

aid = sys.argv[1]
url = "https://www.iesdouyin.com/share/video/%s/" % aid
r = requests.get(url, headers=H, timeout=25)
t = r.text
print("status", r.status_code, "len", len(t))

for pat in ["play_addr", "playApi", r"\.mp4", "video_id", "_ROUTER_DATA", "RENDER_DATA", "aweme_detail", "playAddr"]:
    print("%-14s %d" % (pat, len(re.findall(pat, t))))

hits = re.findall(r"https?://[^\s\"'\\]+\.mp4[^\s\"'\\]*", t)
print("mp4 urls:", len(hits))
for h in hits[:5]:
    print("  ", h[:150])

# also look for the json blob that usually holds play_addr.url_list
m = re.search(r"_ROUTER_DATA\s*=\s*(\{.*?\});?\s*</script>", t, re.S)
print("router_data block:", bool(m))
if m:
    blob = m.group(1)
    urls = re.findall(r"https?:\\?/\\?/[^\"']+?\.mp4[^\"']*", blob)
    print("router mp4 hits:", len(urls))
    for u in urls[:5]:
        print("  ", u.replace("\\u002F", "/").replace("\\/", "/")[:150])
