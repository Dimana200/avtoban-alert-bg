#!/usr/bin/env python3
"""Air quality for every municipality -> site/air.json (every 3 hours).
Source: Copernicus Atmosphere Monitoring Service (CAMS) European air quality forecast, via Open-Meteo (CC BY 4.0).
This is a model (forecast) for the municipality centre, not a measurement at a station.
European Air Quality Index (EEA): 0-20 good, 20-40 fair, 40-60 moderate, 60-80 poor, 80-100 very poor, >100 extremely poor."""
import json, os
from datetime import datetime, timezone
from common import http

HERE = os.path.dirname(os.path.abspath(__file__))
MUNIS = os.path.join(HERE, "..", "site", "munis.json")
OUT = os.path.join(HERE, "..", "site", "air.json")


def main():
    munis = json.load(open(MUNIS, encoding="utf-8"))
    out = {}
    for i in range(0, len(munis), 50):
        part = munis[i:i + 50]
        url = ("https://air-quality-api.open-meteo.com/v1/air-quality?latitude=" + ",".join(str(m["c"][0]) for m in part)
               + "&longitude=" + ",".join(str(m["c"][1]) for m in part)
               + "&current=european_aqi,pm10,pm2_5&hourly=european_aqi&forecast_days=2&timezone=Europe%2FSofia")
        js = http(url, timeout=120)
        if isinstance(js, dict):
            js = [js]
        for m, r in zip(part, js):
            cur, hr = r.get("current", {}), r.get("hourly", {})
            now = cur.get("time", "")
            nxt = [v for t, v in zip(hr.get("time", []), hr.get("european_aqi", [])) if v is not None and t >= now][:24]
            if cur.get("european_aqi") is None:
                continue
            out[m["r"] + "|" + m["n"]] = {"aqi": round(cur["european_aqi"]), "pm10": cur.get("pm10"), "pm25": cur.get("pm2_5"),
                                          "max24": round(max(nxt)) if nxt else None}
    if len(out) < 100:
        raise RuntimeError(f"air quality for only {len(out)} municipalities")
    json.dump({"source": "Copernicus CAMS / Open-Meteo", "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "m": out},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    worst = sorted(out.items(), key=lambda kv: -kv[1]["aqi"])[:5]
    print(f"air quality: {len(out)} municipalities; worst now {[(k, v['aqi']) for k, v in worst]}")


if __name__ == "__main__":
    main()
