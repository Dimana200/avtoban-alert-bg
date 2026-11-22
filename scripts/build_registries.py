"""The official registers, to check the places from OpenStreetMap -> data/registries.json

- Hospitals: the National Health Information System's public registers API (registries.his.bg, the data behind
  opendata.his.bg/hospitals): every hospital with an active licence, its towns, phone and whether it has an
  emergency unit ("спешн..." in the name of one of its departments).
- Pharmacies: the Bulgarian Drug Agency's register of retail licences (bda.bg, an .xls file): the town and address of
  every active pharmacy, and of the closed ones (licence ended or taken away). Only town and address are kept:
  no company or manager names (many are sole traders, i.e. a person's name).

Used by build_places.py. If a register cannot be read, its part of the old file is kept."""
import io, json, os, re, sys, time, urllib.parse, urllib.request
import common

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "registries.json")
HIS = "https://registries.his.bg/api/v1/hospital"
BDA_PAGE = "https://www.bda.bg/bg/%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B8/%D1%80%D0%B5%D0%B3%D0%B8%D1%81%D1%82%D1%80%D0%B8-%D0%BD%D0%B0-%D1%82%D1%8A%D1%80%D0%B3%D0%BE%D0%B2%D1%86%D0%B8-%D0%B8-%D0%BF%D1%80%D0%BE%D0%B8%D0%B7%D0%B2%D0%BE%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B8"


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": common.UA})
    for i in range(3):
        try:
            b = urllib.request.urlopen(req, timeout=120).read()
            return b if raw else json.loads(b)
        except Exception as e:
            print("retry", url[:90], e, flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError("cannot read " + url)


TOWN = re.compile(r"\b(гр|с)\.\s*([А-Яа-я][А-Яа-я .\-]+?)(?=\s*(?:$|,|\d|ул\.|бул\.|ж\.к|кв\.|п\.к|общ|обл|Област|\())")


def towns(text):
    return [m.group(2).strip().lower() for m in TOWN.finditer(text or "")]


def hospitals():
    lst = get(HIS + "/getHospitalForApiV1?" + urllib.parse.urlencode({"start": 0, "length": 100000, "searchText": "", "searchStatus": 1}))
    out = []
    for r in lst.get("registry") or []:
        if r.get("statusCode") != 1:
            continue
        d = get(HIS + "/getHospitalByNumberForApiV1?number=" + urllib.parse.quote(r["number"]))
        time.sleep(0.3)                                    # gently: one request at a time
        tw = towns(d.get("name")) + [t for a in d.get("adresses") or [] for t in towns(a.get("addressText"))]
        deps = [e.get("name") or "" for a in d.get("adresses") or [] for e in a.get("hospitalElements") or []]
        em = any(re.search(r"спешн", x, re.I) for x in deps)
        out.append({"n": d.get("name") or r.get("name"), "t": sorted(set(tw)), "ph": (d.get("phone") or "").strip(),
                    "em": 1 if em else 0, "vid": d.get("vidCode") or r.get("vidCode"), "no": r["number"]})
    if len(out) < 200:
        raise RuntimeError(f"only {len(out)} hospitals")
    print("hospitals:", len(out), "with emergency unit:", sum(h["em"] for h in out), flush=True)
    return out


def pharmacies():
    import pandas as pd
    page = get(BDA_PAGE, raw=True).decode("utf-8", "ignore")
    m = re.findall(r'href="([^"]*Register_Apteki[^"]*\.xlsx?)"', page)
    if not m:
        raise RuntimeError("no pharmacy register link on the page")
    url = urllib.parse.urljoin(BDA_PAGE, m[0])
    print("pharmacy register:", url, flush=True)
    sheets = pd.read_excel(io.BytesIO(get(url, raw=True)), sheet_name=None, header=None, dtype=str)
    names = list(sheets)
    act, gone = sheets[names[0]], sheets[names[1]] if len(names) > 1 else None

    def col(df, word):
        for i in range(min(4, len(df))):
            for j, v in enumerate(df.iloc[i]):
                if isinstance(v, str) and word in v:
                    return i, j
        return None, None

    out = {"active": [], "closed": []}
    hi, tj = col(act, "Адрес на аптека - град")
    _, aj = col(act, "Адрес на аптека")
    if aj == tj:
        aj = tj + 1
    for _, r in act.iloc[hi + 1:].iterrows():
        t, a = r.iloc[tj], r.iloc[aj]
        if isinstance(t, str) and isinstance(a, str):
            out["active"].append([t.strip(), a.strip()])
    if gone is not None:
        hi, tj = col(gone, "Адрес на аптека - град")
        if hi is not None:
            aj = tj + 1
            for _, r in gone.iloc[hi + 1:].iterrows():
                t, a = r.iloc[tj], r.iloc[aj]
                if isinstance(t, str) and isinstance(a, str):
                    out["closed"].append([t.strip(), a.strip()])
    if len(out["active"]) < 1500:
        raise RuntimeError(f"only {len(out['active'])} pharmacies")
    print("pharmacies active:", len(out["active"]), "closed:", len(out["closed"]), flush=True)
    return out


def main():
    old = {}
    if os.path.exists(OUT):
        old = json.load(open(OUT, encoding="utf-8"))
    res = dict(old)
    for key, fn in (("hospitals", hospitals), ("pharmacies", pharmacies)):
        try:
            res[key] = fn()
            res[key + "_at"] = time.strftime("%Y-%m-%d", time.gmtime())
        except Exception as e:
            print("KEPT OLD", key, e, flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, separators=(",", ":"))
    print("bytes:", os.path.getsize(OUT))


if __name__ == "__main__":
    main()
