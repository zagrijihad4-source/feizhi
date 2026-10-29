"""Render the panel headlessly and save a screenshot for visual review."""
import sys
import time

from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791"
out = sys.argv[2] if len(sys.argv) > 2 else r"<PROJECT_ROOT>\tmp\panel.png"
w = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
h = int(sys.argv[4]) if len(sys.argv) > 4 else 950

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
    page.goto(url, wait_until="networkidle", timeout=60000)
    time.sleep(3.5)
    page.screenshot(path=out, full_page=False)
    # also collect console errors, they are the usual cause of a blank panel
    print("title:", page.title())
    print("saved:", out)
    b.close()
