import json, sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 411, "height": 800}, device_scale_factor=2, is_mobile=True, has_touch=True,
                        geolocation={"latitude": 42.1354, "longitude": 24.7453}, permissions=["geolocation"])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("https://dimana200.github.io/avtoban-alert-bg/?app=1&nocache=%d" % __import__("time").time(), wait_until="networkidle")
    pg.wait_for_timeout(6000)
    r = pg.evaluate("""() => { const i = document.querySelector('.me-arrow img'); const st = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules].map(r => r.cssText) } catch (e) { return [] } }).filter(t => t.includes('me-arrow')); return {found: !!i, rect: i && i.getBoundingClientRect().toJSON(), css: st, html: document.documentElement.className} }""")
    print(json.dumps(r, ensure_ascii=False)[:1500]); print("errors:", errs[:5])
    pg.screenshot(path="arrow.png"); b.close()
