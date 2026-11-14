"""Temporary: our cameras along named streets (OSM ways) in a few cities."""
import json, sys, math
sys.path.insert(0, "scripts")
from build_roads import fetch
from build_avgspeed import seg_dist
Q = {
 "София": ["Цариградско шосе", "България", "Княгиня Мария Луиза", "Васил Левски", "Цар Освободител", "Евлоги и Христо Георгиеви",
           "Тодор Александров", "Александър Стамболийски", "Сливница", "Генерал Данаил Николаев", "Мадрид", "Тодор Каблешков",
           "Александър Малинов", "Андрей Сахаров", "Пейо Крачолов Яворов", "Драган Цанков", "Захари Стоянов", "Георги Сава Раковски", "Оборище"],
 "Пловдив": ["Княгиня Мария Луиза", "Уилям Гладстон", "Санкт Петербург", "Асеновградско шосе", "Карловско шосе"],
 "Русе": ["Христо Ботев"], "Плевен": ["Русе", "Христо Ботев", "Сан Стефано", "Стоян Заимов"], "Поморие": ["Княз Борис I"],
}
cams = json.load(open("site/cameras.json"))["cameras"]
for city, streets in Q.items():
    area = f'area["name"="{city}"]["boundary"="administrative"]->.c;'
    for st in streets:
        ways = fetch(area + f'way["highway"]["name"~"{st}"](area.c);out geom;')
        lines = [[(p["lat"], p["lon"]) for p in w["geometry"]] for w in ways if "geometry" in w]
        if not lines:
            print(f"NOSTREET {city} | {st}"); continue
        lat = [p[0] for l in lines for p in l]; lon = [p[1] for l in lines for p in l]
        box = (min(lat) - .002, max(lat) + .002, min(lon) - .003, max(lon) + .003)
        hits = {"speed": 0, "red": 0}
        for c in cams:
            if not (box[0] < c["lat"] < box[1] and box[2] < c["lon"] < box[3]): continue
            if min(seg_dist((c["lat"], c["lon"]), a, b)[0] for l in lines for a, b in zip(l, l[1:])) < 40:
                hits[c["t"]] += 1
        print(f"ST {city} | {st} | speed {hits['speed']} | red {hits['red']}")
