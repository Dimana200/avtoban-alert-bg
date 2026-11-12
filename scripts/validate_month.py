#!/usr/bin/env python3
"""30-day check: which forecast rule matches real fog at Bulgarian airports best.

Observed: METAR from Ogimet (fallback: aviationweather.gov, 7 days). Forecast: Open-Meteo historical
forecast API for several models. Fog = observed visibility under 1000 m.
Prints, for every rule: fog hours caught (POD), share of alarms that were wrong (FAR) and CSI."""
import re, sys, time, urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from common import http
from validate import STATIONS, metar_vis

DAYS = 30
MODELS = ["best_match", "icon_seamless", "gfs_seamless", "meteofrance_seamless", "ecmwf_ifs025", "ukmo_seamless"]
VARS = "visibility,relative_humidity_2m,wind_speed_10m,weather_code,cloud_cover_low"


def observations(end):
    obs = defaultdict(dict)
    start = end - timedelta(days=DAYS)
    for icao in STATIONS:
        try:
            url = ("https://www.ogimet.com/cgi-bin/getmetar?" + urllib.parse.urlencode(
                {"icao": icao, "begin": start.strftime("%Y%m%d%H%M"), "end": end.strftime("%Y%m%d%H%M")}))
            txt = http(url, timeout=90, raw=True, tries=2).decode("utf-8", "replace")
            n = 0
            for line in txt.splitlines():
                p = line.split(",", 6)
                if len(p) < 7 or not p[1].isdigit():
                    continue
                hour = f"{p[1]}-{p[2]}-{p[3]}T{p[4]}"
                v = metar_vis(p[6])
                if v is not None:
                    obs[icao][hour] = min(v, obs[icao].get(hour, 99999)); n += 1
            print(f"{icao}: {n} METAR from Ogimet", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{icao}: Ogimet failed ({e})", flush=True)
        time.sleep(8)
    if sum(len(v) for v in obs.values()) < 200:
        print("falling back to aviationweather.gov (7 days)")
        js = http("https://aviationweather.gov/api/data/metar?" + urllib.parse.urlencode(
            {"ids": ",".join(STATIONS), "hours": 168, "format": "json"}), timeout=60)
        for m in js:
            t = m.get("reportTime") or m.get("obsTime")
            if isinstance(t, (int, float)):
                t = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M")
            v = metar_vis(m.get("rawOb", ""))
            if v is not None:
                h = str(t)[:13]
                obs[m["icaoId"]][h] = min(v, obs[m["icaoId"]].get(h, 99999))
    return obs


def forecasts(end):
    q = {"latitude": ",".join(str(s[1]) for s in STATIONS.values()), "longitude": ",".join(str(s[2]) for s in STATIONS.values()),
         "hourly": VARS, "models": ",".join(MODELS), "timezone": "UTC", "wind_speed_unit": "kmh",
         "start_date": (end - timedelta(days=DAYS)).strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d")}
    js = http("https://historical-forecast-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q), timeout=120)
    out = {}
    for icao, loc in zip(STATIONS, js):
        hr = loc["hourly"]
        out[icao] = {t[:13]: {k: hr[k][i] for k in hr if k != "time"} for i, t in enumerate(hr["time"])}
    return out


def g(row, var, model):
    return row.get(f"{var}_{model}", row.get(var) if model == "best_match" else None)


def rules():
    r = {}
    for m in MODELS:
        for th in (1000, 500, 200, 100):
            r[f"{m}: visibility < {th}"] = lambda x, m=m, th=th: (g(x, "visibility", m) is not None and g(x, "visibility", m) < th)
        r[f"{m}: weather code fog (45/48)"] = lambda x, m=m: g(x, "weather_code", m) in (45, 48)
        r[f"{m}: humidity >= 97% and wind < 8 km/h"] = lambda x, m=m: (g(x, "relative_humidity_2m", m) or 0) >= 97 and (g(x, "wind_speed_10m", m) or 99) < 8
        r[f"{m}: humidity >= 99% and wind < 6 km/h"] = lambda x, m=m: (g(x, "relative_humidity_2m", m) or 0) >= 99 and (g(x, "wind_speed_10m", m) or 99) < 6
        r[f"{m}: visibility < 500 and humidity >= 97%"] = lambda x, m=m: (g(x, "visibility", m) or 1e9) < 500 and (g(x, "relative_humidity_2m", m) or 0) >= 97
    for k in (2, 3):
        r[f"at least {k} models: visibility < 1000"] = lambda x, k=k: sum(1 for m in MODELS if (g(x, "visibility", m) or 1e9) < 1000) >= k
        r[f"at least {k} models: humidity >= 97% and wind < 8"] = lambda x, k=k: sum(1 for m in MODELS if (g(x, "relative_humidity_2m", m) or 0) >= 97 and (g(x, "wind_speed_10m", m) or 99) < 8) >= k
    return r


def main():
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    obs, fc = observations(end), forecasts(end)
    rows = [(icao, h, v, fc[icao][h]) for icao in obs for h, v in obs[icao].items() if h in fc.get(icao, {})]
    for th in (1000, 200):
        print(f"\nobserved hours: {len(rows)}; observed fog < {th} m: {sum(1 for r in rows if r[2] < th)} h "
              + str({STATIONS[i][0]: sum(1 for r in rows if r[0] == i and r[2] < th) for i in STATIONS}))
    print("\nrule | fog hours caught | false alarms | POD | FAR | CSI   (fog = observed < 1000 m)")
    res = []
    for name, f in rules().items():
        hit = miss = fa = 0
        for _, _, v, x in rows:
            p = f(x)
            if v < 1000:
                hit += p; miss += not p
            else:
                fa += p
        pod = hit / (hit + miss) if hit + miss else 0
        far = fa / (hit + fa) if hit + fa else 0
        csi = hit / (hit + miss + fa) if hit + miss + fa else 0
        res.append((csi, name, hit, fa, pod, far))
    for csi, name, hit, fa, pod, far in sorted(res, reverse=True):
        print(f"{name} | {hit} | {fa} | {pod:.0%} | {far:.0%} | {csi:.2f}")


if __name__ == "__main__":
    main()
