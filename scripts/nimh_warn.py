"""Official NIMH warnings for today by municipality (wind, rain, snow/ice, temperature) and by
region (fog, thunderstorms), from https://weather.bg/obshtini/ (content © НИМХ, cited on the map).

Each region page has a table: municipality | high temp | low temp | wind | rain | snow/ice, where a
cell's background colour is the level (#00ff00 none, #ffff00 yellow, orange, red). Fog and
thunderstorms are only warned per region, as text under the region header whose colour is the level.
"""
import html, re, time
from common import http

BASE = "https://weather.bg/obshtini/index.php"
REGIONS = ("BGS BLG DOB GAB HKV JAM KNL KRZ LOV MON PAZ PDV PER PVN RAZ RSE SFO SHU SLS SLV SML SOF "
           "SZR TGV VAR VID VRC VTR").split()
COLS = ["hot", "cold", "wind", "rain", "snow"]


def level(color):
    c = color.lower().lstrip("#")
    if len(c) != 6:
        return None
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    if g > 200 and r < 100:
        return 0                         # green: no danger
    if r > 200 and g > 200 and b < 100:
        return 1                         # yellow
    if r > 200 and 80 <= g <= 200 and b < 100:
        return 2                         # orange
    if r > 200 and g < 80:
        return 3                         # red
    return None                          # grey: no data


def norm(name):
    n = re.sub(r"(?i)\bобщина\b", "", name).replace("Столична", "София").strip()
    return re.sub(r"\s+", " ", n).lower()


def parse(page, code):
    """-> (municipalities {norm name: {kind: level}}, region {"level", "text"})"""
    i = page.find("<div class='obl2'>")
    head = page[page.find("myTable1"):i] if "myTable1" in page else ""
    rl = re.search(r"<tr bgcolor=\"(#[0-9A-Fa-f]{6})\"", head)
    rows = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t))).strip()
            for t in re.findall(r"<td colspan=\"4\">(.*?)</td>", head, re.S)]
    text = " ".join(t for t in rows if t and not t.startswith(("прогноза за", "издадена на")))
    region = {"level": level(rl.group(1)) if rl else None, "text": text}
    munis = {}
    for name, body in re.findall(r"<tr><td>([^<]+)</td>(.*?)</tr>", page[i:], re.S):
        lv = [level(c) for c in re.findall(r"background-color:\s*(#[0-9a-fA-F]{6})", body)]
        if len(lv) >= 5:
            munis[norm(name)] = {k: v for k, v in zip(COLS, lv) if v}
    return munis, region


def fetch():
    munis, regions = {}, {}
    for code in REGIONS:
        try:
            page = http(f"{BASE}?z=d&o={code}", timeout=60, raw=True, tries=3).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print("   NIMH warnings: region", code, "failed:", e)
            continue
        m, r = parse(page, code)
        for k, v in m.items():
            munis[k] = dict(v, region=code)
        regions[code] = r
        time.sleep(2)                     # be gentle with the NIMH server
    active = {k: v for k, v in munis.items() if len(v) > 1}
    print(f"NIMH warnings: {len(munis)} municipalities read, {len(active)} with a warning; "
          f"regions with text: {[(c, r['level'], r['text'][:60]) for c, r in regions.items() if r['text'] and r['text'] != 'Няма опасност'][:8]}")
    return munis, regions
