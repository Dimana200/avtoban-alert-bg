#!/usr/bin/env python3
"""Download Bulgarian motorways from OpenStreetMap and split them into ~8 km sections.

Writes site/roads.json:
  points:   [{id, ref, name, lat, lon}]   one weather sample point per section
  segments: [{p, ref, c: [[lat, lon], ...]}] drawable pieces, each tied to its section point
"""
import json, os, re, sys
from collections import defaultdict
from common import http, km

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
CELL = 0.07          # ~7-8 km grid cell -> one section per cell and motorway
NAMES = {"A1": "Тракия", "A2": "Хемус", "A3": "Струма", "A4": "Марица", "A5": "Черно море", "A6": "Европа"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "roads.json")
Q = ('[out:json][timeout:300];area["ISO3166-1"="BG"][admin_level=2]->.a;'
     '(way["highway"="motorway"](area.a);node["place"~"^(city|town|village)$"](area.a););out geom tags;')


def norm_ref(t):
    ref = (t.get("ref") or "").replace("А", "A").replace(" ", "").upper()   # Cyrillic А -> Latin A
    m = re.search(r"A\d", ref)
    return m.group(0) if m else None


def nearest_place(places, p):
    """Name of a town within 15 km (preferred) or else the nearest village, for 'near Yambol'-style labels."""
    best, best_d = "", 1e9
    for lat, lon, name, w in places:
        if abs(lat - p[0]) > 0.3 or abs(lon - p[1]) > 0.4:
            continue
        d = km(p, (lat, lon)) / (1 + (w >= 2) * 2)   # towns count as 3x closer than villages
        if d < best_d:
            best, best_d = name, d
    return best


def along(cs):
    """Order section centres along the road: start at one end, then always step to the nearest unvisited."""
    if not cs:
        return []
    c0 = (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))
    a = max(cs, key=lambda c: km(c, c0))            # one end of the road
    start = max(cs, key=lambda c: km(c, a))          # the other end, farthest from it
    order, left = [start], [c for c in cs if c is not start]
    while left:
        nxt = min(left, key=lambda c: km(c, order[-1]))
        order.append(nxt)
        left.remove(nxt)
    if (order[0][1], -order[0][0]) > (order[-1][1], -order[-1][0]):   # west/north end first
        order.reverse()
    return order


def build(js):
    lines, places = defaultdict(list), []
    for el in js.get("elements", []):
        t = el.get("tags", {})
        if el.get("type") == "node" and t.get("name"):
            w = {"city": 3, "town": 2, "village": 1}.get(t.get("place"), 0)
            places.append((el["lat"], el["lon"], t.get("name"), w))
            continue
        if t.get("highway") != "motorway":
            continue
        ref = norm_ref(t)
        if not ref or not el.get("geometry"):
            continue
        lines[ref].append([(g["lat"], g["lon"]) for g in el["geometry"]])
    points, segments = [], []
    for ref in sorted(lines):
        cells = defaultdict(list)
        for ln in lines[ref]:
            for p in ln:
                cells[(int(p[0] // CELL), int(p[1] // CELL))].append(p)
        cents = [(sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)) for ps in cells.values()]
        pts = []
        for i, (lat, lon) in enumerate(along(cents)):
            pid = f"{ref}-{i}"
            pts.append((pid, (lat, lon)))
            near = nearest_place(places, (lat, lon))
            points.append({"id": pid, "ref": ref, "name": NAMES.get(ref, ref), "near": near,
                           "lat": round(lat, 4), "lon": round(lon, 4)})
        for ln in lines[ref]:
            cur, cur_p = [], None
            for a, b in zip(ln, ln[1:]):
                mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                pid = min(pts, key=lambda q: km(mid, q[1]))[0]
                if pid != cur_p and cur:
                    segments.append({"p": cur_p, "ref": ref, "c": cur})
                    cur = [cur[-1]]
                cur_p = pid
                if not cur:
                    cur = [[round(a[0], 4), round(a[1], 4)]]
                cur.append([round(b[0], 4), round(b[1], 4)])
            if cur and len(cur) > 1:
                segments.append({"p": cur_p, "ref": ref, "c": cur})
    return {"points": points, "segments": segments}


def main():
    js = None
    for ep in OVERPASS:
        try:
            js = http(ep, {"data": Q}, timeout=400, tries=2)
            if re.search(r"error|timed out", js.get("remark", ""), re.I):
                raise RuntimeError(js["remark"])
            break
        except Exception as e:  # noqa: BLE001
            print("failed", ep, e)
    if not js:
        sys.exit(1)
    out = build(js)
    if len(out["points"]) < 20:
        print("too few sections, keeping old file:", len(out["points"])); sys.exit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    by = defaultdict(int)
    for p in out["points"]:
        by[p["ref"]] += 1
    print("sections per motorway:", dict(by), "segments:", len(out["segments"]))


if __name__ == "__main__":
    main()
