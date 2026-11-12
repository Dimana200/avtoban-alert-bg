#!/usr/bin/env python3
"""Speed limits for the phone app: every road in Bulgaria with a maxspeed tag in OpenStreetMap,
plus motorways without one (140 km/h by law), cut into 0.1 x 0.1 degree tiles.

Writes site/speed/<lat*10>_<lon*10>.json  [[limit, lat1, lon1, lat2, lon2, ...], ...]
and site/speed/index.json  (list of tiles that exist).
Roads without a known limit are left out: the app stays silent there rather than guess.
"""
import json, math, os, re, shutil, sys, time
from collections import defaultdict
from build_roads import fetch, simplify

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "speed")
AREA = 'area["ISO3166-1"="BG"][admin_level=2]->.a;'
GROUPS = ["motorway|motorway_link|trunk|trunk_link", "primary|primary_link|secondary|secondary_link",
          "tertiary|tertiary_link|unclassified", "residential|living_street"]
ZONES = {"bg:urban": 50, "bg:rural": 90, "bg:motorway": 140, "bg:trunk": 120, "bg:living_street": 20, "bg:zone20": 20, "bg:zone30": 30}


def limit(t):
    v = (t.get("maxspeed") or "").strip().lower()
    if v in ZONES:
        return ZONES[v]
    m = re.fullmatch(r"(\d{2,3})(\s*km/h)?", v)
    if m:
        n = int(m.group(1))
        return n if 5 <= n <= 160 else None
    if not v and t.get("highway") == "motorway":
        return 140
    return None


def tile(p):
    return f"{math.floor(p[0] * 10)}_{math.floor(p[1] * 10)}"


def main():
    tiles, stats = defaultdict(list), defaultdict(int)
    for g in GROUPS:
        q = AREA + f'way["highway"~"^({g})$"]["maxspeed"](area.a);out geom tags;'
        if g.startswith("motorway"):
            q = AREA + f'(way["highway"~"^({g})$"]["maxspeed"](area.a);way["highway"="motorway"](area.a););out geom tags;'
        els = fetch(q)
        print(f"{g}: {len(els)} ways", flush=True)
        for el in els:
            lim = limit(el.get("tags", {}))
            geo = el.get("geometry")
            if not lim or not geo:
                continue
            stats[lim] += 1
            pts = [(x["lat"], x["lon"]) for x in geo]
            cur, cur_t = [], None
            for a, b in zip(pts, pts[1:]):
                t = tile(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
                if t != cur_t and cur:
                    tiles[cur_t].append((lim, cur))
                    cur = [cur[-1]]
                cur_t = t
                if not cur:
                    cur = [a]
                cur.append(b)
            if len(cur) > 1:
                tiles[cur_t].append((lim, cur))
        time.sleep(10)
    if sum(len(v) for v in tiles.values()) < 1000:
        print("too little data, keeping the old tiles"); sys.exit(1)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    total = 0
    for k, segs in tiles.items():
        rows = []
        for lim, pts in segs:
            pts = simplify(pts, 8)
            row = [lim]
            for p in pts:
                row += [round(p[0], 5), round(p[1], 5)]
            rows.append(row)
        s = json.dumps(rows, separators=(",", ":"))
        total += len(s)
        open(os.path.join(OUT, k + ".json"), "w").write(s)
    json.dump(sorted(tiles), open(os.path.join(OUT, "index.json"), "w"), separators=(",", ":"))
    print(f"tiles {len(tiles)}, {total / 1e6:.1f} MB; ways by limit: {dict(sorted(stats.items()))}")


if __name__ == "__main__":
    main()
