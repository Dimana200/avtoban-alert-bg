#!/usr/bin/env python3
"""Warnings for citizens by municipality ("Моят район") -> site/alerts.json, hourly.

Official NIMH warnings (weather.bg/obshtini, content © НИМХ) for today and tomorrow:
heat, cold, wind, rain, snow/ice per municipality; fog and thunderstorms per region.
Keys are "<region code>|<municipality name>", e.g. "PDV|пловдив" (names repeat across regions, e.g. Бяла).
A "tomorrow" page is used only if NIMH issued it for that date (otherwise it is an old page).
"""
import json, os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import nimh_warn

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "site", "alerts.json")


def day(z, want):
    res = {"date": want.isoformat(), "m": {}, "r": {}}
    for code, d in nimh_warn.fetch_day(z).items():
        if d["date"] != want.isoformat():
            continue
        if d["issued"] and date.fromisoformat(d["issued"]) < want - timedelta(days=2):
            continue                                    # a stale page, not issued for this day
        for name, kinds in d["munis"].items():
            if kinds:
                res["m"][f"{code}|{name}"] = kinds
        r = d["region"]
        if r.get("text") and r["text"] != "Няма опасност":
            res["r"][code] = r
    return res


def main():
    today = datetime.now(ZoneInfo("Europe/Sofia")).date()
    days = [day("d", today), day("u", today + timedelta(days=1))]
    out = {"updated": datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "НИМХ (weather.bg)", "days": days}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for d in days:
        lv = [max(v.values()) for v in d["m"].values()]
        print(f"{d['date']}: municipalities with a warning {len(lv)} (orange {lv.count(2)}, red {lv.count(3)}), regions with text {len(d['r'])}")


if __name__ == "__main__":
    main()
