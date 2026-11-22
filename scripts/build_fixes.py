#!/usr/bin/env python3
""""Има грешка" reports on places, from Firestore -> site/fixes.json, and notes to OpenStreetMap.

Kinds: gone (the place is no longer there), place (wrong spot on the map), info (wrong phone or hours).
One report per device, place and kind (the app writes fixes/<place>_<device>, a later one replaces it).
site/fixes.json: {"p": {place: [gone, place, info]}}: the app shows "може да е затворено" from 1 "gone" and hides
the place from 2. Reports older than a year are not counted.

When 2 devices report the same problem, an anonymous note is left on OpenStreetMap at the place (once per place
and kind), so its volunteers check and fix the source too; otherwise the next monthly update would bring the
mistake back. At most 5 notes per run.
"""
import hashlib, json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
import common  # noqa: F401 - IPv4-only patch

URL = "https://firestore.googleapis.com/v1/projects/avtoban-alert-bg/databases/(default)/documents:runQuery"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "..", "state", "fixes.json")
OUT = os.path.join(HERE, "..", "site", "fixes.json")
PLACES = os.path.join(HERE, "..", "site", "places.json")
KINDS = ["gone", "place", "info"]
NOTE_TEXT = {
    "gone": "според тях обектът вече не съществува / users report that this place no longer exists",
    "place": "според тях обектът е на друго място / users report that this place is at a different location",
    "info": "според тях телефонът или работното време са грешни / users report a wrong phone number or opening hours",
}
MAX_NOTES = 5


def query(since):
    q = {"structuredQuery": {"from": [{"collectionId": "fixes"}],
         "where": {"fieldFilter": {"field": {"fieldPath": "at"}, "op": "GREATER_THAN", "value": {"timestampValue": since}}},
         "orderBy": [{"field": {"fieldPath": "at"}, "direction": "ASCENDING"}], "limit": 1000}}
    req = urllib.request.Request(URL, data=json.dumps(q).encode(), headers={"Content-Type": "application/json", "User-Agent": common.UA})
    return [r["document"] for r in json.load(urllib.request.urlopen(req, timeout=60)) if r.get("document")]


def note(lat, lon, text):
    data = urllib.parse.urlencode({"lat": lat, "lon": lon, "text": text}).encode()
    req = urllib.request.Request("https://api.openstreetmap.org/api/0.6/notes.json", data=data,
                                 headers={"User-Agent": common.UA})
    return json.load(urllib.request.urlopen(req, timeout=60))["properties"]["id"]


def main():
    try:
        st = json.load(open(STATE, encoding="utf-8"))
    except FileNotFoundError:
        st = {"until": "2026-01-01T00:00:00Z", "r": {}, "noted": {}}
    new = 0
    while True:
        try:
            docs = query(st["until"])
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            print("fixes not readable yet (Firestore rules without 'fixes')")
            docs = []
        for d in docs:
            f = d["fields"]
            p = f.get("p", {}).get("stringValue", "")
            u = f.get("u", {}).get("stringValue", "")
            k = f.get("k", {}).get("stringValue", "")
            at = f.get("at", {}).get("timestampValue")
            if p and u and k in KINDS and at:
                key = hashlib.sha256((p + "_" + u).encode()).hexdigest()[:20]
                st["r"][key] = [p, k, at[:10]]           # the device's latest report on this place
                new += 1
            if at:
                st["until"] = at
        if len(docs) < 1000:
            break
    year = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    agg = {}
    for p, k, day in st["r"].values():
        if day >= year:
            agg.setdefault(p, [0, 0, 0])[KINDS.index(k)] += 1

    # notes to OpenStreetMap from 2 reports
    try:
        places = {x[0]: x for x in json.load(open(PLACES, encoding="utf-8"))["p"]}
    except Exception:  # noqa: BLE001
        places = {}
    sent = 0
    for p, c in sorted(agg.items()):
        for i, k in enumerate(KINDS):
            tag = p + ":" + k
            if c[i] < 2 or tag in st["noted"] or p not in places or sent >= MAX_NOTES:
                continue
            x = places[p]
            kind = {"n": "node", "w": "way", "r": "relation"}[p[0]]
            text = (f"„{x[2]}“ (https://www.openstreetmap.org/{kind}/{p[1:]}): {c[i]} потребители на приложението "
                    f"Avtoban Alert BG, {NOTE_TEXT[k]}. Моля, проверете на място. / Please check on the ground.")
            try:
                st["noted"][tag] = note(x[3], x[4], text)
                sent += 1
                time.sleep(2)
            except Exception as e:  # noqa: BLE001
                print("note failed", p, e)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), separators=(",", ":"), sort_keys=True)
    json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "p": agg},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    print(f"new fix reports: {new}, places reported: {len(agg)}, OpenStreetMap notes sent: {sent}")


if __name__ == "__main__":
    main()
