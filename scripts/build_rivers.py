#!/usr/bin/env python3
"""River flow at NIMH's hydrometric stations -> site/rivers.json (measured daily at 8:00 local time).
Sources (NIMH, Национален институт по метеорология и хидрология):
  - info.meteo.bg/openData/river-runoff/  open data: per station Q today and the station's long-term Qmin / Qavg / Qmax
  - hydro.bg/bg/t1.php                     the station map: pixel position of every station (turned into lat/lon here)
Levels are OUR thresholds on NIMH's numbers, not an official NIMH warning:
  1 high water  Q >= 5 x the long-term average
  2 orange      Q >= 30 % of the highest flow on record at that station
  3 red         Q >= 50 % of the highest flow on record"""
import html, json, os, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from common import http

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "rivers.json")
# stations in towns, used to turn map pixels into lat/lon (fitted fresh each run, so a redrawn map still works)
ANCHORS = {"72700": (42.147, 24.750), "51650": (42.605, 23.035), "51430": (42.262, 23.117), "22750": (43.137, 24.716),
           "21650": (42.915, 24.263), "23650": (42.874, 25.318), "73850": (41.770, 26.199), "42800": (43.177, 27.444),
           "74850": (42.172, 26.568), "71800": (42.194, 24.333), "43700": (43.161, 26.813), "52850": (41.520, 23.866)}


def fit(rows, ys):
    """Least squares y = a*x + b*y + c (3x3 normal equations, no numpy on the runner)."""
    m = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    v = [sum(r[i] * y for r, y in zip(rows, ys)) for i in range(3)]
    for i in range(3):                                  # Gauss-Jordan
        p = m[i][i]
        m[i] = [x / p for x in m[i]]; v[i] /= p
        for k in range(3):
            if k != i:
                f = m[k][i]
                m[k] = [a - f * b for a, b in zip(m[k], m[i])]; v[k] -= f * v[i]
    return v


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def num(s):
    s = s.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def positions():
    s = http("https://hydro.bg/bg/t1.php", raw=True, timeout=60).decode("utf-8", "replace")
    px = {m.group(3): (float(m.group(1)), float(m.group(2)))
          for m in re.finditer(r'coords="([-\d.]+),([-\d.]+),\d+"\s+id="(\d+)"', s)}
    pts = [(px[k], v) for k, v in ANCHORS.items() if k in px]
    if len(pts) < 6:
        raise RuntimeError(f"station map: only {len(pts)} anchor stations")
    a = [[x, y, 1.0] for (x, y), _ in pts]
    cl, co = fit(a, [v[0] for _, v in pts]), fit(a, [v[1] for _, v in pts])
    err = max(((dot([x, y, 1], cl) - v[0]) * 111) ** 2 + ((dot([x, y, 1], co) - v[1]) * 81) ** 2
              for (x, y), v in pts) ** 0.5
    if err > 6:
        raise RuntimeError(f"station map fit off by {err:.1f} km")
    print(f"station map: {len(px)} stations, fit within {err:.1f} km")
    return {k: (round(dot([x, y, 1], cl), 3), round(dot([x, y, 1], co), 3))
            for k, (x, y) in px.items() if 0 <= x < 1000 and 0 <= y < 700}


def table(day):
    s = http("https://info.meteo.bg/openData/river-runoff/", data={"mydate": day}, raw=True, timeout=60).decode("utf-8", "replace")
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S | re.I):
        c = [html.unescape(re.sub(r"<[^>]+>", "", td)).strip() for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)]
        if len(c) >= 9 and c[0].isdigit():
            rows.append(c)
    return rows


def main():
    pos = positions()
    today = datetime.now(ZoneInfo("Europe/Sofia")).date()
    for day in (today, today - timedelta(days=1)):
        rows = table(day.isoformat())
        if sum(1 for r in rows if num(r[7]) is not None) >= 20:
            break
    else:
        raise RuntimeError("no river data for today or yesterday")
    out = []
    for r in rows:
        sid, river, place = r[0], r[1], r[2]
        qavg, qmax, q, dh = num(r[4]), num(r[5]), num(r[7]), num(r[8])
        if q is None or sid not in pos:
            continue
        lv = 0
        if qmax and q >= 0.5 * qmax:
            lv = 3
        elif qmax and q >= 0.3 * qmax:
            lv = 2
        elif qavg and q >= 5 * qavg:
            lv = 1
        out.append({"id": sid, "river": river, "place": place, "lat": pos[sid][0], "lon": pos[sid][1],
                    "q": q, "qavg": qavg, "qmax": qmax, "dh": dh, "level": lv})
    json.dump({"source": "НИМХ", "date": day.isoformat(), "stations": out}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print(f"rivers {day}: {len(out)} stations; high {[(s['river'], s['place'], s['level']) for s in out if s['level']]}")


if __name__ == "__main__":
    main()
