#!/usr/bin/env python3
"""Compare the Open-Meteo values the map uses with real airport observations (METAR) in Bulgaria
for the last 48 hours: visibility (fog) and wind gusts. Prints a report; changes nothing."""
import re, sys, urllib.parse
from collections import defaultdict
from common import http

STATIONS = {  # ICAO: (name, lat, lon)
    "LBSF": ("София", 42.695, 23.406), "LBPD": ("Пловдив", 42.068, 24.851), "LBBG": ("Бургас", 42.570, 27.515),
    "LBWN": ("Варна", 43.232, 27.825), "LBGO": ("Горна Оряховица", 43.152, 25.713),
}


def metar_vis(raw):
    """Prevailing visibility in metres from a European METAR; None if missing."""
    if " CAVOK" in raw:
        return 10000
    toks = raw.split()
    for i, t in enumerate(toks[2:], 2):
        if re.fullmatch(r"\d{4}", t) and not re.fullmatch(r"\d{4}", toks[i - 1] if i else ""):
            return 10000 if t == "9999" else int(t)
    return None


def metar_gust(raw):
    m = re.search(r"\b\d{3}\d{2}G(\d{2})KT\b", raw)
    return round(int(m.group(1)) * 1.852) if m else None


def main():
    obs = defaultdict(dict)   # icao -> "YYYY-MM-DDTHH" -> (vis, gust)
    js = http("https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode(
        {"ids": ",".join(STATIONS), "hours": 48, "format": "json"}), timeout=60)
    for m in js:
        raw, t = m.get("rawOb", ""), m.get("reportTime") or m.get("obsTime")
        if isinstance(t, (int, float)):
            from datetime import datetime, timezone
            t = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M")
        hour = str(t)[:13]
        v = metar_vis(raw)
        if v is None:
            continue
        prev = obs[m["icaoId"]].get(hour)
        if prev is None or v < prev[0]:          # keep the worst report in each hour
            obs[m["icaoId"]][hour] = (v, metar_gust(raw))
    q = {"latitude": ",".join(str(s[1]) for s in STATIONS.values()), "longitude": ",".join(str(s[2]) for s in STATIONS.values()),
         "hourly": "visibility,wind_gusts_10m", "past_days": 2, "forecast_days": 1, "timezone": "UTC", "wind_speed_unit": "kmh"}
    model = http("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=60)
    print("hour (UTC) | station | observed vis m | model vis m | observed gust | model gust")
    pairs = []
    for (icao, (name, _, _)), loc in zip(STATIONS.items(), model):
        hr = loc["hourly"]
        mv = {t[:13]: (v, g) for t, v, g in zip(hr["time"], hr["visibility"], hr["wind_gusts_10m"])}
        for hour, (ov, og) in sorted(obs[icao].items()):
            if hour not in mv or mv[hour][0] is None:
                continue
            pairs.append((icao, hour, ov, mv[hour][0], og, mv[hour][1]))
            if ov < 2000 or mv[hour][0] < 2000:
                print(f"{hour} | {name} | {ov} | {round(mv[hour][0])} | {og} | {round(mv[hour][1] or 0)}")
    print(f"\nhours compared: {len(pairs)}")
    for th in (1000, 500, 200):
        hit = sum(1 for p in pairs if p[2] < th and p[3] < th)
        miss = sum(1 for p in pairs if p[2] < th and p[3] >= th)
        false = sum(1 for p in pairs if p[2] >= th and p[3] < th)
        print(f"fog below {th} m: observed {hit + miss} h, model caught {hit}, missed {miss}, false alarms {false}")
    for mth in (1000, 500, 200, 100):
        for oth in (1000, 500, 200):
            n = sum(1 for p in pairs if p[3] < mth)
            ok = sum(1 for p in pairs if p[3] < mth and p[2] < oth)
            if n:
                print(f"when model says < {mth} m ({n} h): observed < {oth} m in {ok} h ({round(100 * ok / n)}%)")
    gp = [(p[4], p[5]) for p in pairs if p[5] is not None]
    print(f"\nwind: model gust >= 55 km/h in {sum(1 for o, m in gp if m >= 55)} h; observed reported gust >= 55 in "
          f"{sum(1 for o, m in gp if o and o >= 55)} h")


if __name__ == "__main__":
    main()
