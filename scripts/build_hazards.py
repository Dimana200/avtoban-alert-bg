#!/usr/bin/env python3
"""Check weather on every motorway section for now + next 3 hours and write site/hazards.json.

Levels follow the European warning colours: 0 none, 1 yellow, 2 orange, 3 red.
Weather: Open-Meteo (free for non-commercial use, CC-BY 4.0). Official warnings: Meteoalarm (NIMH data).
"""
import json, os, re, sys, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from common import http

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site")
API = "https://api.open-meteo.com/v1/forecast"
VARS = "visibility,wind_gusts_10m,snowfall,temperature_2m,precipitation,weather_code"
METEOALARM = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-bulgaria"
BATCH = 50


def rate(h):
    """Hazards for one forecast hour -> list of (type, level, value)."""
    out = []
    vis, gust, snow = h.get("visibility"), h.get("wind_gusts_10m"), h.get("snowfall")
    temp, prec, code = h.get("temperature_2m"), h.get("precipitation") or 0, h.get("weather_code")
    if vis is not None:
        lv = 3 if vis < 100 else 2 if vis < 200 else 1 if vis < 500 else 0
        if lv: out.append(("fog", lv, round(vis)))
    if gust is not None:
        lv = 3 if gust >= 90 else 2 if gust >= 70 else 1 if gust >= 55 else 0
        if lv: out.append(("wind", lv, round(gust)))
    if snow:
        lv = 3 if snow >= 2 else 2 if snow >= 0.5 else 1
        out.append(("snow", lv, round(snow, 1)))
    if code in (56, 57, 66, 67):
        out.append(("ice", 3, temp))
    elif temp is not None and prec > 0 and -6 <= temp <= 1 and not snow:
        out.append(("ice", 2, temp))
    if code in (95, 96, 99):
        out.append(("storm", 2, prec))
    elif prec >= 5:
        out.append(("rain", 2 if prec >= 10 else 1, prec))
    return out


def worst(hours):
    """hours: list of (time, dict). Keep the worst level per hazard type, with its first time."""
    best = {}
    for t, h in hours:
        for typ, lv, val in rate(h):
            if typ not in best or lv > best[typ]["level"]:
                best[typ] = {"type": typ, "level": lv, "value": val, "at": t}
    return sorted(best.values(), key=lambda x: -x["level"])


def weather(points):
    res = {}
    for i in range(0, len(points), BATCH):
        chunk = points[i:i + BATCH]
        q = {"latitude": ",".join(str(p["lat"]) for p in chunk), "longitude": ",".join(str(p["lon"]) for p in chunk),
             "hourly": VARS, "forecast_hours": 4, "timezone": "Europe/Sofia", "wind_speed_unit": "kmh"}
        js = http(API + "?" + urllib.parse.urlencode(q), timeout=60)
        if isinstance(js, dict):
            js = [js]
        for p, loc in zip(chunk, js):
            hr = loc["hourly"]
            hours = [(hr["time"][k], {v: hr[v][k] for v in VARS.split(",")}) for k in range(len(hr["time"]))]
            res[p["id"]] = worst(hours)
    return res


def warnings():
    """Active official warnings for Bulgaria from Meteoalarm (yellow and above). Never fatal."""
    try:
        root = ET.fromstring(http(METEOALARM, timeout=60, raw=True))
    except Exception as e:  # noqa: BLE001
        print("meteoalarm unavailable:", e)
        return None
    now, out = datetime.now(timezone.utc), []
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        f = {}
        for el in entry:
            f[el.tag.split("}")[-1]] = (el.text or "").strip()
        lvl = re.match(r"(\d)", f.get("awareness_level", ""))
        lvl = int(lvl.group(1)) - 1 if lvl else 0          # Meteoalarm: 2 yellow, 3 orange, 4 red
        exp = f.get("expires", "")
        try:
            if exp and datetime.fromisoformat(exp.replace("Z", "+00:00")) < now:
                continue
        except ValueError:
            pass
        if lvl >= 1:
            out.append({"level": min(lvl, 3), "event": f.get("event") or f.get("title", ""),
                        "area": f.get("areaDesc", ""), "type": f.get("awareness_type", ""),
                        "from": f.get("onset", ""), "to": exp})
    return sorted(out, key=lambda w: (-w["level"], w["area"]))


def main():
    roads = json.load(open(os.path.join(ROOT, "roads.json"), encoding="utf-8"))
    pts = roads["points"]
    res = weather(pts)
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "points": {k: v for k, v in res.items() if v}, "checked": len(res), "warnings": warnings()}
    json.dump(out, open(os.path.join(ROOT, "hazards.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    lv = [max(h["level"] for h in v) for v in out["points"].values()]
    print(f"checked {len(res)} sections; yellow {lv.count(1)}, orange {lv.count(2)}, red {lv.count(3)}; "
          f"official warnings: {None if out['warnings'] is None else len(out['warnings'])}")


if __name__ == "__main__":
    main()
