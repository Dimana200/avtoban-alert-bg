#!/usr/bin/env python3
"""Download Bulgarian motorways and class I, II and III roads from OpenStreetMap and tie them to
a weather grid of ~20 x 20 km cells.

Only roads with an official number (ref) are taken, so city streets are left out.

Writes site/roads.json:
  points:   [{id, lat, lon, near}]                one weather check per grid cell
  roads:    [{ref, cls, name, cells: [ids]}]      cells in order along the road
  segments: [{p, r, k, c: [[lat, lon], ...]}]     drawable pieces: cell id, road ref, class, coords
Classes: 0 motorway, 1 first class, 2 second class, 3 third class.
"""
import json, math, os, re, sys, time
from collections import defaultdict
from common import http, km

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
CELL_LAT, CELL_LON = 0.18, 0.25     # ~20 x 20 km at Bulgarian latitudes
SIMPLIFY_M = 40                     # drop line detail below ~40 m
MOTORWAYS = {"A1": "Тракия", "A2": "Хемус", "A3": "Струма", "A4": "Марица", "A5": "Черно море", "A6": "Европа"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "roads.json")
AREA = 'area["ISO3166-1"="BG"][admin_level=2]->.a;'
QUERIES = [
    AREA + 'way["highway"~"^(motorway|trunk|primary)$"](area.a);out geom tags;',
    AREA + 'way["highway"="secondary"]["ref"](area.a);out geom tags;',
    AREA + 'way["highway"="tertiary"]["ref"](area.a);out geom tags;',
    AREA + 'node["place"~"^(city|town|village)$"](area.a);out;',
]
MUNI_IDS = AREA + 'rel["boundary"="administrative"]["admin_level"="5"](area.a);out ids;'   # municipalities are level 5 in Bulgaria
LAT2LATIN = str.maketrans({"А": "A", "І": "I", "Ӏ": "I"})


def road_id(t):
    """(ref, class) from OSM tags, e.g. ('A1', 0), ('I-1', 1), ('II-18', 2), ('III-1006', 3)."""
    hw = t.get("highway")
    raw = (t.get("ref") or "").translate(LAT2LATIN).upper().replace(" ", "")
    raw = raw.split(";")[0]
    if hw == "motorway":
        m = re.search(r"A\d", raw)
        return (m.group(0), 0) if m else (None, None)
    m = re.match(r"^(III|II|I)-?(\d+)", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}", len(m.group(1))
    m = re.match(r"^(\d+)$", raw)          # bare number: class from road type and digit count
    if m:
        n = m.group(1)
        cls = 1 if len(n) == 1 else 2 if len(n) == 2 else 3
        return f"{'I' * cls}-{n}", cls
    if hw in ("trunk", "primary") and not raw:
        return None, None                  # unnumbered urban arterials are left out
    return None, None


def simplify(pts, tol_m=SIMPLIFY_M):
    """Douglas-Peucker on lat/lon using a local metre scale."""
    if len(pts) < 3:
        return pts
    ky = 111_320
    kx = ky * math.cos(math.radians(pts[0][0]))
    xy = [(p[1] * kx, p[0] * ky) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = xy[a], xy[b]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1, -1
        for i in range(a + 1, b):
            d = abs(dy * (xy[i][0] - x1) - dx * (xy[i][1] - y1)) / L
            if d > best:
                best, bi = d, i
        if best > tol_m:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def along(cs):
    """Order points along a road: start at one end, then always step to the nearest unvisited."""
    if len(cs) < 2:
        return list(cs)
    c0 = (sum(c[1][0] for c in cs) / len(cs), sum(c[1][1] for c in cs) / len(cs))
    a = max(cs, key=lambda c: km(c[1], c0))
    start = max(cs, key=lambda c: km(c[1], a[1]))
    order, left = [start], [c for c in cs if c is not start]
    while left:
        nxt = min(left, key=lambda c: km(c[1], order[-1][1]))
        order.append(nxt)
        left.remove(nxt)
    if (order[0][1][1], -order[0][1][0]) > (order[-1][1][1], -order[-1][1][0]):   # west/north end first
        order.reverse()
    return order


def nearest_place(places, p):
    best, best_d = "", 1e9
    for lat, lon, name, w in places:
        if abs(lat - p[0]) > 0.3 or abs(lon - p[1]) > 0.4:
            continue
        d = km(p, (lat, lon)) / (1 + (w >= 2) * 2)   # towns count as 3x closer than villages
        if d < best_d:
            best, best_d = name, d
    return best


def municipalities(elements):
    """[(name, bbox, segments)] from admin_level 5 relations (Bulgarian municipalities); rings need no assembling because
    the point-in-polygon test below just counts crossings over all boundary segments."""
    out = []
    for el in elements:
        if el.get("type") != "relation" or el.get("tags", {}).get("admin_level") != "5":
            continue
        segs = []
        for m in el.get("members", []):
            g = m.get("geometry") or []
            if m.get("role") in ("outer", "inner") and len(g) > 1:
                segs += [((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(g, g[1:])]
        if segs:
            la = [p[0] for sg in segs for p in sg]
            lo = [p[1] for sg in segs for p in sg]
            name = el["tags"].get("name", "")
            out.append((re.sub(r"(?i)\bобщина\b", "", name).strip(), (min(la), max(la), min(lo), max(lo)), segs))
    return out


def muni_of(munis, p):
    for name, (a, b, c, d), segs in munis:
        if not (a <= p[0] <= b and c <= p[1] <= d):
            continue
        inside = False
        for (y1, x1), (y2, x2) in segs:
            if (y1 > p[0]) != (y2 > p[0]) and p[1] < x1 + (p[0] - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
        if inside:
            return name
    return ""


def cell_of(p):
    return f"{int(math.floor(p[0] / CELL_LAT))}_{int(math.floor(p[1] / CELL_LON))}"


def build(elements):
    lines, places, names = defaultdict(list), [], {}
    for el in elements:
        t = el.get("tags", {})
        if el.get("type") == "node":
            if t.get("name"):
                w = {"city": 3, "town": 2, "village": 1}.get(t.get("place"), 0)
                places.append((el["lat"], el["lon"], t["name"], w))
            continue
        ref, cls = road_id(t)
        if not ref or not el.get("geometry"):
            continue
        lines[(ref, cls)].append([(g["lat"], g["lon"]) for g in el["geometry"]])
    # a road keeps the best (lowest) class it is tagged with
    best_cls = {}
    for ref, cls in lines:
        best_cls[ref] = min(cls, best_cls.get(ref, 9))
    merged = defaultdict(list)
    for (ref, cls), ls in lines.items():
        merged[ref] += ls

    cell_nodes = defaultdict(list)
    for ls in merged.values():
        for ln in ls:
            for p in ln:
                cell_nodes[cell_of(p)].append(p)
    munis = municipalities(elements)
    points = {}
    for cid, ps in cell_nodes.items():
        lat = sum(p[0] for p in ps) / len(ps)
        lon = sum(p[1] for p in ps) / len(ps)
        # a cell can span several municipalities: keep all of them its road nodes fall in
        ms = sorted({muni_of(munis, p) for p in ps[:: max(1, len(ps) // 25)]} - {""})
        points[cid] = {"id": cid, "lat": round(lat, 4), "lon": round(lon, 4), "near": nearest_place(places, (lat, lon)), "m": ms}

    roads, segments = [], []
    for ref, ls in sorted(merged.items()):
        cls = best_cls[ref]
        cells = sorted({cell_of(p) for ln in ls for p in ln})
        ordered = [c[0] for c in along([(c, (points[c]["lat"], points[c]["lon"])) for c in cells])]
        roads.append({"ref": ref, "cls": cls, "name": MOTORWAYS.get(ref, ""), "cells": ordered})
        for ln in ls:
            # split by weather cell on the full geometry first, then thin out each piece
            cur, cur_c = [], None
            for a, b in zip(ln, ln[1:]):
                c = cell_of(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
                if c != cur_c and cur:
                    segments.append({"p": cur_c, "r": ref, "k": cls, "c": cur})
                    cur = [cur[-1]]
                cur_c = c
                if not cur:
                    cur = [a]
                cur.append(b)
            if len(cur) > 1:
                segments.append({"p": cur_c, "r": ref, "k": cls, "c": cur})
    for sg in segments:
        sg["c"] = [[round(p[0], 4), round(p[1], 4)] for p in simplify(sg["c"])]
    return {"points": sorted(points.values(), key=lambda p: p["id"]), "roads": roads, "segments": segments}


def fetch(q):
    # the public servers are often busy for a few minutes: several rounds with growing pauses
    for rnd in range(4):
        for ep in OVERPASS:
            try:
                js = http(ep, {"data": "[out:json][timeout:400];" + q}, timeout=480, tries=1)
                if re.search(r"error|timed out|out of memory", js.get("remark", ""), re.I):
                    raise RuntimeError(js["remark"])
                return js.get("elements", [])
            except Exception as e:  # noqa: BLE001
                print("   failed", ep, e, flush=True)
        time.sleep(60 * (rnd + 1))
    raise RuntimeError("all Overpass servers failed")


def municipality_elements():
    """Municipality boundaries in batches of 25 (one big query overloads the public servers)."""
    ids = [e["id"] for e in fetch(MUNI_IDS) if e.get("type") == "relation"]
    out = []
    for i in range(0, len(ids), 25):
        part = fetch("rel(id:" + ",".join(map(str, ids[i:i + 25])) + ");out geom;")
        out += part
        time.sleep(5)
    print(f"municipalities: {len(out)} of {len(ids)}", flush=True)
    return out


def main():
    elements = []
    for q in QUERIES:
        part = fetch(q)
        print(f"query {QUERIES.index(q) + 1}: {len(part)} elements", flush=True)
        elements += part
        time.sleep(5)
    try:
        elements += municipality_elements()
    except Exception as e:  # noqa: BLE001
        print("municipalities unavailable, reusing the previous file:", e)
    out = build(elements)
    if os.path.exists(OUT):                      # keep municipalities from the last good build where missing
        old = {p["id"]: p.get("m", []) for p in json.load(open(OUT, encoding="utf-8"))["points"]}
        for p in out["points"]:
            if not p["m"] and old.get(p["id"]):
                p["m"] = old[p["id"]]
    by = defaultdict(int)
    for r in out["roads"]:
        by[r["cls"]] += 1
    with_m = sum(1 for p in out["points"] if p["m"])
    print(f"cells with a municipality: {with_m} of {len(out['points'])}")
    if by[0] < 3 or by[1] < 5 or len(out["points"]) < 100 or with_m < len(out["points"]) * 0.8:
        print("too little data, keeping old file:", dict(by), len(out["points"])); sys.exit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write(s)
    print(f"roads per class {dict(sorted(by.items()))}; weather cells {len(out['points'])}; "
          f"segments {len(out['segments'])}; file {len(s) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
