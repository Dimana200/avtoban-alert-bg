"""Temporary: our speed cameras around named places."""
import json, sys, math
sys.path.insert(0, "scripts")
from build_roads import fetch, AREA
from build_avgspeed import km
names = ["Сомовит","Козлодуй","Севлиево","Килифарево","Паничерево","Баня","Братя Кънчеви","Стара Загора","Търговище","Златиница","Костинброд",
 "Пазарджик","Бургас","Царево","Исперих","Айтос","Добромир","Величка","Кричим","Девин","Ножарово","Антимово","Антонивановци","Божурище","Варна",
 "Враца","Монтана","Перник","Разград","Попово","Поморие","Свети Влас","Слънчев бряг","Плевен","Пловдив"]
pl = {}
for e in fetch(AREA + 'node["place"~"city|town|village|hamlet|suburb"]["name"~"^(' + "|".join(names) + ')$"](area.a);out;'):
    pl.setdefault(e["tags"]["name"], []).append((e["lat"], e["lon"], e["tags"]["place"]))
cams = [c for c in json.load(open("site/cameras.json"))["cameras"] if c["t"] == "speed"]
for n in names:
    best = None
    for la, lo, t in pl.get(n, []):
        r = 8 if t == "city" else 4
        k = [c for c in cams if km((la, lo), (c["lat"], c["lon"])) <= r]
        if best is None or len(k) > len(best[1]): best = ((la, lo, t), k)
    if best is None: print(f"PL {n} | not found"); continue
    print(f"PL {n} | {best[0][2]} | speed cams {len(best[1])} | limits {sorted(c['limit'] for c in best[1])}")
