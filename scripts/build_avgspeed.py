#!/usr/bin/env python3
"""Average-speed sections of BG TOLL (data/avgspeed_sections.tsv, copied from bgtoll.bg) placed on the map.

Each end of a section is given only as "place (km N+NNN)" on a numbered road. It is located like this:
  1. km posts (OSM highway=milestone) lying on that road: interpolate between the two posts around km N+NNN;
  2. otherwise the point of the road nearest to the named place;
  3. then snapped to the nearest toll gantry (OSM highway=toll_gantry) on the road, where the cameras are.
Writes site/avgspeed.json: [{id, road, ref, from, to, km_from, km_to, len_km, a, b, cert, limit, how}].
"""
import json, math, os, re
from build_roads import fetch, AREA

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "data", "avgspeed_sections.tsv")
ROADS = os.path.join(HERE, "..", "site", "roads.json")
OUT = os.path.join(HERE, "..", "site", "avgspeed.json")
MOTORWAYS = {"Тракия": "A1", "Хемус": "A2", "Струма": "A3", "Марица": "A4", "Черно море": "A5", "Европа": "A6"}
ON_ROAD_M = 60          # a km post or gantry this close to the road belongs to it
PLACE_ALIAS = {"яз. Дяково": "Дяково", 'Тунел "Мало Бучино"': "Мало Бучино", "м/у 18 и п.в.Илиянци": "Илиянци"}


def ref_of(road):
    m = re.search(r'"([^"]+)"', road)
    if road.startswith("АМ") and m:
        return MOTORWAYS[m.group(1)]
    return road.strip()


def xy(p, lat0):
    return (p[1] * 111320 * math.cos(math.radians(lat0)), p[0] * 111320)


def seg_dist(p, a, b):
    """metres from p to segment a-b, and the closest point."""
    lat0 = p[0]
    (px, py), (ax, ay), (bx, by) = xy(p, lat0), xy(a, lat0), xy(b, lat0)
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy), (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def near_road(p, lines):
    best = (1e12, None)
    for ln in lines:
        if abs(ln[0][0] - p[0]) > 0.5 or abs(ln[0][1] - p[1]) > 0.7:
            continue
        for a, b in zip(ln, ln[1:]):
            d = seg_dist(p, a, b)
            if d[0] < best[0]:
                best = d
    return best


def km(a, b):
    return 2 * 6371 * math.asin(math.sqrt(math.sin(math.radians(b[0] - a[0]) / 2) ** 2 +
           math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2))


def main():
    rows = [l.rstrip("\n").split("\t") for l in open(SRC, encoding="utf-8") if l.strip() and not l.startswith("#")]
    roads = json.load(open(ROADS, encoding="utf-8"))
    lines = {}
    for s in roads["segments"]:
        lines.setdefault(s["r"], []).append([tuple(c) for c in s["c"]])

    names = sorted({PLACE_ALIAS.get(r[i], r[i]) for r in rows for i in (1, 3)})
    rx = "|".join(re.escape(n) for n in names)
    places = {}
    for e in fetch(AREA + f'node["place"]["name"~"^({rx})$"](area.a);out;'):
        places.setdefault(e["tags"]["name"], []).append((e["lat"], e["lon"]))
    posts = [((e["lat"], e["lon"]), float(re.sub(r"[^\d.]", "", e["tags"]["distance"].replace(",", ".")) or -1))
             for e in fetch(AREA + 'node["highway"="milestone"]["distance"](area.a);out;')]
    gantries = [(e["lat"], e["lon"]) for e in fetch(AREA + 'node["highway"="toll_gantry"](area.a);out;')]
    print(f"places {len(places)}/{len(names)}, km posts {len(posts)}, gantries {len(gantries)}")

    cache = {}

    def locate(road, place, k):
        key = (road, place, k)
        if key in cache:
            return cache[key]
        ref, ls = ref_of(road), lines.get(ref_of(road), [])
        name = PLACE_ALIAS.get(place, place)
        # the place: of several with that name, the one nearest to the road
        cands = sorted(places.get(name, []), key=lambda p: near_road(p, ls)[0])
        pl = cands[0] if cands else None
        est, how = None, ""
        # 1. km posts on the road, near the place (other roads have their own numbering)
        mine = [(p, d) for p, d in posts if (pl is None or km(p, pl) < 25) and near_road(p, ls)[0] < ON_ROAD_M]
        lo = max((x for x in mine if x[1] <= k), key=lambda x: x[1], default=None)
        hi = min((x for x in mine if x[1] > k), key=lambda x: x[1], default=None)
        if lo and hi and hi[1] - lo[1] <= 3 and km(lo[0], hi[0]) <= 4:
            t = (k - lo[1]) / (hi[1] - lo[1])
            est = near_road((lo[0][0] + t * (hi[0][0] - lo[0][0]), lo[0][1] + t * (hi[0][1] - lo[0][1])), ls)[1]
            how = f"km posts {lo[1]:g}-{hi[1]:g}"
        elif lo or hi:
            p, d = min([x for x in (lo, hi) if x], key=lambda x: abs(x[1] - k))
            if abs(d - k) <= 1.5:
                est, how = p, f"km post {d:g}"
        # 2. the road point nearest to the place
        if est is None and pl is not None:
            d, est = near_road(pl, ls)
            how = f"place ({d / 1000:.1f} km from the road)"
        if est is None:
            cache[key] = (None, "not found")
            return cache[key]
        # 3. the camera gantry on the road closest to that point
        g = [x for x in gantries if km(x, est) < 2.0 and near_road(x, ls)[0] < ON_ROAD_M]
        if g:
            gg = min(g, key=lambda x: km(x, est))
            how += f", gantry {km(gg, est) * 1000:.0f} m away"
            est = gg
        cache[key] = ((round(est[0], 6), round(est[1], 6)), how)
        return cache[key]

    out = []
    for i, (road, f, kf, t, kt, cert) in enumerate(rows):
        kf, kt = float(kf), float(kt)
        a, ha = locate(road, f, kf)
        b, hb = locate(road, t, kt)
        ref = ref_of(road)
        length = abs(kt - kf)
        ok = a and b and 0.5 * length <= km(a, b) <= 1.15 * length + 0.3     # straight line can't be longer than the road
        print(f"{'ok ' if ok else 'BAD'} {ref:6} {f} {kf} -> {t} {kt}: {length:.1f} km, straight {km(a, b) if a and b else -1:.1f} | {ha} | {hb}")
        if not ok:
            continue
        out.append({"id": i, "road": road, "ref": ref, "from": f, "to": t, "km_from": kf, "km_to": kt,
                    "len_km": round(length, 3), "a": a, "b": b, "cert": cert == "1",
                    "limit": 140 if ref.startswith("A") else 90})
    json.dump({"source": "bgtoll.bg", "sections": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"placed {len(out)} of {len(rows)} sections")


if __name__ == "__main__":
    main()
