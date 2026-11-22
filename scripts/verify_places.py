"""Check hospitals and pharmacies from OpenStreetMap against the official registers (data/registries.json).

Marks written into a place's extras:
  v: 1   found in the official register (an active licence)
  x: 1   pharmacy: only a closed licence at this address, no active one -> "may be closed"
  em     hospitals found in the register: the register decides (1 = emergency unit, removed when it has none)
  ph     hospitals found in the register without a phone in OpenStreetMap: the register's phone
A place the register does not know stays as it is (OpenStreetMap also has clinics and old names)."""
import math, re

GENERIC = set("""многопрофилна специализирана университетска болница болници болнична за и по на в от с към
активно лечение продължително рехабилитация лечебно заведение център центъра медицински медицинска
умбал мбал сбал сбалх сбалаг сбалпфз сбалол сбалвб сбалнп сбалоз сбалб сбалкб сбалк сбалдб сбалпп сбр мц дкц коц цпз ддлр
ад еад еоод оод ет гр град село ул бул д р др проф доц акад хоспитал hospital clinic клиника клиничен филиал
обл област община""".split())


def norm(s):
    s = (s or "").lower().replace("ё", "е")
    s = re.sub(r"[\"'„“”«»().,;:/\\\-–]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(name, town_words=()):
    out = set()
    for w in norm(name).split():
        if len(w) < 3 or w in GENERIC or w in town_words or w.isdigit():
            continue
        if w in ("свети", "света", "св"):
            continue
        out.add(w[:6])                          # "клиник" = "клиника", "георги" = "георгий"
    return out


def km(a, b, c, d):
    r = math.pi / 180
    x, y = (c - a) * r, (d - b) * r
    h = math.sin(x / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin(y / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


class Towns:
    """The nearest settlement of a point (OpenStreetMap place nodes), in a grid for speed."""

    def __init__(self, places):
        self.g = {}
        for name, kind, lat, lon in places:
            self.g.setdefault((int(lat * 10), int(lon * 10)), []).append((name, kind, lat, lon))

    def near(self, lat, lon):
        best, bd = None, 1e9
        ci, cj = int(lat * 10), int(lon * 10)
        for i in range(ci - 2, ci + 3):
            for j in range(cj - 2, cj + 3):
                for name, kind, a, b in self.g.get((i, j), ()):
                    d = km(lat, lon, a, b)
                    # a point inside a town's area is often nearer to a village's centre point: towns weigh more
                    d = d / (3 if kind == "city" else 2 if kind == "town" else 1)
                    if d < bd:
                        best, bd = name, d
        return best


STREET = re.compile(r"^(ул|улица|бул|булевард|пл|площад|ж\.?\s*к|кв|квартал)\b\.?\s*", re.I)


def addr_key(town, addr):
    """("гр. Берковица", "ул. Николаевска № 8") -> ("берковица", "николаевска", "8")"""
    t = norm(re.sub(r"^(гр|с)\.\s*", "", town or "", flags=re.I))
    t = re.sub(r"\s+\d{4}$", "", t)
    a = (addr or "").split(",")[0]
    a = STREET.sub("", a.strip())
    m = re.search(r"(?:№|N|No)?\s*(\d+[а-яa-z]?)\b", a)
    num = m.group(1).lower() if m else ""
    street = norm(re.sub(r"(№|N\b|No\b)?\s*\d+.*$", "", a))
    street = " ".join(w for w in street.split() if w not in ("ул", "бул", "пл", "бл", "вх", "ет", "ап"))
    return (t, street[:14], num)


def verify(places, reg, towns):
    """places: the places.json rows (changed in place). Returns counts for the log."""
    stats = {"hosp": 0, "hosp_v": 0, "hosp_em_on": 0, "hosp_em_off": 0, "hosp_ph": 0,
             "ph": 0, "ph_addr": 0, "ph_v": 0, "ph_x": 0, "reg_hosp": 0, "reg_hosp_matched": 0}
    hosp = reg.get("hospitals") or []
    stats["reg_hosp"] = len(hosp)
    by_town = {}
    for h in hosp:
        for t in h["t"]:
            by_town.setdefault(norm(t), []).append(h)
    matched = set()
    act, closed = set(), set()
    ph = reg.get("pharmacies") or {}
    for t, a in ph.get("active", []):
        act.add(addr_key(t, a))
    for t, a in ph.get("closed", []):
        closed.add(addr_key(t, a))

    for p in places:
        cat = p[1]
        if cat not in ("hospital", "pharmacy"):
            continue
        ex = p[5] if len(p) > 5 else {}
        addr = ex.get("a", "")
        town = None
        if addr and "," in addr:
            town = norm(addr.split(",")[-1])
        if not town:
            town = norm(towns.near(p[3], p[4]) or "")
        if cat == "hospital":
            stats["hosp"] += 1
            cands = by_town.get(town, [])
            tw = set(town.split())
            mine = tokens(p[2], tw)
            best, bs, tie = None, 0, False
            for h in cands:
                s = len(mine & tokens(h["n"], tw))
                if s > bs:
                    best, bs, tie = h, s, False
                elif s == bs and s > 0:
                    tie = True
            if (best is None or tie) and not mine and len(cands) == 1:
                best, tie = cands[0], False         # "Болница" / "МБАЛ Берковица" and the town has only one hospital
            if best is None or tie:
                continue
            matched.add(best["no"])
            stats["hosp_v"] += 1
            ex["v"] = 1
            if best["em"] and not ex.get("em"):
                ex["em"] = 1; stats["hosp_em_on"] += 1
            elif not best["em"] and ex.get("em"):
                ex.pop("em"); stats["hosp_em_off"] += 1
            if best["ph"] and not ex.get("ph"):
                ex["ph"] = best["ph"]; stats["hosp_ph"] += 1
        else:
            stats["ph"] += 1
            if not addr:
                continue
            stats["ph_addr"] += 1
            street = addr.split(",")[0]
            k = addr_key(town, street)
            if not k[2]:
                continue
            if k in act:
                ex["v"] = 1; stats["ph_v"] += 1
            elif k in closed:
                ex["x"] = 1; stats["ph_x"] += 1
        if ex and len(p) == 5:
            p.append(ex)
    stats["reg_hosp_matched"] = len(matched)
    return stats
