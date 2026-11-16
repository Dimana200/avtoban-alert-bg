"""UI check of the map in app mode on a phone: layer chooser, kept choice, tap on a road opens its popup."""
import json, os, sys
from playwright.sync_api import sync_playwright

SITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")
roads = json.load(open(os.path.join(SITE, "roads.json"), encoding="utf-8"))
cells = [p["id"] for p in roads["points"] if abs(p["lat"] - 42.15) < 0.25 and abs(p["lon"] - 24.75) < 0.35]
json.dump({"updated": "2026-11-14T00:00:00Z", "warnings": [], "points": {c: [{"type": "nimhrain", "level": 2, "value": {"s": "Пловдив"}}] for c in cells}},
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
    # new layers: АПИ events handed over by the app, rivers, fires, air
    pg.evaluate("() => { map.setView([42.7, 25.3], 7); return 1; }")
    pg.wait_for_timeout(1500)
    nb = pg.locator(".leaflet-marker-icon").count()
    pg.evaluate("""() => apiEvents([{lat: 42.3, lon: 24.8, type: 'Accident', name: 'катастрофа', text: 'ПТП на АМ Тракия', set: 'danger&c=d01'},
                                    {lat: 43.087, lon: 25.648, type: 'Roadworks', name: 'ремонт и ограничено движение', text: 'В.Търново - Г.Оряховица', set: 'danger&c=d01'}], Date.now())""")
    pg.wait_for_timeout(500)
    na = pg.locator(".leaflet-marker-icon").count()
    pg.locator(".lyr-btn").tap(); pg.wait_for_timeout(300)
    boxes = pg.locator(".lyr-box input").count()
    pg.screenshot(path=out + "/5-chooser-all.png")
    layers = pg.evaluate("() => ({river: !!LAYERS.river && LAYERS.river.getLayers().length, fire: !!LAYERS.fire && LAYERS.fire.getLayers().length})")
    pg.locator('input[data-l="api"]').tap(); pg.wait_for_timeout(400)
    nc = pg.locator(".leaflet-marker-icon").count()
    pg.locator('input[data-l="air"]').tap(); pg.wait_for_timeout(5000)
    air = pg.evaluate("() => !!LAYERS.air && LAYERS.air.getLayers().length")
    pg.locator(".lyr-btn").tap(); pg.wait_for_timeout(300)
    pg.screenshot(path=out + "/6-air.png")
    print(f"chooser boxes {boxes}; markers {nb} -> with АПИ {na} -> АПИ hidden {nc}; rivers/fires {layers}; air municipalities {air}")
    ok &= boxes == 9 and na == nb + 2 and nc == nb and layers["river"] and air and air > 100
    # small map, large text: the chooser must scroll inside the map and the last box must be reachable
    pg2 = ctx.new_page()
    pg2.set_viewport_size({"width": 412, "height": 640})
    pg2.goto("http://localhost:8000/index.html")
    pg2.wait_for_timeout(4000)
    pg2.evaluate("() => { document.documentElement.style.fontSize = '130%'; document.querySelector('.lyr-box').style.fontSize = '19px'; return 1; }")
    pg2.locator(".lyr-btn").tap(); pg2.wait_for_timeout(300)
    fitb = pg2.evaluate("""() => { var m = map.getContainer().getBoundingClientRect(), b = document.querySelector('.lyr-box'), r = b.getBoundingClientRect();
        return {inside: r.bottom <= m.bottom + 1, scrolls: b.scrollHeight > b.clientHeight}; }""")
    last = pg2.locator('input[data-l="air"]')
    last.scroll_into_view_if_needed(); pg2.wait_for_timeout(300)
    before = pg2.evaluate("() => SHOW.air")
    last.tap(); pg2.wait_for_timeout(300)
    got = pg2.evaluate("() => SHOW.air") != before
    pg2.screenshot(path=out + "/11-small-chooser.png")
    print("small map chooser:", fitb, "last box tapped:", got)
    ok &= fitb["inside"] and got
    pg2.locator('input[data-l="air"]').tap()      # back off, so the rest of the test is unchanged
    pg2.close()
    # drive view: zoom by kind of road, car in the lower part, finger pauses it for 10 s
    def drive(lat, lon, v, h, lim, n=7):
        for i in range(n):
            pg.evaluate(f"() => {{ drive({lat} + {i} * 0.0003, {lon}, {v}, {h}, {lim}); return 1; }}")
            pg.wait_for_timeout(1000)
        return pg.evaluate("() => map.getZoom()")
    z_town = drive(42.1435, 24.7495, 40, 0, 50)
    north = pg.evaluate("() => { var q = map.latLngToContainerPoint(meMark.getLatLng()); return [Math.round(q.x), Math.round(q.y)]; }")
    pg.screenshot(path=out + "/7-drive-town.png")
    z_road = drive(42.20, 24.90, 85, 90, 90)
    z_mw = drive(42.25, 25.10, 130, 90, 140)
    pg.screenshot(path=out + "/8-drive-motorway.png")
    # heading east (90): a point 1 km east of the car must be straight above it on the screen
    rot = pg.evaluate("""() => { var c = meMark.getLatLng(), a = map.latLngToContainerPoint(c), e = map.latLngToContainerPoint([c.lat, c.lng + 0.0123]);
        return {rotate: canRotate(), bearing: map.getBearing ? map.getBearing() : null, dx: Math.round(e.x - a.x), dy: Math.round(e.y - a.y), car: [Math.round(a.x), Math.round(a.y)]}; }""")
    print("rotation:", rot)
    ok &= rot["rotate"] and abs(rot["dx"]) < 15 and rot["dy"] < -60 and rot["car"][1] > 839 * 0.6
    below = pg.evaluate("() => { var q = map.latLngToContainerPoint(meMark.getLatLng()); return [Math.round(q.x), Math.round(q.y), map.getSize().x, map.getSize().y]; }")
    # zoom in by hand while driving: map stays, "Центрирай" appears; pressing it goes back to the car
    pg.locator(".leaflet-control-zoom-in").tap(); pg.wait_for_timeout(700)
    z_hand = pg.evaluate("() => map.getZoom()")
    drive(42.25, 25.12, 130, 90, 140, n=3)
    stay = pg.evaluate("() => [map.getZoom(), follow, !document.querySelector('.ctr-btn').hidden]")
    pg.screenshot(path=out + "/9a-zoomed-by-hand.png")
    pg.locator(".ctr-btn").tap(); pg.wait_for_timeout(1200)
    back = pg.evaluate("() => [map.getZoom(), follow, !document.querySelector('.ctr-btn').hidden]")
    print(f"zoom by hand {z_hand}: after 3 s of driving {stay}; after Центрирай {back}")
    ok &= stay == [14, False, True] and back == [13, True, False]
    pg.evaluate("() => { drive(null); return 1; }"); pg.wait_for_timeout(800)
    pg.screenshot(path=out + "/9-after-stop.png")
    # a road can still be tapped on the turned map
    pg.evaluate("() => { drive(42.15, 24.75, 60, 45, 90); return 1; }"); pg.wait_for_timeout(600)
    pg.evaluate("() => { drive(42.15, 24.75, 60, 45, 90); return 1; }"); pg.wait_for_timeout(600)
    xy2 = pg.evaluate("""() => { var c = Object.keys(haz.points)[0]; var seg = roads.segments.find(s => s.p === c);
        var ll = seg.c[Math.floor(seg.c.length / 2)]; map.setView(ll, map.getZoom(), {animate: false}); var q = map.latLngToContainerPoint(ll); var r = document.getElementById('map').getBoundingClientRect();
        return [r.left + q.x, r.top + q.y]; }""")
    pg.evaluate("() => { follow = false; return 1; }")
    pg.mouse.click(1, 1)
    pg.touchscreen.tap(xy2[0], xy2[1]); pg.wait_for_timeout(800)
    tapped = pg.locator(".leaflet-popup-content").count()
    pg.screenshot(path=out + "/10-turned-tap.png")
    print("tap on road with the map turned -> popup:", tapped)
    ok &= tapped >= 1
    pg.evaluate("() => { drive(null); return 1; }"); pg.wait_for_timeout(800)
    z_off = pg.evaluate("() => map.getZoom()")
    print("heading north: car at", north)
    ok &= north[1] > below[3] * 0.65 and north[1] < below[3] * 0.85
    print(f"drive zoom town {z_town}, open road {z_road}, motorway {z_mw}; car at {below} (heading east -> car left of centre); after stop {z_off}")
    ok &= z_town == 15 and z_road == 14 and z_mw == 13 and z_off == 10
    b.close()
print("RESULT", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
