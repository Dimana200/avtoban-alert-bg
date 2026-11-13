#!/usr/bin/env python3
"""Municipality boundaries for "Моят район" -> site/munis.json (rarely changes; run by hand).
[{n: name as NIMH writes it (normalised), r: region code (first 3 letters of the OSM ref, e.g. PDV), c: [lat, lon], w: [[lat, lon, lat, lon, ...], ...]}]
The app finds its municipality by counting crossings of the boundary lines (no ring assembly needed)."""
import json, os, re, time
from build_roads import fetch, AREA, simplify
import nimh_warn

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "munis.json")


def main():
    ids = [e["id"] for e in fetch(AREA + 'rel["boundary"="administrative"]["admin_level"="5"](area.a);out ids;') if e.get("type") == "relation"]
    out, no_ref = [], []
    for i in range(0, len(ids), 25):
        for el in fetch("rel(id:" + ",".join(map(str, ids[i:i + 25])) + ");out geom;"):
            t = el.get("tags", {})
            ref = (t.get("ref") or "").upper()
            ways, la, lo, n = [], 0, 0, 0
            for m in el.get("members", []):
                g = m.get("geometry") or []
                if m.get("role") in ("outer", "inner") and len(g) > 1:
                    pts = simplify([(p["lat"], p["lon"]) for p in g], 250)
                    ways.append([round(v, 4) for p in pts for v in p])
                    for p in pts:
                        la += p[0]; lo += p[1]; n += 1
            if not ways:
                continue
            if not re.match(r"^[A-Z]{3}", ref):
                no_ref.append(t.get("name"))
            out.append({"n": nimh_warn.norm(t.get("name", "")), "r": ref[:3], "c": [round(la / n, 3), round(lo / n, 3)], "w": ways})
        time.sleep(5)
    s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    open(OUT, "w", encoding="utf-8").write(s)
    print(f"municipalities {len(out)} of {len(ids)}; without a region ref: {no_ref}; file {len(s) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
