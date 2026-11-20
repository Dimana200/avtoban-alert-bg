#!/usr/bin/env python3
"""Road sections with a concentration of accidents (УКПТП) -> site/ukptp.json.
Source: Държавна агенция „Безопасност на движението по пътищата“ (ДАБДП), sars.gov.bg, published as a GIS Cloud map
(map 2608163, layers marked exportable). The sections were identified by the Ministry of Interior from accident data and
confirmed on site by commissions under the road infrastructure safety regulation. One list per 12-month period
(1 July - 30 June); the newest period is used."""
import json, os, re
from common import http

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "ukptp.json")
API = "https://api.giscloud.com/1/"


def main():
    layers = http(API + "maps/2608163/layers.json?perpage=50", timeout=60)["data"]
    lines = [(re.search(r"(\d{4})-(\d{4})", l["name"]), l) for l in layers if l["type"] == "line" and "УКПТП" in l["name"]]
    lines = [(m, l) for m, l in lines if m]
    if not lines:
        raise RuntimeError("no УКПТП line layer on the map")
    m, layer = max(lines, key=lambda x: int(x[0].group(2)))
    period = f"01.07.{m.group(1)} – 30.06.{m.group(2)}"
    feats = http(API + f"layers/{layer['id']}/features.json?geometry=geojson&epsg=4326&perpage=5000", timeout=120)["data"]
    out = []
    for f in feats:
        g, d = f.get("__geometry") or {}, f.get("data") or {}
        parts = g.get("coordinates") or []
        if g.get("type") == "LineString":
            parts = [parts]
        elif g.get("type") != "MultiLineString":
            continue
        pts = [[round(c[1], 5), round(c[0], 5)] for part in parts for c in part]
        if not pts:
            continue
        road = (d.get("road_id") or "").replace("Ɪ", "I").replace("Ɪ", "I")      # the source uses look-alike letters
        out.append({"n": d.get("n_ukptp"), "obl": d.get("oblast", ""), "road": road,
                    "from": d.get("from_km", ""), "to": d.get("to_km", ""), "len": d.get("lentgth_m"), "c": pts})
    if len(out) < 10:
        raise RuntimeError(f"only {len(out)} УКПТП sections")
    out.sort(key=lambda s: (s["obl"], s["road"], s["from"]))
    json.dump({"source": "ДАБДП", "period": period, "sections": out}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"УКПТП {period}: {len(out)} sections, e.g. {[(s['road'], s['from'], s['obl']) for s in out[:3]]}")


if __name__ == "__main__":
    main()
