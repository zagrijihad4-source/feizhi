"""Open a persistent Edge profile on douyin.com, wait for the user to log in,
then persist the storage state so later scraping runs reuse the session.

Runs windowed on purpose: the user has to scan a QR code.
"""
import pathlib
import time

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(r"<PROJECT_ROOT>\sing")
PROFILE = ROOT / ".dy_profile"
OUT = ROOT / "douyin"
STATE = OUT / "storage_state.json"
LOG = OUT / "login.log"
FLAG = OUT / "login_ok.txt"


def log(msg):
    OUT.mkdir(parents=True, exist_ok=True)
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(line + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (FLAG,):
        if p.exists():
            p.unlink()
    log("=== start, profile=%s" % PROFILE)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE),
            channel="msedge",
            headless=False,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=90000)
            log("douyin.com opened")
        except Exception as exc:  # noqa: BLE001
            log("goto failed: %s" % exc)

        deadline = time.time() + 600
        logged = False
        while time.time() < deadline:
            time.sleep(3)
            try:
                jar = {c["name"]: c["value"] for c in ctx.cookies("https://www.douyin.com")}
            except Exception as exc:  # noqa: BLE001
                log("cookie read failed: %s" % exc)
                continue
            sid = jar.get("sessionid") or jar.get("sessionid_ss") or ""
            if len(sid) > 8:
                log("login detected: sessionid=%s...(len %d) cookies=%d" % (sid[:6], len(sid), len(jar)))
                logged = True
                break

        if logged:
            try:
                ctx.storage_state(path=str(STATE))
                log("storage_state -> %s" % STATE)
                FLAG.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf8")
            except Exception as exc:  # noqa: BLE001
                log("save state failed: %s" % exc)
            log("keeping window open 180s so the session settles")
            time.sleep(180)
        else:
            log("timeout: no login within 10 minutes")

        ctx.close()
    log("=== exit")


if __name__ == "__main__":
    main()
