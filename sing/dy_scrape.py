"""Scrape a Douyin creator's post list (titles, timestamps, play URLs) using
the logged-in persistent profile.

Douyin signs its web API with a_bogus, so we let the real page compute the
signature and simply capture the aweme/post responses it receives.

usage: python dy_scrape.py [max_scrolls]
"""
import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(r"<PROJECT_ROOT>\sing")
PROFILE = ROOT / ".dy_profile"
OUT = ROOT / "douyin"
POSTS = OUT / "posts.json"
LOG = OUT / "scrape.log"

SEC_UID = "MS4wLjABAAAAR1kx7Xkq66oz6ilu2f49kmDZ9bU36CO5Q3vNXkl274BIZ6Np_rZCDKgXVIr3teds"
HOME = "https://www.douyin.com/user/" + SEC_UID

KEYWORDS = ["清唱", "无伴奏", "清声", "原声", "干声", "cover", "翻唱", "纯人声", "acoustic"]

posts = {}


def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def pick_url(addr):
    if not isinstance(addr, dict):
        return ""
    urls = addr.get("url_list") or []
    return urls[0] if urls else ""


def take(item):
    if not isinstance(item, dict):
        return
    aid = str(item.get("aweme_id") or "")
    if not aid or aid in posts:
        return
    video = item.get("video") or {}
    posts[aid] = {
        "aweme_id": aid,
        "desc": (item.get("desc") or "").strip(),
        "create_time": item.get("create_time"),
        "duration_ms": video.get("duration"),
        "play": pick_url(video.get("play_addr")),
        "download": pick_url(video.get("download_addr")),
        "music": ((item.get("music") or {}).get("title") or "").strip(),
        "stats": {
            "digg": (item.get("statistics") or {}).get("digg_count"),
            "play": (item.get("statistics") or {}).get("play_count"),
        },
    }


def main():
    max_scrolls = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    if not (OUT / "login_ok.txt").exists():
        raise SystemExit("not logged in: %s missing" % (OUT / "login_ok.txt"))

    with sync_playwright() as p:
        # Prefer the saved storage_state: the persistent profile gets locked by
        # whichever process opened it, and the login script may still be alive.
        if (OUT / "storage_state.json").exists():
            browser = p.chromium.launch(
                channel="msedge",
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            ctx = browser.new_context(storage_state=str(OUT / "storage_state.json"), no_viewport=True)
            log("using storage_state")
        else:
            ctx = p.chromium.launch_persistent_context(
                str(PROFILE),
                channel="msedge",
                headless=False,
                no_viewport=True,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            )
            log("using persistent profile")

        def on_response(resp):
            u = resp.url
            if "aweme/post" not in u and "aweme/detail" not in u:
                return
            try:
                data = json.loads(resp.body().decode("utf8", "ignore"))
            except Exception:  # noqa: BLE001
                return
            n0 = len(posts)
            for it in data.get("aweme_list") or []:
                take(it)
            if "aweme_detail" in data:
                take(data["aweme_detail"])
            if len(posts) != n0:
                log("captured +%d -> %d" % (len(posts) - n0, len(posts)))

        ctx.on("response", on_response)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded", timeout=90000)
        log("home opened")
        time.sleep(5)

        stale = 0
        SCROLL_JS = """() => {
            const before = document.documentElement.scrollTop || 0;
            window.scrollTo(0, document.documentElement.scrollHeight);
            let best = null, bestH = 0;
            document.querySelectorAll('div,main,section,ul').forEach(d => {
                if (d.scrollHeight > d.clientHeight + 200 && d.clientHeight > 200) {
                    if (d.scrollHeight > bestH) { bestH = d.scrollHeight; best = d; }
                }
            });
            if (best) best.scrollTop = best.scrollHeight;
            return {
                before: before,
                after: document.documentElement.scrollTop || 0,
                container: best ? bestH : 0
            };
        }"""
        for i in range(max_scrolls):
            before = len(posts)
            try:
                info = page.evaluate(SCROLL_JS)
            except Exception as exc:  # noqa: BLE001
                log("scroll eval failed: %s" % exc)
                info = {}
            time.sleep(1.8)
            if len(posts) == before:
                stale += 1
            else:
                stale = 0
            if i % 5 == 0:
                log("scroll %d posts=%d %s" % (i, len(posts), info))
            if stale >= 14:
                log("no new posts for %d rounds, stop at scroll %d" % (stale, i))
                break

        ctx.storage_state(path=str(OUT / "storage_state.json"))

        rows = sorted(posts.values(), key=lambda r: r.get("create_time") or 0)
        POSTS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")
        log("saved %d posts -> %s" % (len(rows), POSTS))

        hits = [r for r in rows if any(k.lower() in (r["desc"] + " " + r["music"]).lower() for k in KEYWORDS)]
        log("keyword hits: %d" % len(hits))
        for r in hits[:40]:
            ts = time.strftime("%Y-%m-%d", time.localtime(r["create_time"])) if r.get("create_time") else "?"
            log("  %s %s | %s" % (ts, r["aweme_id"], r["desc"][:60]))

        ctx.close()


if __name__ == "__main__":
    main()
