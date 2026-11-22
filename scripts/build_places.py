"""Places for the app's search: fuel, food, toilets, car service, parking, rest areas, hospitals, pharmacies.
OpenStreetMap via Overpass -> site/places.json (compact: one list per place).
Hospital photos: free photos from Wikimedia Commons (through the hospital's Wikidata item), with author and licence."""
import json, os, re, time, urllib.parse, urllib.request
from build_roads import fetch
import common

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "site", "places.json")

Q = """area["ISO3166-1"="BG"][admin_level=2]->.a;
(nwr[amenity=fuel](area.a);
 nwr[amenity~"^(restaurant|fast_food|cafe)$"][name](area.a);
 nwr[amenity=toilets](area.a);
 nwr[shop~"^(car_repair|tyres)$"](area.a);
 nwr[amenity=parking][name](area.a);
 nwr[highway~"^(rest_area|services)$"](area.a);
 nwr[amenity=hospital](area.a);
 nwr[healthcare=hospital](area.a);
 nwr[amenity=pharmacy](area.a););
out center tags;"""

# category, and the name to show when the place has none
def kind(t):
    a, s, h = t.get("amenity"), t.get("shop"), t.get("highway")
    if a == "fuel": return "fuel", "Бензиностанция"
    if a in ("restaurant", "fast_food", "cafe"): return "food", {"restaurant": "Ресторант", "fast_food": "Закусвалня", "cafe": "Кафе"}[a]
    if a == "toilets": return "wc", "Тоалетна"
    if s == "tyres": return "service", "Гуми"
    if s == "car_repair": return "service", "Автосервиз"
    if a == "parking": return "parking", "Паркинг"
    if h in ("rest_area", "services"): return "rest", "Място за почивка"
    if a == "hospital" or t.get("healthcare") == "hospital": return "hospital", "Болница"
    if a == "pharmacy": return "pharmacy", "Аптека"
    return None, None


def api(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": common.UA})
    return json.load(urllib.request.urlopen(req, timeout=60))


def photos(out):
    """Hospitals with a Wikidata item that has a photo (P18): a thumbnail from Commons, its author and licence."""
    hosp = [p for p in out if len(p) > 5 and "wd" in p[5]]
    qids = sorted({p[5]["wd"] for p in hosp})
    files = {}
    for i in range(0, len(qids), 50):
        try:
            js = api("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                                             "props": "claims", "format": "json"})
        except Exception as e:  # noqa: BLE001
            print("wikidata failed", e, flush=True); continue
        for q, ent in js.get("entities", {}).items():
            c = ent.get("claims", {}).get("P18")
            if c:
                try: files[q] = c[0]["mainsnak"]["datavalue"]["value"]
                except (KeyError, IndexError): pass
        time.sleep(1)
    info = {}
    names = sorted(set(files.values()))
    for i in range(0, len(names), 40):
        try:
            js = api("https://commons.wikimedia.org/w/api.php", {"action": "query", "titles": "|".join("File:" + n for n in names[i:i + 40]),
                     "prop": "imageinfo", "iiprop": "url|extmetadata", "iiurlwidth": 640, "format": "json"})
        except Exception as e:  # noqa: BLE001
            print("commons failed", e, flush=True); continue
        for pg in js.get("query", {}).get("pages", {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            md = ii.get("extmetadata", {})

            artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "")).strip()[:60]
            lic = md.get("LicenseShortName", {}).get("value", "")[:30]
            if ii.get("thumburl"):
                info[pg["title"][5:]] = (ii["thumburl"], (artist + ", " if artist else "") + lic + ", Wikimedia Commons")
        time.sleep(1)
    n = 0
    for p in hosp:
        f = files.get(p[5]["wd"])
        f2 = f and f.replace("_", " ")
        got = info.get(f) or info.get(f2)
        if got:
            p[5]["img"], p[5]["ia"] = got
            n += 1
        del p[5]["wd"]
    print(f"hospitals with a Wikidata item: {len(hosp)}, with a photo: {n}", flush=True)


def main():
    els = fetch(Q)
    out, seen = [], set()
    for e in els:
        t = e.get("tags", {})
        cat, default = kind(t)
        if not cat:
            continue
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        pid = e["type"][0] + str(e["id"])
        if pid in seen:
            continue
        seen.add(pid)
        name = (t.get("name:bg") or t.get("name") or t.get("brand") or default).strip()[:80]
        extra = {}
        if t.get("brand") and t.get("brand") != name: extra["b"] = t["brand"][:40]
        if t.get("opening_hours"): extra["oh"] = t["opening_hours"][:60]
        if cat in ("hospital", "pharmacy"):
            ph = t.get("phone") or t.get("contact:phone")
            if ph: extra["ph"] = ph.split(";")[0].strip()[:30]
            web = t.get("website") or t.get("contact:website")
            if web and web.startswith("http"): extra["w"] = web[:120]
            addr = " ".join(x for x in [t.get("addr:street"), t.get("addr:housenumber")] if x)
            city = t.get("addr:city") or t.get("addr:place")
            if addr or city: extra["a"] = ", ".join(x for x in [addr, city] if x)[:100]
            if t.get("emergency") == "yes": extra["em"] = 1
            if cat == "hospital" and t.get("wikidata", "").startswith("Q"): extra["wd"] = t["wikidata"]
        sub = t.get("amenity") if cat == "food" else t.get("shop") if cat == "service" else None
        if sub: extra["s"] = sub
        out.append([pid, cat, name, round(lat, 5), round(lon, 5)] + ([extra] if extra else []))
    photos(out)
    out.sort(key=lambda p: p[0])
    if len(out) < 1000:
        raise SystemExit(f"only {len(out)} places: keeping the old file")
    counts = {}
    for p in out: counts[p[1]] = counts.get(p[1], 0) + 1
    print("places:", len(out), counts, flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "OpenStreetMap", "p": out},
                  f, ensure_ascii=False, separators=(",", ":"))
    print("bytes:", os.path.getsize(OUT))


if __name__ == "__main__":
    main()
