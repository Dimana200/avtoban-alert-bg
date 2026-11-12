"""Hourly observations of the 44 NIMH weather stations from weather.bg ("Текущи данни").

Source: НИМХ, https://weather.bg (content © НИМХ; cited as the source on the map).
The page gives the weather phenomenon as text (e.g. "мъгла") and wind in m/s, not visibility in metres.
Mountain peaks are left out: fog on a summit says nothing about the roads below.
"""
import html, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from common import http

URL = "https://weather.bg/index.php?koiFail=tekushti&lng=0"

# station name on weather.bg -> (lat, lon), approximate position of the town
STATIONS = {
    "Ново село": (44.16, 22.78), "Видин": (43.99, 22.88), "Враца": (43.21, 23.55), "Монтана": (43.41, 23.23),
    "Лом": (43.82, 23.24), "Оряхово": (43.73, 23.96), "Кнежа": (43.50, 24.08), "Ловеч": (43.14, 24.72),
    "Плевен": (43.42, 24.61), "Велико Търново": (43.08, 25.63), "Свищов": (43.62, 25.35), "Русе": (43.85, 25.96),
    "Шумен": (43.27, 26.92), "Разград": (43.53, 26.52), "Силистра": (44.12, 27.26), "Варна": (43.21, 27.91),
    "Шабла": (43.54, 28.53), "Калиакра": (43.36, 28.47), "Добрич": (43.57, 27.83), "Кюстендил": (42.28, 22.69),
    "Драгоман": (42.92, 22.93), "Благоевград": (42.02, 23.09), "София-ЦМС": (42.65, 23.38),
    "Пловдив - Тракия": (42.14, 24.79), "Пазарджик": (42.19, 24.33), "Чирпан": (42.20, 25.33),
    "Казанлък": (42.62, 25.39), "Стара Загора": (42.43, 25.64), "Сливен": (42.68, 26.32), "Елхово": (42.17, 26.57),
    "Карнобат": (42.65, 26.98), "н. Емине": (42.70, 27.90), "Бургас": (42.50, 27.47), "Ахтопол": (42.10, 27.94),
    "Сандански": (41.57, 23.28), "Гоце Делчев": (41.57, 23.73), "Рожен": (41.69, 24.74), "Кърджали": (41.65, 25.37),
    "Хасково": (41.93, 25.56),
}


def _cell_text(cell):
    alts = " ".join(re.findall(r'(?:alt|title)\s*=\s*"([^"]*)"', cell))
    txt = re.sub(r"<[^>]+>", " ", cell)
    return re.sub(r"\s+", " ", html.unescape(txt + " " + alts)).strip()


def parse(page):
    """-> {station: {"date", "hour", "phen", "wind_ms"}} for the stations we know."""
    out = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
        cells = [_cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if len(cells) < 6:
            continue
        name = cells[0].strip()
        if name not in STATIONS:
            continue
        wind = re.match(r"\d+", cells[5] or "")
        out[name] = {"date": cells[1], "hour": cells[2], "phen": cells[4].lower(), "wind_ms": int(wind.group(0)) if wind else None}
    return out


def hazards(obs):
    """Measured hazards -> list of (station, lat, lon, type, level, text)."""
    res, now = [], datetime.now(ZoneInfo("Europe/Sofia")).replace(tzinfo=None)
    for name, o in obs.items():
        try:
            t = datetime.strptime(f"{o['date']} {int(o['hour']):02d}", "%d.%m.%Y %H")
        except ValueError:
            continue
        if not timedelta(hours=-1) <= now - t <= timedelta(hours=3):
            continue                                   # old report: do not show it as current
        lat, lon = STATIONS[name]
        p, w = o["phen"], o["wind_ms"]
        where = f"станция {name}, {o['hour']} ч."
        if "мъгла" in p:
            res.append((name, lat, lon, "fogobs", 3 if re.search(r"гъста|силна", p) else 2, where))
        if re.search(r"виелица|навявания", p):
            res.append((name, lat, lon, "snowobs", 3, where))
        elif re.search(r"сняг|снеговалеж", p):
            res.append((name, lat, lon, "snowobs", 2, where))
        if re.search(r"поледица|заледяване|замръзващ|скреж", p):
            res.append((name, lat, lon, "iceobs", 3 if "поледица" in p else 2, where))
        if w is not None and w >= 15:
            res.append((name, lat, lon, "windobs", 3 if w >= 20 else 2, f"{round(w * 3.6)} km/h, {where}"))
    return res


def fetch():
    page = http(URL, timeout=60, raw=True, tries=2).decode("utf-8", "replace")
    obs = parse(page)
    print(f"NIMH stations read: {len(obs)}; phenomena: " + "; ".join(f"{k}: {v['phen']} {v['wind_ms']} m/s" for k, v in obs.items()))
    return obs
