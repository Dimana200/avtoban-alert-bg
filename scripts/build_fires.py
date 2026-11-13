#!/usr/bin/env python3
"""Fires seen by satellites in and around Bulgaria in the last 24 hours -> site/fires.json (every 10 minutes).
Source: NASA FIRMS (Fire Information for Resource Management System), open data, no key needed for these files.
A hot spot can also be a stubble or rubbish fire or a hot factory roof; several close together are more certain.
Detections within 2 km of each other are merged into one fire."""
import csv, io, json, os
from datetime import datetime, timezone
from common import http, km

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "fires.json")
BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
FILES = ["suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_Europe_24h.csv", "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Europe_24h.csv",
         "noaa-21-viirs-c2/csv/J2_VIIRS_C2_Europe_24h.csv", "modis-c6.1/csv/MODIS_C6_1_Europe_24h.csv"]
BOX = (41.0, 44.4, 22.1, 28.9)         # Bulgaria plus about 20 km


def confident(row):
    c = (row.get("confidence") or "").strip().lower()
    if c in ("l", "low"):
        return False
    if c.isdigit():
        return int(c) >= 50           # MODIS: 0-100
    return True                       # VIIRS: n (nominal) or h (high)


def main():
    pts, ok = [], 0
    for f in FILES:
        try:
            text = http(BASE + f, raw=True, timeout=90, tries=2).decode("utf-8", "replace")
            ok += 1
        except Exception as e:  # noqa: BLE001 - one satellite missing is fine
            print("skip", f, e)
            continue
        for r in csv.DictReader(io.StringIO(text)):
            try:
                la, lo = float(r["latitude"]), float(r["longitude"])
            except (KeyError, ValueError):
                continue
            if BOX[0] <= la <= BOX[1] and BOX[2] <= lo <= BOX[3] and confident(r):
                t = f"{r['acq_date']}T{r['acq_time'].zfill(4)[:2]}:{r['acq_time'].zfill(4)[2:]}:00Z"
                pts.append((la, lo, float(r.get("frp") or 0), t))
    if ok == 0:
        raise RuntimeError("no FIRMS file could be read")
    fires = []
    for la, lo, frp, t in sorted(pts, key=lambda p: p[3]):
        near = next((f for f in fires if km((f["lat"], f["lon"]), (la, lo)) <= 2), None)
        if near:
            near["n"] += 1
            near["frp"] = round(near["frp"] + frp, 1)
            near["t"] = max(near["t"], t)
        else:
            fires.append({"lat": round(la, 4), "lon": round(lo, 4), "n": 1, "frp": round(frp, 1), "t": t})
    json.dump({"source": "NASA FIRMS", "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "fires": fires},
              open(OUT, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"fires: {len(pts)} detections from {ok} satellites -> {len(fires)} fires; 3+ detections: {sum(1 for f in fires if f['n'] >= 3)}")


if __name__ == "__main__":
    main()
