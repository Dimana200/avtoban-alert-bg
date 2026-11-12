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
VARS = "wind_gusts_10m,snowfall,temperature_2m,precipitation,weather_code"
METEOALARM = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-bulgaria"
BATCH = 50


def rate(h):
    """Hazards for one forecast hour -> list of (type, level, value)."""
    out = []
    gust, snow = h.get("wind_gusts_10m"), h.get("snowfall")
    temp, prec, code = h.get("temperature_2m"), h.get("precipitation") or 0, h.get("weather_code")
    # Fog: a 30-day check against airport observations (scripts/validate_month.py) showed that the
    # model visibility gives mostly false alarms (Plovdiv 20-100 m forecast vs 2600-7000 m measured).
    # The model's fog weather code was the best rule (caught ~half of fog hours), but 3 of 4 alarms
    # were still wrong, so forecast fog is only ever "attention". Orange/red fog comes from real
    # measurements (airports) or official warnings.
    if code in (45, 48):
        out.append(("fog", 1, None))
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


AIRPORTS = {"LBSF": ("летище София", 42.695, 23.406), "LBPD": ("летище Пловдив", 42.068, 24.851),
            "LBBG": ("летище Бургас", 42.570, 27.515), "LBWN": ("летище Варна", 43.232, 27.825),
            "LBGO": ("летище Горна Оряховица", 43.152, 25.713)}
OBS_RADIUS_KM = 25


def measured_fog():
    """Latest airport visibility (METAR, newest report of the last 2 hours) under 1000 m -> {icao: (name, lat, lon, metres, time)}."""
    from validate import metar_vis
    try:
        js = http("https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode(
            {"ids": ",".join(AIRPORTS), "hours": 2, "format": "json"}), timeout=60)
    except Exception as e:  # noqa: BLE001
        print("airport observations unavailable:", e)
        return {}
    latest = {}
    for m in js:
        icao = m.get("icaoId")
        if icao in AIRPORTS and icao not in latest:          # newest report comes first
            v = metar_vis(m.get("rawOb", ""))
            if v is not None:
                latest[icao] = v
    print("airport visibility now:", latest)
    return {k: (*AIRPORTS[k], v) for k, v in latest.items() if v < 1000}


def main():
    roads = json.load(open(os.path.join(ROOT, "roads.json"), encoding="utf-8"))
    pts = roads["points"]
    res = weather(pts)
    from common import km
    import nimh
    measured = [(name, lat, lon, "fogobs", 3 if v < 200 else 2, {"v": v, "s": name})
                for name, lat, lon, v in measured_fog().values()]
    try:
        measured += [(n, la, lo, t, lv, {"v": None, "s": txt}) for n, la, lo, t, lv, txt in nimh.hazards(nimh.fetch())]
    except Exception as e:  # noqa: BLE001 - observations are a bonus, never block the forecast
        print("NIMH observations unavailable:", e)
    replaces = {"fogobs": "fog", "snowobs": "snow", "iceobs": "ice", "windobs": "wind"}
    for name, lat, lon, typ, lv, val in measured:
        for p in pts:
            if km((p["lat"], p["lon"]), (lat, lon)) > OBS_RADIUS_KM:
                continue
            cur = res.get(p["id"], [])
            same = [h for h in cur if h["type"] == typ]
            if same and same[0]["level"] >= lv:
                continue                                   # a closer/stronger measurement is already there
            cur = [h for h in cur if h["type"] not in (typ, replaces[typ])]
            res[p["id"]] = sorted(cur + [{"type": typ, "level": lv, "value": val, "at": None}], key=lambda x: -x["level"])
    print("measured hazards:", [(m[0], m[3], m[4]) for m in measured])
    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "points": {k: v for k, v in res.items() if v}, "checked": len(res), "warnings": warnings()}
    json.dump(out, open(os.path.join(ROOT, "hazards.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    lv = [max(h["level"] for h in v) for v in out["points"].values()]
    print(f"checked {len(res)} sections; yellow {lv.count(1)}, orange {lv.count(2)}, red {lv.count(3)}; "
          f"official warnings: {None if out['warnings'] is None else len(out['warnings'])}")


if __name__ == "__main__":
    main()
