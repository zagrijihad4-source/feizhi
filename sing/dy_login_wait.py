"""Open Douyin in a visible Chrome window and wait for the operator to log in.

The saved storage_state expired (search returned nothing), so a human has to
complete the login once. This keeps polling until a real sessionid appears,
then writes storage_state.json and exits on its own.
"""
import json
import os
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "douyin")
STATE = os.path.join(OUT, "storage_state.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MAX_WAIT = 600          # seconds


def logged_in(ctx):
    for c in ctx.cookies():
        if c.get("name") == "sessionid" and c.get("value") and len(c["value"]) > 10:
            return True
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STATE):
        os.replace(STATE, STATE + ".bak")
        print("old state backed up ->", STATE + ".bak")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False,
                                    args=["--mute-audio", "--start-maximized"])
        ctx = browser.new_context(no_viewport=True, user_agent=UA)
        page = ctx.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=90000)
        print("browser opened, waiting for login (up to %d s) ..." % MAX_WAIT, flush=True)

        t0 = time.time()
        ok = False
        while time.time() - t0 < MAX_WAIT:
            if logged_in(ctx):
                ok = True
                break
            time.sleep(3)

        if ok:
            time.sleep(2)
            ctx.storage_state(path=STATE)
            n = len(json.load(open(STATE, encoding="utf-8")).get("cookies", []))
            print("LOGIN OK  cookies=%d  saved %s" % (n, STATE), flush=True)
            page.wait_for_timeout(1500)
        else:
            print("TIMEOUT: no sessionid after %d s" % MAX_WAIT, flush=True)
        browser.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
