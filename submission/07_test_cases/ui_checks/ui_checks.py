"""Browser regression checks: mobile safety visibility, pause/resume, evidence navigation."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
SAFETY = "sess_7c3b79f4a2e047e1b94c4b57bac2cb40"
results = []

def check(name, ok, detail=""):
    results.append((name, ok)); print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))

def open_page(b, width, workspace, tab=None):
    ctx = b.new_context(viewport={"width": width, "height": 812 if width < 600 else 900})
    pg = ctx.new_page()
    pg.add_init_script(f"localStorage.setItem('mindbridge:workspace','{workspace}');"
                       + (f"sessionStorage.setItem('mindbridge:tab-session','{tab}');" if tab else ""))
    pg.goto("http://localhost:5173/"); pg.wait_for_timeout(2500)
    return ctx, pg

def in_view(pg, locator):
    box = locator.bounding_box(); vh = pg.viewport_size["height"]
    return box is not None and box["y"] >= 0 and box["y"] + box["height"] <= vh, box

with sync_playwright() as p:
    b = p.chromium.launch()
    for width in (375, 1440):
        ctx, pg = open_page(b, width, "patient", SAFETY)
        alerts = pg.locator("section[role=alert]")
        ok, box = in_view(pg, pg.locator("#crisis-title"))
        check(f"{width}px safety: crisis heading visible on open without scrolling", ok, f"y={box and round(box['y'])}")
        ok, _ = in_view(pg, pg.get_by_role("link", name="Find a crisis line in your country: findahelpline.com"))
        check(f"{width}px safety: crisis line link visible on open", ok)
        check(f"{width}px safety: exactly one crisis banner", alerts.count() == 1)
        card_links = pg.locator("#confirmation-title").locator("xpath=ancestor::article").get_by_role("link").count()
        check(f"{width}px safety: confirmation card does not repeat crisis contacts", card_links == 0)
        pg.screenshot(path=str(OUT / f"safety-open-{width}.png")); ctx.close()

        ctx, pg = open_page(b, width, "patient", "demo-s5-interrupted")
        check(f"{width}px pause: paused card shown", pg.get_by_text("Paused. Your answers are saved").is_visible())
        pg.get_by_role("button", name="Continue", exact=True).click()
        focused = pg.evaluate("document.activeElement?.tagName")
        check(f"{width}px resume: Continue focuses the answer box", focused == "TEXTAREA", focused)
        pg.reload(); pg.wait_for_timeout(2000)
        check(f"{width}px pause: paused state persists after reload", pg.get_by_text("Paused. Your answers are saved").is_visible())
        pg.screenshot(path=str(OUT / f"paused-{width}.png")); ctx.close()

        ctx, pg = open_page(b, width, "clinician")
        btn = pg.get_by_role("button", name="See in conversation").first
        btn.click(); pg.wait_for_timeout(900)
        source = pg.locator("li", has=pg.get_by_text("Source", exact=True)).first
        ok, _ = in_view(pg, source) if source.count() else (False, None)
        check(f"{width}px evidence: source patient message highlighted and in view", ok)
        pg.screenshot(path=str(OUT / f"evidence-{width}.png")); ctx.close()
    b.close()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} UI checks passed")
sys.exit(1 if failed else 0)
