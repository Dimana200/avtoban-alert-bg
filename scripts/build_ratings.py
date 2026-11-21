#!/usr/bin/env python3
"""Place ratings from Firestore -> site/ratings.json (stars and tag counts per place).

Only ratings newer than the last run are read (Firestore reads stay small however many ratings there are).
Each device's latest rating per place is kept in state/ratings.json under a hash, not the device id.
"""
import hashlib, json, os, urllib.error, urllib.request
from datetime import datetime, timezone
import common  # noqa: F401 - IPv4-only patch

URL = "https://firestore.googleapis.com/v1/projects/avtoban-alert-bg/databases/(default)/documents:runQuery"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "..", "state", "ratings.json")
OUT = os.path.join(HERE, "..", "site", "ratings.json")
TAGS = {"clean", "fast", "parking", "cheap", "dirty", "slow"}


def query(since):
    q = {"structuredQuery": {"from": [{"collectionId": "ratings"}],
         "where": {"fieldFilter": {"field": {"fieldPath": "at"}, "op": "GREATER_THAN", "value": {"timestampValue": since}}},
         "orderBy": [{"field": {"fieldPath": "at"}, "direction": "ASCENDING"}], "limit": 1000}}
    req = urllib.request.Request(URL, data=json.dumps(q).encode(), headers={"Content-Type": "application/json", "User-Agent": common.UA})
    return [r["document"] for r in json.load(urllib.request.urlopen(req, timeout=60)) if r.get("document")]


def main():
    try:
        st = json.load(open(STATE, encoding="utf-8"))
    except FileNotFoundError:
        st = {"until": "2026-01-01T00:00:00Z", "r": {}}
    new = 0
    while True:
        try:
            docs = query(st["until"])
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            # the Firestore rules for ratings are not published yet: nothing to read, keep an empty list
            print("ratings not readable yet (Firestore rules without 'ratings')")
            docs = []
        for d in docs:
            f = d["fields"]
            p = f.get("p", {}).get("stringValue", "")
            u = f.get("u", {}).get("stringValue", "")
            s = int(f.get("s", {}).get("integerValue", 0))
            t = [x.get("stringValue") for x in f.get("t", {}).get("arrayValue", {}).get("values", [])]
            at = f.get("at", {}).get("timestampValue")
            if p and u and 1 <= s <= 5:
                key = hashlib.sha256((p + "_" + u).encode()).hexdigest()[:20]
                st["r"][key] = [p, s, sorted(x for x in t if x in TAGS)]
                new += 1
            if at:
                st["until"] = at
        if len(docs) < 1000:
            break
    agg = {}
    for p, s, t in st["r"].values():
        a = agg.setdefault(p, [0, 0, {}])
        a[0] += 1
        a[1] += s
        for x in t:
            a[2][x] = a[2].get(x, 0) + 1
    out = {pid: [n, round(total / n, 1), tags] for pid, (n, total, tags) in agg.items()}
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), separators=(",", ":"), sort_keys=True)
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "p": out},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    print(f"new ratings: {new}, places rated: {len(out)}")


if __name__ == "__main__":
    main()
