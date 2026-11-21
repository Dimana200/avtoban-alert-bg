"""Places along the roads for the app's search: fuel, food, toilets, car service, parking, rest areas.
OpenStreetMap via Overpass -> site/places.json (compact: one list per place)."""
import json, os, time
from build_roads import fetch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "site", "places.json")

Q = """area["ISO3166-1"="BG"][admin_level=2]->.a;
(nwr[amenity=fuel](area.a);
 nwr[amenity~"^(restaurant|fast_food|cafe)$"][name](area.a);
 nwr[amenity=toilets](area.a);
 nwr[shop~"^(car_repair|tyres)$"](area.a);
 nwr[amenity=parking][name](area.a);
 nwr[highway~"^(rest_area|services)$"](area.a););
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
    return None, None


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
        sub = t.get("amenity") if cat == "food" else t.get("shop") if cat == "service" else None
        if sub: extra["s"] = sub
        out.append([pid, cat, name, round(lat, 5), round(lon, 5)] + ([extra] if extra else []))
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
