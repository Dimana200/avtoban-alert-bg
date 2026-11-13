"""UI check of the map in app mode on a phone: layer chooser, kept choice, tap on a road opens its popup."""
import json, os, sys
from playwright.sync_api import sync_playwright

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")
roads = json.load(open(os.path.join(SITE, "roads.json"), encoding="utf-8"))
cells = [p["id"] for p in roads["points"] if abs(p["lat"] - 42.15) < 0.25 and abs(p["lon"] - 24.75) < 0.35]
json.dump({"updated": "2026-11-14T00:00:00Z", "points": {c: [{"type": "nimhrain", "level": 2, "value": {"s": "Пловдив"}}] for c in cells}},
          open(os.path.join(SITE, "hazards.json"), "w"))
out = sys.argv[1]
ok = True
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(**pw.devices["Pixel 7"], geolocation={"latitude": 42.15, "longitude": 24.75}, permissions=["geolocation"])
    pg = ctx.new_page()
    pg.on("console", lambda m: print("console:", m.text) if m.type == "error" else None)
    pg.goto("http://localhost:8000/index.html?app=1")
    pg.wait_for_timeout(6000)
    n0 = pg.locator(".leaflet-marker-icon").count()
    pg.screenshot(path=out + "/1-start.png")
    # tap a hazard road (orange) near the position dot
    pt = pg.evaluate("""() => { var c = Object.keys(haz.points)[0], p = pts[c];
        var seg = roads.segments.find(s => s.p === c); var ll = seg.c[Math.floor(seg.c.length / 2)];
        map.setView(ll, 12); return null; }""")
    pg.wait_for_timeout(800)
    xy = pg.evaluate("""() => { var c = Object.keys(haz.points)[0]; var seg = roads.segments.find(s => s.p === c);
        var ll = seg.c[Math.floor(seg.c.length / 2)]; var q = map.latLngToContainerPoint(ll); var r = document.getElementById('map').getBoundingClientRect();
        return [r.left + q.x, r.top + q.y]; }""")
    pg.touchscreen.tap(xy[0], xy[1])
    pg.wait_for_timeout(800)
    popup = pg.locator(".leaflet-popup-content").count()
    print("tap on road -> popup:", popup, pg.locator(".leaflet-popup-content").first.inner_text()[:80] if popup else "")
    ok &= popup == 1
    pg.screenshot(path=out + "/2-road-popup.png")
    # layer chooser
    pg.locator(".lyr-btn").tap()
    pg.wait_for_timeout(300)
    pg.screenshot(path=out + "/3-chooser.png")
    for k in ("ok", "speed", "red", "avg"):
        pg.locator(f'input[data-l="{k}"]').tap()
    pg.wait_for_timeout(500)
    map_view = pg.evaluate("() => { map.setView([42.6, 25.3], 8); return 1; }")
    pg.wait_for_timeout(800)
    n1 = pg.locator(".leaflet-marker-icon").count()
    pg.screenshot(path=out + "/4-less.png")
    pg.reload(); pg.wait_for_timeout(5000)
    kept = pg.evaluate("() => [SHOW.ok, SHOW.speed, SHOW.red, SHOW.avg, SHOW.rep]")
    print(f"markers at start {n0}, after hiding cameras {n1}; kept after reload {kept}")
    ok &= n1 < n0 and kept == [False, False, False, False, True]
    b.close()
print("RESULT", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
