"""Charging stations from Open Charge Map (https://openchargemap.org) -> data/ocm.json, for build_places.py.

Needs the free API key in the OCM_API_KEY environment variable (GitHub secret); without it nothing is done.
Only records whose data provider is marked open-data licensed by Open Charge Map itself are kept (their user-contributed
data is CC BY 4.0). A station that is not operational is left out. The source must be shown to the user."""
import json, os, sys, time, urllib.parse, urllib.request
import common

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "ocm.json")
API = "https://api.openchargemap.io/v3/poi"

SHORT = {"Type 2 (Socket Only)": "Type 2", "Type 2 (Tethered Connector)": "Type 2", "CCS (Type 2)": "CCS",
         "CCS (Type 1)": "CCS1", "CHAdeMO": "CHAdeMO", "Type 1 (J1772)": "Type 1", "Tesla (Model S/X)": "Tesla",
         "Tesla (Roadster)": "Tesla", "Tesla Supercharger": "Tesla", "Tesla (Supercharger)": "Tesla",
         "Schuko": "Шуко", "CEE 3 Pin": "CEE", "CEE 5 Pin": "CEE"}


def main():
    key = os.environ.get("OCM_API_KEY", "").strip()
    if not key:
        print("no OCM_API_KEY: Open Charge Map skipped")
        return
    q = urllib.parse.urlencode({"output": "json", "countrycode": "BG", "maxresults": 10000, "compact": "false",
                                "verbose": "false", "key": key})
    req = urllib.request.Request(API + "?" + q, headers={"User-Agent": common.UA, "X-API-Key": key})
    data = None
    for i in range(3):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=180))
            break
        except Exception as e:  # noqa: BLE001
            print("retry", type(e).__name__, str(e)[:80].replace(key, "***"), flush=True)
            time.sleep(10 * (i + 1))
    if not isinstance(data, list) or len(data) < 20:
        print("Open Charge Map: no usable answer, old file kept")
        return
    out, skipped = [], {"licence": 0, "not operational": 0, "no point": 0}
    for p in data:
        dp = p.get("DataProvider") or {}
        if not dp.get("IsOpenDataLicensed"):
            skipped["licence"] += 1
            continue
        st = p.get("StatusType") or {}
        if st.get("IsOperational") is False:
            skipped["not operational"] += 1
            continue
        a = p.get("AddressInfo") or {}
        if a.get("Latitude") is None or a.get("Longitude") is None:
            skipped["no point"] += 1
            continue
        sock = {}
        for c in p.get("Connections") or []:
            t = (c.get("ConnectionType") or {}).get("Title") or ""
            name = SHORT.get(t) or t.split(" (")[0]
            if not name:
                continue
            n = c.get("Quantity") or 1
            kw = c.get("PowerKW")
            cur = sock.setdefault(name, [0, 0])
            cur[0] += n
            cur[1] = max(cur[1], int(kw) if kw else 0)
        sk = ", ".join(f"{k} ×{v[0]}" + (f" · {v[1]} kW" if v[1] else "") for k, v in sock.items())[:120]
        op = ((p.get("OperatorInfo") or {}).get("Title") or "")[:40]
        if op.lower().startswith("(unknown") or op.lower().startswith("(business"):
            op = ""
        out.append({"id": p["ID"], "t": (a.get("Title") or "Зарядна станция")[:80], "lat": round(a["Latitude"], 5),
                    "lon": round(a["Longitude"], 5), "sk": sk, "op": op, "ph": (a.get("ContactTelephone1") or "")[:30],
                    "addr": ", ".join(x for x in [a.get("AddressLine1"), a.get("Town")] if x)[:100],
                    "free": 1 if "free" in (p.get("UsageCost") or "").lower() else 0})
    if len(out) < 20:
        print("only", len(out), "stations kept: old file kept", skipped)
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"updated": time.strftime("%Y-%m-%d", time.gmtime()), "p": out}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("Open Charge Map stations kept:", len(out), "skipped:", skipped)


if __name__ == "__main__":
    main()
