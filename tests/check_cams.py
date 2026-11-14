"""Temporary: which cameras of a list (town, road, limit) have one of ours nearby on that road."""
import json, sys, os, re
sys.path.insert(0, "scripts")
from build_roads import fetch, AREA
from build_avgspeed import near_road, km
rows = [l.rstrip("\n").split("\t") for l in open("tests/check_list.tsv", encoding="utf-8") if l.strip()]
cams = [c for c in json.load(open("site/cameras.json"))["cameras"] if c["t"] == "speed"]
roads = json.load(open("site/roads.json"))
lines = {}
for s in roads["segments"]:
    lines.setdefault(s["r"], []).append([tuple(c) for c in s["c"]])
names = sorted({re.sub(r"\s*\(.*", "", r[0]) for r in rows})
rx = "|".join(re.escape(n) for n in names)
places = {}
for e in fetch(AREA + f'node["place"~"city|town|village"]["name"~"^({rx})$"](area.a);out;'):
    places.setdefault(e["tags"]["name"], []).append((e["lat"], e["lon"], e["tags"]["place"]))
found = 0
for town, addr, lim in rows:
    n = re.sub(r"\s*\(.*", "", town)
    m = re.search(r"\b(I{1,3}-\d+|АМ „(\w+)“)", addr)
    ref = None
    if m:
        ref = {"Тракия": "A1", "Хемус": "A2"}.get(m.group(2), None) if m.group(2) else m.group(1)
    cands = places.get(n, [])
    if ref and cands:
        cands = sorted(cands, key=lambda p: near_road(p[:2], lines.get(ref, []))[0])
    if not cands:
        print(f"NOPLACE {town} | {addr}"); continue
    p = cands[0]
    r = 8 if p[2] == "city" else 3.5
    near = [c for c in cams if km(p[:2], (c["lat"], c["lon"])) <= r]
    if ref and lines.get(ref):
        near = [c for c in near if near_road((c["lat"], c["lon"]), lines[ref])[0] < 150]
    ok = bool(near)
    found += ok
    print(f"{'HAVE' if ok else 'MISS'} {town} | {addr} | {lim} | ours: {[(c['src'], c['limit']) for c in near][:4]}")
print(f"RESULT {found} of {len(rows)} have a camera of ours nearby")
