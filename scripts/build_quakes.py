#!/usr/bin/env python3
"""Earthquakes in and around Bulgaria in the last 3 days -> site/quakes.json (every 10 minutes).
Source: EMSC, European-Mediterranean Seismological Centre (seismicportal.eu), free FDSN service."""
import json, os
from datetime import datetime, timedelta, timezone
from common import http

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "quakes.json")


def main():
    since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")
    js = http("https://www.seismicportal.eu/fdsnws/event/1/query?format=json&minlat=39.5&maxlat=46&minlon=20&maxlon=31"
              f"&minmag=2.5&starttime={since}&limit=200", timeout=60)
    out = []
    for f in js.get("features", []):
        p, c = f["properties"], f["geometry"]["coordinates"]
        out.append({"id": f.get("id") or p.get("unid"), "t": p["time"][:19] + "Z", "mag": round(float(p["mag"]), 1),
                    "lat": round(c[1], 3), "lon": round(c[0], 3), "depth": round(abs(c[2])), "place": p.get("flynn_region", "")})
    json.dump({"source": "EMSC", "quakes": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"earthquakes in the last 3 days: {len(out)}; strongest {max((q['mag'] for q in out), default=0)}")


if __name__ == "__main__":
    main()
