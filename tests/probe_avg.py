"""Temporary: candidates (places, km posts, toll gantries) for the 5 average-speed sections that were not placed."""
import json, re, sys
sys.path.insert(0, "scripts")
from build_roads import fetch, AREA
from build_avgspeed import near_road, km
roads = json.load(open("site/roads.json"))
lines = {}
for s in roads["segments"]:
    lines.setdefault(s["r"], []).append([tuple(c) for c in s["c"]])
SECT = [("A1", "Кръстина", 344.388, "Ветрен", 357.949), ("A6", "Илиянци", 50.427, "Чепинци", 60.705),
        ("I-5", "Обретеник", 34.704, "Тръстеник", 25.914), ("I-5", "Одяланик", 11.382, "Тръстеник", 25.914),
        ("I-5", "Казанлък", 199.527, "Ягода", 212.716)]
names = sorted({s[1] for s in SECT} | {s[3] for s in SECT})
rx = "|".join(names)
pl = {}
for e in fetch(AREA + f'nwr["name"~"^({rx})$"](area.a);out center;'):
    c = (e.get("lat") or e["center"]["lat"], e.get("lon") or e["center"]["lon"])
    pl.setdefault(e["tags"]["name"], []).append((c, e["tags"].get("place") or e["tags"].get("natural") or e["tags"].get("highway") or "?"))
posts = [((e["lat"], e["lon"]), e["tags"]["distance"]) for e in fetch(AREA + 'node["highway"="milestone"]["distance"](area.a);out;')]
gan = [(e["lat"], e["lon"]) for e in fetch(AREA + 'node["highway"="toll_gantry"](area.a);out;')]
for ref, a, ka, b, kb in SECT:
    ls = lines.get(ref, [])
    print(f"=== {ref} {a} {ka} -> {b} {kb}  len {abs(kb-ka):.2f}; road lines {len(ls)}")
    for n in (a, b):
        for c, t in pl.get(n, []):
            d = near_road(c, ls)[0]
            if d < 15000: print(f"  PLACE {n} {t} {c[0]:.5f},{c[1]:.5f} {d/1000:.1f} km from road")
    for p, d in posts:
        try: dv = float(re.sub(r"[^\d.]", "", d.replace(",", ".")))
        except ValueError: continue
        if (abs(dv - ka) < 3 or abs(dv - kb) < 3) and near_road(p, ls)[0] < 80:
            print(f"  POST {dv} {p[0]:.5f},{p[1]:.5f}")
    near = [g for g in gan if near_road(g, ls)[0] < 80 and any(km(g, c) < 12 for n in (a, b) for c, _ in pl.get(n, []))]
    for g in near:
        print(f"  GANTRY {g[0]:.5f},{g[1]:.5f}  " + " ".join(f"{n}:{min((km(g, c) for c, _ in pl.get(n, [])), default=-1):.1f}km" for n in (a, b)))
