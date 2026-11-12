#!/usr/bin/env python3
"""Copy the driver reports that are still valid from Firestore into site/reports.json.

The map reads this small file instead of asking Firestore itself. Firestore then costs the same
however many people look at the map: one query every few minutes from here.
"""
import json, os, urllib.request
from datetime import datetime, timezone
import common  # noqa: F401 - IPv4-only patch

URL = "https://firestore.googleapis.com/v1/projects/avtoban-alert-bg/databases/(default)/documents:runQuery"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "reports.json")
TYPES = {"accident", "stranded", "jam", "closed", "roadworks", "fog", "wind", "rocks", "camera"}


def num(x):
    return float(x.get("doubleValue", x.get("integerValue", 0))) if x else 0.0


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    q = {"structuredQuery": {"from": [{"collectionId": "reports"}],
         "where": {"fieldFilter": {"field": {"fieldPath": "exp"}, "op": "GREATER_THAN", "value": {"timestampValue": now}}},
         "limit": 1000}}
    req = urllib.request.Request(URL, data=json.dumps(q).encode(), headers={"Content-Type": "application/json", "User-Agent": common.UA})
    rows = json.load(urllib.request.urlopen(req, timeout=60))
    out = []
    for row in rows:
        d = row.get("document")
        if not d:
            continue
        f = d["fields"]
        t = f.get("t", {}).get("stringValue")
        up, down = int(num(f.get("up"))), int(num(f.get("down")))
        if t not in TYPES or (down >= 2 and down > up):
            continue
        out.append({"id": d["name"].rsplit("/", 1)[1], "t": t, "lat": round(num(f.get("lat")), 5), "lon": round(num(f.get("lon")), 5),
                    "exp": f["exp"]["timestampValue"], "up": up, "down": down})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"updated": now, "reports": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"reports valid now: {len(out)}")


if __name__ == "__main__":
    main()
