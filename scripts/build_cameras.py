#!/usr/bin/env python3
"""Stationary speed cameras for the app and the map -> site/cameras.json.

Sources (both free to reuse):
  - OpenStreetMap: highway=speed_camera nodes and the "device" members of enforcement=maxspeed relations (ODbL);
  - Столична община, map „Безопасност СО - 2025“: places where speed cameras are being designed (data/cameras_sofia_2025.tsv).
Average-speed cameras of BG TOLL are in avgspeed.json, not here.
"""
import json, os, re
from build_roads import fetch, AREA
from common import km

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "site", "cameras.json")
SOFIA = os.path.join(HERE, "..", "data", "cameras_sofia_2025.tsv")


def num(v):
    m = re.match(r"\d+", v or "")
    return int(m.group(0)) if m else 0


def main():
    cams = []
    nodes = {e["id"]: e for e in fetch(AREA + 'node["highway"="speed_camera"](area.a);out;')}
    for e in nodes.values():
        t = e.get("tags", {})
        cams.append({"lat": round(e["lat"], 6), "lon": round(e["lon"], 6), "limit": num(t.get("maxspeed")), "src": "osm"})
    # enforcement relations: the device node is the camera, maxspeed is on the relation
    rels = fetch(AREA + 'rel["enforcement"="maxspeed"](area.a);out body;')
    dev_ids = {m["ref"]: num(r.get("tags", {}).get("maxspeed")) for r in rels for m in r.get("members", [])
               if m.get("type") == "node" and m.get("role") == "device"}
    if dev_ids:
        for e in fetch("node(id:" + ",".join(map(str, dev_ids)) + ");out;"):
            cams.append({"lat": round(e["lat"], 6), "lon": round(e["lon"], 6), "limit": dev_ids[e["id"]], "src": "osm"})
    for line in open(SOFIA, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        lon, lat, name = line.rstrip("\n").split("\t")
        cams.append({"lat": float(lat), "lon": float(lon), "limit": 0, "src": "sofia", "name": name})
    # the same camera from two sources: keep one (the one with a speed limit)
    out = []
    for c in sorted(cams, key=lambda c: -c["limit"]):
        if all(km((c["lat"], c["lon"]), (o["lat"], o["lon"])) > 0.03 for o in out):
            out.append(c)
    json.dump({"cameras": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"cameras: {len(out)} (osm {sum(c['src'] == 'osm' for c in out)}, sofia {sum(c['src'] == 'sofia' for c in out)})")


if __name__ == "__main__":
    main()
